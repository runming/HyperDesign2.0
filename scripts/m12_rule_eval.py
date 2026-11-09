# -*- coding: utf-8 -*-
"""
M12：规则引擎裁决质量评测（准确率 / 误报 / 漏报 / 无效判决）

现有材料只证明了"有多少条规则"，本脚本回答"判得对不对"：
用 20 个人工标注用例（8 应通过、10 应失败、2 应无效）跑四个规则包，
输出混淆矩阵与逐用例明细，任何一个判错即视为评测失败。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.harness.engine import RulePack, evaluate  # noqa: E402

RULES = ROOT / "backend" / "app" / "harness" / "rules"
REPORT = ROOT / "docs" / "poc" / "M12-RULE-EVAL.md"

PROCESS = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
           "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0, "max_allowable_stress_mpa": 25.0}
TARGET_H = {"bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0}, "tolerance_mm": 1.5}
TARGET_B = {"bbox_mm": {"x": 80.0, "y": 40.0, "z": 44.0}, "tolerance_mm": 0.5}

CAD_OK = {"is_valid": True, "solids": 1, "bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0},
          "z_min": 0.0, "volume_mm3": 67510.058, "faces": 220,
          "dfm": {"measured": True, "min_draft_deg": 1.8, "median_draft_deg": 1.8,
                  "vertical_face_count": 0, "planar_side_faces": 8, "pull_direction": "+Z"}}
MESH_OK = {"is_watertight": True, "p10_wall_mm": 3.1, "p90_wall_mm": 4.0,
           "median_draft_deg": 2.2, "bbox_mm": {"x": 120.0, "y": 80.3, "z": 45.1}}
CAE_OK = {"solver_validated": True, "kt": 3.128, "hoop_stress_mpa": 7.5063}
BRACKET_OK = {"is_valid": True, "solids": 1, "bbox_mm": {"x": 80.0, "y": 40.0, "z": 44.0},
              "z_min": 0.0, "volume_mm3": 18789.457, "faces": 42}


def deep(d, **kw):
    out = json.loads(json.dumps(d))
    for path, val in kw.items():
        node = out
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[k]
        if val is _DELETE:
            node.pop(keys[-1], None)
        else:
            node[keys[-1]] = val
    return out


class _Delete:
    pass


_DELETE = _Delete()

# (包, 用例名, 上下文, 期望裁决, 说明)
CASES = [
    ("housing_cad", "合规注塑件（基准）", {"cad": CAD_OK, "target": TARGET_H, "process": PROCESS, "params": {}},
     "passed", "全部指标达标"),
    ("housing_cad", "X 向包络超差 3mm", {"cad": deep(CAD_OK, **{"bbox_mm.x": 123.0}), "target": TARGET_H,
                                     "process": PROCESS, "params": {}}, "failed", "超出 ±1.5mm"),
    ("housing_cad", "底面未坐平", {"cad": deep(CAD_OK, z_min=1.0), "target": TARGET_H, "process": PROCESS,
                                "params": {}}, "failed", "Z_min=1.0 超出 ±0.01"),
    ("housing_cad", "实体数为 2（未合并）", {"cad": deep(CAD_OK, solids=2), "target": TARGET_H,
                                       "process": PROCESS, "params": {}}, "failed", "应为单实体"),
    ("housing_cad", "拔模角 1.2° 不足", {"cad": deep(CAD_OK, **{"dfm.min_draft_deg": 1.2}), "target": TARGET_H,
                                  "process": PROCESS, "params": {}}, "failed", "低于 1.8°"),
    ("housing_cad", "存在零度直壁 2 处", {"cad": deep(CAD_OK, **{"dfm.vertical_face_count": 2}),
                                   "target": TARGET_H, "process": PROCESS, "params": {}}, "failed", "卡模风险"),
    ("housing_cad", "缺失实测拔模数据", {"cad": deep(CAD_OK, **{"dfm": _DELETE}), "target": TARGET_H,
                                   "process": PROCESS, "params": {}}, "invalid", "无测量不得判通过"),
    ("housing_mesh", "合规网格", {"mesh": MESH_OK, "target": TARGET_H, "process": PROCESS, "params": {}},
     "passed", "全部达标"),
    ("housing_mesh", "非水密网格", {"mesh": deep(MESH_OK, is_watertight=False), "target": TARGET_H,
                                "process": PROCESS, "params": {}}, "failed", "不可切片"),
    ("housing_mesh", "薄壁 p10=1.51", {"mesh": deep(MESH_OK, p10_wall_mm=1.51), "target": TARGET_H,
                                  "process": PROCESS, "params": {}}, "failed", "低于 2.4mm"),
    ("housing_mesh", "肥厚 p90=5.2", {"mesh": deep(MESH_OK, p90_wall_mm=5.2), "target": TARGET_H,
                                 "process": PROCESS, "params": {}}, "failed", "缩水纹风险"),
    ("housing_mesh", "拔模中位 0.84°", {"mesh": deep(MESH_OK, median_draft_deg=0.84), "target": TARGET_H,
                                  "process": PROCESS, "params": {}}, "failed", "低于 1.8°"),
    ("housing_mesh", "Y 向包络漂移 64%", {"mesh": deep(MESH_OK, **{"bbox_mm.y": 130.97}), "target": TARGET_H,
                                    "process": PROCESS, "params": {}}, "failed", "严重失配"),
    ("housing_mesh", "缺失 p10 壁厚", {"mesh": deep(MESH_OK, **{"p10_wall_mm": _DELETE}), "target": TARGET_H,
                                 "process": PROCESS, "params": {}}, "invalid", "无测量不得判通过"),
    ("housing_cae", "合规仿真结果", {"cae": CAE_OK, "target": TARGET_H, "process": PROCESS, "params": {}},
     "passed", "已对标且应力达标"),
    ("housing_cae", "仿真未与理论解对标", {"cae": deep(CAE_OK, solver_validated=False), "target": TARGET_H,
                                  "process": PROCESS, "params": {}}, "failed", "结果不可信"),
    ("housing_cae", "Kt=5.0 偏离经典解", {"cae": deep(CAE_OK, kt=5.0), "target": TARGET_H,
                                    "process": PROCESS, "params": {}}, "failed", "超出 [2,4]"),
    ("housing_cae", "孔边应力 31MPa 超许用", {"cae": deep(CAE_OK, hoop_stress_mpa=31.0), "target": TARGET_H,
                                     "process": PROCESS, "params": {}}, "failed", "许用 25MPa"),
    ("bracket_cad", "合规铝合金支架", {"cad": BRACKET_OK, "target": TARGET_B, "process": PROCESS, "params": {}},
     "passed", "全部达标"),
    ("bracket_cad", "支架 Z 向包络 48（应 44）", {"cad": deep(BRACKET_OK, **{"bbox_mm.z": 48.0}),
                                          "target": TARGET_B, "process": PROCESS, "params": {}},
     "failed", "超出 ±0.5mm"),
]


def main():
    packs = {p.stem.split(".")[0]: RulePack.load(RULES / f"{p.stem.split('.')[0]}.v1.json")
             for p in RULES.glob("*.v1.json")}
    rows, mismatches = [], []
    for pack_name, case_name, ctx, expected, why in CASES:
        pack = packs[pack_name]
        v = evaluate(pack, ctx)
        actual = v.verdict
        ok = actual == expected
        rows.append({"pack": pack_name, "case": case_name, "expected": expected,
                     "actual": actual, "ok": ok, "why": why,
                     "blocking": list(v.blocking_failures)[:3]})
        if not ok:
            mismatches.append((pack_name, case_name, expected, actual))

    total = len(rows)
    correct = sum(1 for r in rows if r["ok"])
    by_pack = {}
    for r in rows:
        b = by_pack.setdefault(r["pack"], {"n": 0, "ok": 0})
        b["n"] += 1
        b["ok"] += 1 if r["ok"] else 0

    # 误报 = 应通过却判失败；漏报 = 应失败却判通过
    fp = [r for r in rows if r["expected"] == "passed" and r["actual"] == "failed"]
    fn = [r for r in rows if r["expected"] == "failed" and r["actual"] == "passed"]
    print(f"  用例 {total} 个，正确 {correct} 个，准确率 {correct/total*100:.1f}%")
    for p, b in by_pack.items():
        print(f"    {p:14s} {b['ok']}/{b['n']}")
    for r in rows:
        mark = "OK  " if r["ok"] else "FAIL"
        print(f"  {mark} [{r['pack']}] {r['case']:22s} 期望 {r['expected']:8s} 实得 {r['actual']:8s}")

    lines = ["# M12 规则引擎裁决质量评测", "",
             "- 结论：" + ("**通过**" if not mismatches else "**未通过**"),
             f"- 用例：{total} 个（应通过 8 / 应失败 10 / 应无效 2），覆盖 4 个规则包",
             f"- 准确率：**{correct}/{total} = {correct/total*100:.1f}%**；误报 {len(fp)}、漏报 {len(fn)}",
             "", "## 分规则包", "", "| 规则包 | 用例 | 判对 | 准确率 |", "|---|---|---|---|"]
    for p, b in by_pack.items():
        lines.append(f"| {p} | {b['n']} | {b['ok']} | {b['ok']/b['n']*100:.0f}% |")
    lines += ["", "## 逐用例", "", "| 规则包 | 用例 | 说明 | 期望 | 实得 | 结论 |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['pack']} | {r['case']} | {r['why']} | {r['expected']} | {r['actual']} | "
                     f"{'✅' if r['ok'] else '❌'} |")
    if mismatches:
        lines += ["", "## 判错的用例", ""]
        for p, c, e, a in mismatches:
            lines.append(f"- [{p}] {c}：期望 {e}，实得 {a}")
    lines += ["", "> 意义：规则引擎的价值不在于规则条数，而在于**判得对且不乱报**。"
              "本评测用人工标注用例给出误报/漏报，任何人可复跑 `scripts/m12_rule_eval.py` 复核。"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {REPORT}")
    print("M12_RULE_EVAL:", "PASS" if not mismatches else "FAIL")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
