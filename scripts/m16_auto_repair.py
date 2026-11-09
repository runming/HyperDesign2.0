# -*- coding: utf-8 -*-
"""M16 门禁：工程证据驱动的自动修复闭环。

R1 实体断开（POST_H 未顶到内顶面）→ 自动修复后单实体通过
R2 拔模不足 → 自动抬到下限并通过
R3 壁厚不足 → 抬到 2.4 并同步立柱高度，通过
R4 不可修复场景（包络偏差过大）→ 不硬修，如实回报
R5 修复轮次上限 ≤2，且每轮带结构化证据
R6 助手对话中触发自动修复并成功（端到端）
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.harness import repair as R  # noqa: E402

REPORT = ROOT / "docs" / "poc" / "M16-AUTO-REPAIR.md"
BASE_IR = json.loads((ROOT / "examples" / "sensor_housing.m0.ir.json").read_text(encoding="utf-8"))
CHECKS = []


def check(name, passed, detail=""):
    CHECKS.append({"name": name, "passed": passed, "detail": detail})
    print(("  PASS " if passed else "  FAIL ") + f"{name}: {detail}")


def with_params(**kw):
    ir = json.loads(json.dumps(BASE_IR))
    ir["parameters"].update(kw)
    return ir


def main():
    # R1 实体断开：POST_H 与包络不匹配
    ir1 = with_params(POST_H=40.0)
    r1 = R.auto_repair(ir1)
    first = r1["attempts"][0]
    acts1 = r1["attempts"][1]["actions"] if len(r1["attempts"]) > 1 else []
    check("R1 实体断开自动修复", r1["ok"] and first["failed"] == ["cad.solid.single"]
          and acts1 and acts1[0]["param"] == "POST_H",
          f"首轮 {first['verdict']}（实体数 {first['metrics'].get('solids')}）→ "
          f"修复动作 {[(a['param'], a['after']) for a in acts1]} → {r1['rounds']} 轮后通过")

    # R2 拔模不足
    ir2 = with_params(DRAFT_DEG=0.9)
    r2 = R.auto_repair(ir2)
    acts2 = r2["attempts"][1]["actions"] if len(r2["attempts"]) > 1 else []
    check("R2 拔模不足自动修复", r2["ok"] and any(a["param"] == "DRAFT_DEG" and a["after"] == 1.8
                                            for a in acts2),
          f"动作 {[(a['param'], a['after']) for a in acts2]} → 通过={r2['ok']}")

    # R3 壁厚不足（同时影响立柱高度）
    ir3 = with_params(WALL=2.0)
    r3 = R.auto_repair(ir3)
    acts3 = r3["attempts"][1]["actions"] if len(r3["attempts"]) > 1 else []
    check("R3 壁厚不足自动修复并同步立柱高", r3["ok"] and any(a["param"] == "WALL" for a in acts3),
          f"动作 {[(a['param'], a['after']) for a in acts3]} → 通过={r3['ok']}，"
          f"最终 POST_H={r3['ir']['parameters']['POST_H']}")

    # R4 不可修复：包络与目标严重不符（目标由参数推出，故改参数但几何不跟随）
    ir4 = with_params(LENGTH_X=120.0)
    ir4["features"][0]["params"]["length"] = 150.0        # 几何比声明的长 30mm
    r4 = R.auto_repair(ir4)
    check("R4 不可修复场景如实回报", (not r4["ok"]) and len(r4["attempts"]) >= 1,
          f"通过={r4['ok']}，首轮未通过项={r4['attempts'][0]['failed']}，"
          f"轮次={r4['rounds']}（不硬修）")

    # R5 轮次上限与证据结构
    ok5 = r1["rounds"] <= 2 and all({"round", "verdict", "failed", "actions"} <= set(a)
                                    for a in r1["attempts"])
    check("R5 修复轮次上限与证据结构", ok5,
          f"轮次={r1['rounds']}，证据字段={sorted(r1['attempts'][0].keys())}")

    # R6 助手端到端：改包络后触发自动修复
    from app.assistant.engine import Assistant, Session
    s = Session(sid="repair-gate")
    a = Assistant(s)
    a.message("帮我设计一个 120×80×45 的 PC+ABS 传感器外壳")
    a.message("把立柱高度改成 40")
    reply = a.message("检查一下能不能修好")
    ok6 = reply["kind"] in ("repaired", "modified", "regression") and reply.get("build", {}).get("ok")
    check("R6 助手对话触发修复（端到端）", ok6,
          f"裁决={reply['kind']}，重建={reply.get('build', {}).get('ok')}，"
          f"准入={reply.get('verdict')}")

    return write_report(all(c["passed"] for c in CHECKS), r1, r4)


def write_report(ok_all, r1, r4):
    lines = ["# M16 门禁报告 · 工程证据驱动的自动修复闭环", "",
             "- 结论：" + ("**通过**" if ok_all else "**未通过**"),
             "- 模块：`backend/app/harness/repair.py`（证据 → 参数补丁 → 重建 → 再裁决，最多 2 轮）", "",
             "| 门禁 | 结果 | 证据 |", "|---|---|---|"]
    for c in CHECKS:
        lines.append(f"| {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    lines += ["", "## 修复过程证据链（R1 实体断开）", "",
              "| 轮次 | 裁决 | 未通过项 | 实体数 | 修复动作 |", "|---|---|---|---|---|"]
    for at in r1["attempts"]:
        acts = "；".join(f"{x['param']} {x['before']}→{x['after']}" for x in at["actions"]) or "—"
        lines.append(f"| {at['round']} | {at['verdict']} | {at['failed'] or '无'} | "
                     f"{at['metrics'].get('solids', '—')} | {acts} |")
    lines += ["", "## 不可修复场景（R4）", "",
              f"- 首轮未通过项：{r4['attempts'][0]['failed']}",
              f"- 结论：不硬修，如实回报（修复器只处理有明确几何因果的问题）", "",
              "> 原则：**修不好就不修**。自动修复只在「因果明确」时改参数（立柱顶不到内顶面、拔模低于下限、",
              "> 壁厚低于下限），其他情况一律交人工，避免「为了让通过而通过」。"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {REPORT}")
    print("M16_GATE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
