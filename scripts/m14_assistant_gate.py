# -*- coding: utf-8 -*-
"""M14 门禁：交互式 AI 助手（前期需求 / 中期修改 / 后期定型）。

A1 前期：自然语言需求 → 结构化 brief + 包络写入 IR
A2 守卫：壁厚改 2.0 → 拒绝并引用规范，IR 不变
A3 守卫：拔模改 0.5 → 拒绝
A4 可行性与内核联动：圆角改 3.0 → 判不可行并回滚，给出所需下限
A5 中期修改生效：圆角改 5.0 → 重建成功 + 准入通过
A6 标准件吸附：安装孔改 M4 底孔 → 取标准 Ø3.3
A7 后期定型：定型后拒绝修改；解冻后可继续
A8 多轮上下文：IR 累积变更与历史完整
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.assistant.engine import Assistant, Session  # noqa: E402
from app.standards.tables import snap_hole, tolerance_for  # noqa: E402

REPORT = ROOT / "docs" / "poc" / "M14-ASSISTANT-GATE.md"
CHECKS = []


def check(name, passed, detail=""):
    CHECKS.append({"name": name, "passed": passed, "detail": detail})
    print(("  PASS " if passed else "  FAIL ") + f"{name}: {detail}")


def main():
    s = Session(sid="s-gate")
    a = Assistant(s)

    # A1 前期需求
    r1 = a.message("帮我设计一个 120×80×45 的 PC+ABS 传感器外壳，二号车间注塑")
    ok1 = (r1["kind"] == "brief" and r1["params"]["LENGTH_X"] == 120.0
           and r1["params"]["WIDTH_Y"] == 80.0 and r1["params"]["HEIGHT_Z"] == 45.0
           and r1["stage"] == "designing")
    check("A1 前期需求建模", ok1,
          f"包络={[r1['params'][k] for k in ('LENGTH_X', 'WIDTH_Y', 'HEIGHT_Z')]}，阶段={r1['stage']}，"
          f"材料={r1.get('brief', {}).get('material')}，重建成功={r1.get('build', {}).get('ok')}")

    # A1b 改包络：助手自动重算派生参数（立柱顶到内顶面 / 导光窗随高度 / 高厚比超限抬壁厚）
    r1b = a.message("包络改成 130×90×50")
    m1b = r1b.get("build", {}).get("metrics") or {}
    ok1b = (r1b["kind"] == "modified" and r1b["params"]["LENGTH_X"] == 130.0
            and r1b["params"]["WALL"] == 2.5          # 50/2.4 超过高厚比 20 → 自动抬到 2.5
            and r1b["params"]["POST_H"] == 47.5       # 立柱高度随包络重算
            and m1b.get("solids") == 1 and r1b.get("verdict") == "passed")
    check("A1b 改包络后自动重算派生参数并重建通过", ok1b,
          f"壁厚={r1b['params']['WALL']}（高厚比自动抬升）、立柱高={r1b['params']['POST_H']}、"
          f"导光窗 Z={r1b['params']['LED_Z']}、实体数={m1b.get('solids')}、准入={r1b.get('verdict')}")

    # A2 壁厚守卫
    before = dict(r1b["params"])
    r2 = a.message("把壁厚改成 2.0")
    ok2 = (r2["kind"] == "rejected" and r2["params"]["WALL"] == before["WALL"] != 2.0
           and "2.4" in r2["reply"])
    check("A2 壁厚越界被拒（引用规范）", ok2,
          f"裁决={r2['kind']}，壁厚仍为 {r2['params']['WALL']}mm，回复含规范下限={'2.4' in r2['reply']}")

    # A3 拔模守卫
    r3 = a.message("拔模改成 0.5 度")
    ok3 = r3["kind"] == "rejected" and r3["params"]["DRAFT_DEG"] == before["DRAFT_DEG"]
    check("A3 拔模越界被拒", ok3, f"裁决={r3['kind']}，拔模仍为 {r3['params']['DRAFT_DEG']}°")

    # A4 几何不可行
    r4 = a.message("圆角改成 3.0")
    ok4 = (r4["kind"] == "infeasible" and r4["params"]["CORNER_R"] == before["CORNER_R"]
           and "建议" in r4["reply"])
    check("A4 几何不可行被拒并给出下限", ok4,
          f"裁决={r4['kind']}，圆角回滚到 {r4['params']['CORNER_R']}mm，"
          f"r_top={r4.get('feasibility', {}).get('derived', {}).get('r_top_mm')}mm")

    # A5 修改生效 + 重建 + 准入
    r5 = a.message("圆角改成 5.0")
    ok5 = (r5["kind"] == "modified" and r5["params"]["CORNER_R"] == 5.0
           and r5.get("build", {}).get("ok") and r5.get("verdict") == "passed")
    check("A5 参数修改生效并重建通过", ok5,
          f"圆角={r5['params']['CORNER_R']}mm，体积={r5.get('build', {}).get('metrics', {}).get('volume_mm3')}mm³，"
          f"准入={r5.get('verdict')}")

    # A6 标准件吸附
    r6 = a.message("安装柱改成 M4 底孔")
    std = snap_hole("M4", "pilot")
    ok6 = (r6["kind"] == "modified" and r6["params"]["POST_PILOT_D"] == std["diameter_mm"]
           and r6.get("standards"))
    check("A6 国标件吸附（M4 底孔）", ok6,
          f"底孔={r6['params']['POST_PILOT_D']}mm（标准 {std['diameter_mm']}mm，{std['source']}）")

    # A7 定型与冻结
    r7 = a.message("定型")
    r8 = a.message("把壁厚改成 3.0")
    ok7 = (r7["kind"] == "frozen" and r7["stage"] == "frozen" and r8["kind"] == "frozen")
    check("A7 定型后拒绝修改", ok7,
          f"定型={r7['kind']}，阶段={r7['stage']}，冻结后修改被拒={r8['kind']}")

    r9 = a.message("解冻")
    r10 = a.message("把壁厚改成 2.6")
    ok8 = (r9["kind"] == "unfreeze" and r10["kind"] == "modified"
           and r10["params"]["WALL"] == 2.6)
    check("A8 解冻后继续修改（多轮上下文）", ok8,
          f"解冻={r9['kind']}，壁厚={r10['params']['WALL']}mm，历史 {len(s.history)} 条")

    # 公差表（供工程图标注）
    tol = tolerance_for(45.0, "IT9")
    check("A9 公差表可用（GB/T 1800.1）", tol["tolerance_um"] == 62,
          f"φ45 IT9 = {tol['tolerance_um']}µm（{tol['tolerance_mm']}mm）")

    return write_report(CHECKS, all(c["passed"] for c in CHECKS), s)


def write_report(checks, ok_all, session):
    lines = ["# M14 门禁报告 · 交互式 AI 助手", "",
             "- 结论：" + ("**通过**" if ok_all else "**未通过**"),
             "- 模块：`backend/app/assistant/engine.py`（意图解析 + 会话 + 参数补丁 + 守卫 + 重建 + 裁决）、"
             "`backend/app/standards/tables.py`（国标件与公差表）",
             f"- 会话：{len(session.history)} 轮，最终阶段 `{session.stage}`", "",
             "| 门禁 | 结果 | 证据 |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    lines += ["", "## 对话记录（节选）", ""]
    for h in session.history[:20]:
        role = "用户" if h["role"] == "user" else "助手"
        lines.append(f"- **{role}**：{h['text'][:120]}")
    lines += ["", "> 要点：助手不改越界参数（壁厚/拔模/圆角），而是给出依据与可行下限；",
              "> 每次修改都跑可行性复算 + 内核实测 + 规则裁决，形成「证据 → 回复」闭环。"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {REPORT}")
    print("M14_GATE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
