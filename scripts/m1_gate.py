# -*- coding: utf-8 -*-
"""
M1 门禁：Harness 规则引擎 + Agent 输出信封 + Skill Registry

门禁项：
  H1 三个规则包可加载，规则/条款引用完整
  H2 真实 CAD-IR 构建结果 -> CAD 规则包整体 passed（含拔模实测、包络、基准面）
  H3 v1 生成式白模真实数据 -> 网格规则包 failed，且命中薄壁/拔模/漂移/水密
  H4 造假注入（薄壁 3.0mm、拔模 2.5°、水密 true）-> 网格包 passed（对照，证明规则方向正确）
  H5 指标缺失 -> 整包 invalid（绝不 passed）
  H6 非法算子（eval）-> HarnessConfigError（规则不能变成代码执行入口）
  H7 加强筋规则：1.60mm 失败 / 1.40mm 通过（1.44mm 律）
  H8 Agent 信封：合法输出通过；非法 status / completed 空结果 / needs_input 无 next_action 全部拒绝
  H9 Agent 权限：越权调用技能被拒
  H10 Skill Registry：未知技能 / 缺字段 结构化报错；强度计算数值合理

用法：python scripts/m1_gate.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.envelope import AgentDefinition, AgentEnvelope, EnvelopeError  # noqa: E402
from app.harness.engine import HarnessConfigError, RulePack, evaluate  # noqa: E402
from app.skills.registry import build_default_registry  # noqa: E402

RULES = ROOT / "backend" / "app" / "harness" / "rules"
IR = ROOT / "examples" / "sensor_housing.m0.ir.json"
RUNNER = ROOT / "backend" / "app" / "cadir" / "runner_freecad.py"
FREECAD = os.environ.get("HD_FREECAD_CMD") or \
    r"C:\Users\omegahyper\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe"
V1_MANIFEST = Path(r"D:\hyperdesign\workspace\proj_20261014_001\manifest.json")
REPORT = ROOT / "docs" / "poc" / "M1-GATE-REPORT.md"

TARGET = {"bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0}, "tolerance_mm": 1.5}
PROCESS = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8, "max_bulk_wall_mm": 4.5}


def build_cad_context():
    tmp = Path(tempfile.mkdtemp(prefix="hd2_m1_"))
    env = dict(os.environ, HD2_CAD_IR=str(IR), HD2_CAD_OUT=str(tmp))
    subprocess.run([FREECAD, str(RUNNER)], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env, timeout=300)
    rep = json.loads((tmp / "cad_report.json").read_text(encoding="utf-8"))
    return rep["metrics"]


def mesh_context_from_v1():
    m = json.loads(V1_MANIFEST.read_text(encoding="utf-8"))
    dfm = m["phase7_dfm_report"]
    bb = m["mesh_metrics"]["actual_bbox_mm"]
    return {
        "is_watertight": dfm["is_watertight"],
        "p10_wall_mm": dfm["measured_p10_wall_mm"],
        "p90_wall_mm": dfm["measured_p90_wall_mm"],
        "median_draft_deg": dfm["measured_median_draft_deg"],
        "bbox_mm": {"x": bb["x"], "y": bb["y"], "z": bb["z"]},
        "face_count": dfm["face_count"],
    }


def main():
    checks = []
    ok_all = True

    def check(gid, name, passed, detail=""):
        nonlocal ok_all
        ok_all = ok_all and passed
        checks.append({"id": gid, "name": name, "passed": passed, "detail": detail})
        print(("  PASS " if passed else "  FAIL ") + f"{gid} {name}: {detail}")

    # ---------------- H1 规则包加载 ----------------
    packs = {}
    try:
        for name in ("housing_cad", "housing_mesh", "housing_rib"):
            packs[name] = RulePack.load(RULES / f"{name}.v1.json")
        total = sum(len(p.rules) for p in packs.values())
        cited = sum(1 for p in packs.values() for r in p.rules if r.citation.get("document"))
        check("H1", "规则包可加载且条款引用完整", cited == total,
              f"{len(packs)} 包 / {total} 条规则 / {cited} 条带文档引用")
    except Exception as exc:
        check("H1", "规则包可加载", False, f"{type(exc).__name__}: {exc}")
        return _write_report(checks, False)

    # ---------------- H2 真实 CAD -> 通过 ----------------
    cad_metrics = build_cad_context()
    ctx_cad = {"cad": cad_metrics, "target": TARGET, "process": PROCESS, "params": {}}
    v_cad = evaluate(packs["housing_cad"], ctx_cad)
    check("H2", "真实 CAD-IR 产物通过 CAD 规则包", v_cad.verdict == "passed",
          f"verdict={v_cad.verdict}, 规则 {len(v_cad.results)} 条, 阻断失败={v_cad.blocking_failures}")
    draft_rule = next(r for r in v_cad.results if r.rule_id == "cad.draft.min")
    check("H2b", "拔模规则取到实测值（非图纸标注）",
          draft_rule.verdict == "passed" and draft_rule.actual is not None,
          f"actual={draft_rule.actual}° vs limit={draft_rule.limit}°, citation={draft_rule.citation.get('clause')}")

    # ---------------- H3 v1 白模真实数据 -> 失败 ----------------
    mesh = mesh_context_from_v1()
    ctx_mesh = {"mesh": mesh, "target": TARGET, "process": PROCESS, "params": {}}
    v_mesh = evaluate(packs["housing_mesh"], ctx_mesh)
    hit = {r.rule_id for r in v_mesh.results if r.verdict == "failed"}
    expect_hit = {"dfm.mesh.watertight", "dfm.wall.p10", "dfm.draft.median",
                  "dfm.envelope.drift_y", "dfm.envelope.drift_z"}
    check("H3", "v1 生成式白模被物理规则否决", v_mesh.verdict == "failed" and expect_hit <= hit,
          f"verdict={v_mesh.verdict}, 命中={sorted(hit)}")
    wall = next(r for r in v_mesh.results if r.rule_id == "dfm.wall.p10")
    check("H3b", "薄壁证据可追溯（实测 1.51mm vs 2.4mm 条款）",
          wall.actual == 1.51 and wall.limit == 2.4 and "2.4mm" in json.dumps(wall.citation, ensure_ascii=False),
          f"actual={wall.actual}mm limit={wall.limit}mm action={wall.suggested_action}")

    # ---------------- H4 造假注入 -> 通过（对照） ----------------
    fake = {"mesh": {"is_watertight": True, "p10_wall_mm": 3.0, "p90_wall_mm": 4.0,
                     "median_draft_deg": 2.5,
                     "bbox_mm": {"x": 120.0, "y": 80.5, "z": 45.2}},
            "target": TARGET, "process": PROCESS, "params": {}}
    v_fake = evaluate(packs["housing_mesh"], fake)
    check("H4", "规则方向正确（合规数据可通过）", v_fake.verdict == "passed",
          f"verdict={v_fake.verdict}（对照：证明 H3 的失败来自数据而非规则写死）")

    # ---------------- H5 指标缺失 -> invalid ----------------
    partial = {"mesh": {"is_watertight": True, "bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0}},
               "target": TARGET, "process": PROCESS, "params": {}}
    v_missing = evaluate(packs["housing_mesh"], partial)
    check("H5", "指标缺失判 invalid（绝不按通过处理）",
          v_missing.verdict == "invalid" and len(v_missing.invalid_rules) >= 3,
          f"verdict={v_missing.verdict}, invalid 规则={v_missing.invalid_rules}")

    # ---------------- H6 非法算子 ----------------
    bad_pack = {"pack_id": "evil", "version": "1.0", "stage": "cad", "rules": [
        {"rule_id": "evil.exec", "severity": "error", "stage": "cad",
         "check": {"op": "eval", "left": {"const": "1+1"}, "right": {"const": 2}},
         "message": "x"}]}
    try:
        RulePack.from_dict(bad_pack)
        check("H6", "非法算子被拒绝", False, "未抛异常")
    except HarnessConfigError as exc:
        check("H6", "非法算子被拒绝（规则不能执行代码）", "eval" in str(exc), str(exc))

    # ---------------- H7 加强筋 1.44mm 律 ----------------
    v_rib_bad = evaluate(packs["housing_rib"], {"rib": {"thickness_mm": 1.60}, "process": PROCESS, "params": {}})
    v_rib_ok = evaluate(packs["housing_rib"], {"rib": {"thickness_mm": 1.40}, "process": PROCESS, "params": {}})
    check("H7", "加强筋 60% 规则（1.60 失败 / 1.40 通过）",
          v_rib_bad.verdict == "failed" and v_rib_ok.verdict == "passed",
          f"1.60mm -> {v_rib_bad.verdict}; 1.40mm -> {v_rib_ok.verdict}")

    # ---------------- H8 Agent 信封 ----------------
    good = {"status": "completed", "confidence": 0.92, "result": {"cad_ir": "ok"},
            "assumptions": ["材料 PC+ABS"], "warnings": [],
            "citations": [{"document": "内部注塑工艺规范_v2.4.pdf", "clause": "壁厚 2.4mm"}]}
    env = AgentEnvelope.parse(good)
    bad_cases = []
    for payload, why in [
        ({"status": "done", "result": {"x": 1}}, "非法 status"),
        ({"status": "completed", "confidence": 0.9, "result": {}}, "completed 空结果"),
        ({"status": "needs_input", "confidence": 0.5, "result": {}}, "needs_input 缺 next_action"),
        ({"status": "completed", "confidence": 1.7, "result": {"x": 1}}, "confidence 越界"),
    ]:
        try:
            AgentEnvelope.parse(payload)
            bad_cases.append(why + ":未拒绝")
        except EnvelopeError:
            pass
    check("H8", "Agent 信封合法通过 / 非法拒绝",
          env.status == "completed" and not bad_cases,
          f"合法 envelope citations={len(env.citations)}；非法用例={bad_cases or '全部正确拒绝'}")

    agent = AgentDefinition(key="cad_agent", name="CAD 建模智能体", version="1.0.0",
                            purpose="把批准参数转成 CAD-IR",
                            not_responsible_for=["不直接执行代码", "不做强度计算"],
                            allowed_skills=["cad.ir.*", "harness.evaluate"],
                            human_gate="design.approval")
    try:
        agent.assert_allowed("phase5.raw_python")
        check("H9", "Agent 越权调用被拒", False, "未拦截")
    except EnvelopeError as exc:
        check("H9", "Agent 越权调用被拒（白名单生效）", "phase5.raw_python" in str(exc), str(exc))

    # ---------------- H10 Skill Registry ----------------
    reg = build_default_registry()
    r1 = reg.call("nope.skill", {})
    r2 = reg.call("calc.shaft.strength", {"torque_nm": 100})
    r3 = reg.call("calc.shaft.strength",
                  {"torque_nm": 120.0, "bending_moment_nm": 350.0, "diameter_mm": 30.0,
                   "yield_mpa": 355.0, "span_mm": 200.0})
    ok10 = (r1.error and r1.error["code"] == "SKILL_NOT_FOUND"
            and r2.error and r2.error["code"] == "SKILL_INPUT_INVALID"
            and r3.ok and r3.output["safety_factor"] > 0)
    check("H10", "Skill Registry 错误码与确定性计算", bool(ok10),
          f"未知技能={r1.error and r1.error['code']} / 缺字段={r2.error and r2.error['code']} / "
          f"σ_vm={r3.output.get('sigma_von_mises_mpa')}MPa n={r3.output.get('safety_factor')}")

    # ---------------- H11 技能串联：CAD 构建 + Harness 判定 ----------------
    t0 = time.time()
    build = reg.call("cad.ir.build", {"ir": json.loads(IR.read_text(encoding="utf-8"))})
    verdict_via_skill = None
    if build.ok:
        verdict_via_skill = reg.call("harness.evaluate",
                                     {"pack_path": str(RULES / "housing_cad.v1.json"),
                                      "context": {"cad": build.output["report"]["metrics"],
                                                  "target": TARGET, "process": PROCESS, "params": {}}})
    check("H11", "技能串联（CAD 构建 -> Harness 判定）",
          bool(build.ok and verdict_via_skill and verdict_via_skill.ok
               and verdict_via_skill.output["verdict"] == "passed"),
          f"build.ok={build.ok}, verdict={(verdict_via_skill.output or {}).get('verdict') if verdict_via_skill and verdict_via_skill.ok else None}, "
          f"耗时 {time.time() - t0:.1f}s")

    return _write_report(checks, ok_all, cad_metrics, mesh, v_cad, v_mesh)


def _write_report(checks, ok_all, cad_metrics=None, mesh=None, v_cad=None, v_mesh=None):
    lines = ["# M1 门禁报告 · Harness + Agent 信封 + Skill Registry", "",
             f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 结论：{'**通过**' if ok_all else '**未通过**'}",
             "- 规则包：`housing_cad.v1`（CAD 几何）/ `housing_mesh.v1`（网格物理）/ `housing_rib.v1`（加强筋）", "",
             "| 门禁 | 检查项 | 结果 | 证据 |", "|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['id']} | {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    if v_cad:
        lines += ["", "## CAD 规则包逐条裁决（真实 CAD-IR 产物）", "",
                  "| 规则 | 级别 | 判定 | 实测 | 限值 | 单位 |", "|---|---|---|---|---|---|"]
        for r in v_cad.results:
            lines.append(f"| {r.rule_id} | {r.severity} | {r.verdict} | {r.actual} | {r.limit} | {r.unit or ''} |")
    if v_mesh:
        lines += ["", "## 网格规则包逐条裁决（v1 生成式白模实测数据）", "",
                  "| 规则 | 级别 | 判定 | 实测 | 限值 | 建议动作 |", "|---|---|---|---|---|---|"]
        for r in v_mesh.results:
            lines.append(f"| {r.rule_id} | {r.severity} | {r.verdict} | {r.actual} | {r.limit} | {r.suggested_action or ''} |")
    lines += ["", "> 说明：规则只允许受控算子（`gte/lte/near/ratio_dev/between/in_set/all_of/any_of/not`），",
              "> 未知算子直接抛 `HarnessConfigError`；指标缺失一律判 `invalid`，不会按通过处理。"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告已写入 {REPORT}")
    print("M1_GATE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
