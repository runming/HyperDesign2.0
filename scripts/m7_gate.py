# -*- coding: utf-8 -*-
"""
M7 门禁：设计空间可行性判定与自动修复（先进性 + 场景价值）

门禁项：
  F1 不可行判定：R=3.0 被判不可行，且违反项指向「顶面内角半径」，给出所需 R 下限
  F2 自动修复：最小改动建议可让方案变为可行，且只改必要参数
  F3 真实内核复现：按未修复参数建模会失败（OCC 报错），证明判定不是纸上推演
  F4 修复后重建成功：按建议参数重建通过，且 CAD 准入规则全部通过
  F5 壁厚不足（2.0mm）被判定，并引用企业规范
  F6 拔模不足（0.5°）被判定
  F7 合规参数直接判可行（无误报）
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.cadir.feasibility import HousingParams, evaluate, suggest_repair  # noqa: E402
from app.harness.engine import RulePack, evaluate as harness_eval  # noqa: E402
from app.skills.registry import build_default_registry  # noqa: E402

RULES = ROOT / "backend" / "app" / "harness" / "rules"
IR = ROOT / "examples" / "sensor_housing.m0.ir.json"
REPORT = ROOT / "docs" / "poc" / "M7-GATE-REPORT.md"
RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
FREECAD = os.environ.get("HD_FREECAD_CMD") or \
    r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"

TARGET = {"bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0}, "tolerance_mm": 1.5}
PROCESS = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
           "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0, "max_allowable_stress_mpa": 25.0}
CHECKS = []


def check(name, passed, detail=""):
    CHECKS.append({"name": name, "passed": passed, "detail": detail})
    print(("  PASS " if passed else "  FAIL ") + f"{name}: {detail}")


def build(ir_obj, tag):
    tmp = Path(tempfile.mkdtemp(prefix=f"hd2_m7_{tag}_"))
    ir_path = tmp / "ir.json"
    ir_path.write_text(json.dumps(ir_obj, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, HD2_CAD_IR=str(ir_path), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env, timeout=300)
    rep_path = tmp / "cad_report.json"
    rep = json.loads(rep_path.read_text(encoding="utf-8")) if rep_path.exists() else None
    return rep


def main():
    good = HousingParams(length_mm=120, width_mm=80, height_mm=45,
                         wall_mm=2.4, draft_deg=1.8, corner_r_mm=4.5)
    bad_r = good.copy(corner_r_mm=3.0)

    # F1 不可行判定
    rep_bad = evaluate(bad_r)
    r_top = rep_bad["derived"]["r_top_mm"]
    viol = rep_bad["violations"]
    hint = next((c["hint"] for c in rep_bad["constraints"] if c["name"] == "顶面内角半径"), "")
    check("F1 不可行判定（R=3.0）",
          (not rep_bad["feasible"]) and "顶面内角半径" in viol and "需 R ≥" in hint,
          f"r_top={r_top}mm（要求 ≥0.2），违反项={viol}，提示={hint}")

    # F2 自动修复
    fix = suggest_repair(bad_r)
    steps = fix["steps"]
    only_r = all(s["param"] == "corner_r_mm" for s in steps)
    check("F2 自动修复（最小改动）",
          fix["repaired"] and only_r and len(steps) == 1,
          f"{steps[0]['from']}mm → {steps[0]['to']}mm；理由：{steps[0]['reason'][:60]}…")

    # F3 真实内核复现失败
    ir = json.loads(IR.read_text(encoding="utf-8"))
    ir_bad = json.loads(json.dumps(ir))
    ir_bad["parameters"]["CORNER_R"] = 3.0
    rep3 = build(ir_bad, "bad")
    failed = (rep3 is not None) and (not rep3.get("ok")) and any(
        "CAD_FEATURE_FAILED" in e or "cavity_cut" in e for e in rep3.get("errors", []))
    err = (rep3 or {}).get("errors", [])
    check("F3 真实内核复现（R=3.0 建模失败）", bool(failed),
          f"ok={None if not rep3 else rep3.get('ok')}，错误={(err[0][:110] if err else '无')}")

    # F4 修复后重建 + 准入通过
    new_r = steps[0]["to"]
    ir_ok = json.loads(json.dumps(ir))
    ir_ok["parameters"]["CORNER_R"] = new_r
    rep4 = build(ir_ok, "fixed")
    ok4 = bool(rep4 and rep4.get("ok"))
    metrics = (rep4 or {}).get("metrics") or {}
    pack = RulePack.load(RULES / "housing_cad.v1.json")
    v = harness_eval(pack, {"cad": metrics, "target": TARGET, "process": PROCESS, "params": {}})
    check("F4 修复后重建并通过准入", ok4 and v.verdict == "passed",
          f"R={new_r}mm → 体积 {metrics.get('volume_mm3')}mm³，包络 {metrics.get('bbox_mm')}，"
          f"拔模 {metrics.get('dfm', {}).get('min_draft_deg')}°，准入={v.verdict}")

    # F5 壁厚不足
    thin = good.copy(wall_mm=2.0)
    rep5 = evaluate(thin)
    c5 = next(c for c in rep5["constraints"] if c["name"] == "名义壁厚下限")
    check("F5 壁厚不足被判定", (not rep5["feasible"]) and "名义壁厚下限" in rep5["violations"],
          f"wall=2.0mm → 违反；依据：{c5['formula'][:40]}…")

    # F6 拔模不足
    lowd = good.copy(draft_deg=0.5)
    rep6 = evaluate(lowd)
    check("F6 拔模不足被判定", (not rep6["feasible"]) and "拔模角下限" in rep6["violations"],
          f"draft=0.5° → 违反项={rep6['violations']}")

    # F7 合规参数无误报
    rep7 = evaluate(good)
    check("F7 合规参数判可行（无误报）", rep7["feasible"],
          f"R=4.5/wall=2.4/draft=1.8 → feasible={rep7['feasible']}，r_top={rep7['derived']['r_top_mm']}mm")

    # ---------------- 跨产品族可复制性（同一引擎、不同 IR 与规则包） ----------------
    bracket_ir = json.loads((ROOT / "examples" / "bracket_mount.ir.json").read_text(encoding="utf-8"))
    rep8 = build(bracket_ir, "bracket")
    ok8 = bool(rep8 and rep8.get("ok"))
    m8 = (rep8 or {}).get("metrics") or {}
    bracket_pack = RulePack.load(RULES / "bracket_cad.v1.json")
    target8 = {"bbox_mm": {"x": 80.0, "y": 40.0, "z": 44.0}, "tolerance_mm": 0.5}
    v8 = harness_eval(bracket_pack, {"cad": m8, "target": target8, "process": PROCESS, "params": {}})
    check("F8 同引擎构建第二产品族（CNC 支架）", ok8 and m8.get("is_valid") is True,
          f"体积 {m8.get('volume_mm3')}mm³，包络 {m8.get('bbox_mm')}，实体数 {m8.get('solids')}")

    check("F9 换产品族只换规则包即通过", v8.verdict == "passed",
          f"支架规则包 {bracket_pack.pack_id} 判定={v8.verdict}（无拔模要求，因为是铣削件）")

    # 反证：用注塑规则包跑铣削支架，应因"拔模/壁厚"被判失败 —— 说明规则包与工艺绑定、未硬编码
    housing_pack = RulePack.load(RULES / "housing_cad.v1.json")
    v9 = harness_eval(housing_pack, {"cad": m8, "target": target8, "process": PROCESS, "params": {}})
    check("F10 工艺错配会被规则包拦住（反证）", v9.verdict in ("failed",),
          f"用注塑规则包判铣削支架={v9.verdict}，阻断项={v9.blocking_failures[:3]}")

    return write_report(CHECKS, all(c["passed"] for c in CHECKS), rep_bad, fix, metrics)


def write_report(checks, ok_all, rep_bad, fix, metrics):
    lines = ["# M7 门禁报告 · 设计空间可行性判定与自动修复", "",
             "- 结论：" + ("**通过**" if ok_all else "**未通过**"),
             "- 模块：`backend/app/cadir/feasibility.py`（纯解析，不依赖几何内核）", "",
             "| 门禁 | 结果 | 证据 |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    lines += ["", "## 约束表（R=3.0 的判定过程）", "",
              "| 约束 | 要求 | 实测 | 结论 | 公式 |", "|---|---|---|---|---|"]
    for c in rep_bad["constraints"]:
        lines.append(f"| {c['name']} | {c['required']} | {c['actual']} | "
                     f"{'通过' if c['ok'] else '**违反**'} | {c['formula']} |")
    lines += ["", "## 自动修复步骤", "", "| 参数 | 原值 | 建议值 | 理由 |", "|---|---|---|---|"]
    for s in fix["steps"]:
        lines.append(f"| {s['param']} | {s['from']} | {s['to']} | {s['reason']} |")
    lines += ["", "## 修复后重建结果", "", "```json",
              json.dumps(metrics, ensure_ascii=False, indent=2), "```", "",
              "> 意义：设计不可行时，引擎不是只抛错误，而是给出**可执行的参数修改建议**并自动重建复验，",
              "> 把「工程师反复试错」变成「一次判定 + 一次修复」。"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {REPORT}")
    print("M7_GATE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
