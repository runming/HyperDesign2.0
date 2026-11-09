# -*- coding: utf-8 -*-
"""
M2 门禁：工作流引擎（DAG / 事件流 / 审批门 / 幂等 / 断点续跑）

门禁项：
  W1 定义可加载、拓扑无环、节点类型合法
  W2 合规数据全流程跑通 -> 停在审批门 waiting_approval，节点 n1/n2/n3 均 ok
  W3 approve 后 run 成功；approval 记录含审批人
  W4 reject 后 run 失败，错误码 APPROVAL_REJECTED
  W5 v1 真实白模 -> n3 判 failed 并阻断，**审批门永不打开**（物理信号一票否决）
  W6 CAD-IR 非法（未知算子）-> n1 失败，后续节点 skipped
  W7 事件流：seq 严格递增、可重放、可补拉、可落盘 JSONL、SSE 帧格式正确
  W8 幂等：重复 run_id 被拒；已结束的 run 不可续跑
"""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.skills.registry import build_default_registry  # noqa: E402
from app.workflow.engine import (RUN_FAILED, RUN_SUCCEEDED, RUN_WAITING_APPROVAL,  # noqa: E402
                                 WorkflowDefinition, WorkflowEngine, WorkflowError)
from app.workflow.events import EventStore, SSEFormatter  # noqa: E402

IR = ROOT / "examples" / "sensor_housing.m0.ir.json"
WF = ROOT / "backend" / "app" / "workflow" / "definitions" / "housing_v1.json"
REPORT = ROOT / "docs" / "poc" / "M2-GATE-REPORT.md"
V1_MANIFEST = Path(r"D:\hyperdesign\workspace\proj_20261014_001\manifest.json")

TARGET = {"bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0}, "tolerance_mm": 1.5}
PROCESS = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
           "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0, "max_allowable_stress_mpa": 25.0}
MESH_GOOD = {"is_watertight": True, "p10_wall_mm": 3.1, "p90_wall_mm": 4.0,
             "median_draft_deg": 2.2, "bbox_mm": {"x": 120.0, "y": 80.3, "z": 45.1}}


def v1_mesh():
    m = json.loads(V1_MANIFEST.read_text(encoding="utf-8"))
    d = m["phase7_dfm_report"]
    bb = m["mesh_metrics"]["actual_bbox_mm"]
    return {"is_watertight": d["is_watertight"], "p10_wall_mm": d["measured_p10_wall_mm"],
            "p90_wall_mm": d["measured_p90_wall_mm"],
            "median_draft_deg": d["measured_median_draft_deg"],
            "bbox_mm": {"x": bb["x"], "y": bb["y"], "z": bb["z"]}}


def main():
    checks = []
    ok_all = True

    def check(gid, name, passed, detail=""):
        nonlocal ok_all
        ok_all = ok_all and passed
        checks.append({"id": gid, "name": name, "passed": passed, "detail": detail})
        print(("  PASS " if passed else "  FAIL ") + f"{gid} {name}: {detail}")

    # W1
    try:
        defn = WorkflowDefinition.load(WF)
        order = [n.id for n in defn.topological()]
        check("W1", "工作流定义可加载、拓扑无环", len(order) == len(defn.nodes),
              f"{defn.id}@{defn.version} 节点 {order}")
    except Exception as exc:
        check("W1", "工作流定义可加载", False, f"{type(exc).__name__}: {exc}")
        return _write(checks, False)

    ir = json.loads(IR.read_text(encoding="utf-8"))
    tmpdir = Path(tempfile.mkdtemp(prefix="hd2_m2_"))
    store = EventStore(persist_dir=tmpdir / "events")
    engine = WorkflowEngine(build_default_registry(), store)

    # W2 合规数据跑到审批门
    run = engine.create_run(defn, {"ir": ir, "target": TARGET, "process": PROCESS, "mesh": MESH_GOOD})
    engine.run_until_gate(run)
    node_status = {n.id: n.status for n in run.nodes.values()}
    check("W2", "合规数据跑到审批门", run.status == RUN_WAITING_APPROVAL and
          node_status["n1_cad_build"] == "ok" and node_status["n2_cad_harness"] == "ok"
          and node_status["n3_mesh_dfm"] == "ok" and node_status["n4_human_approval"] == "waiting_approval",
          f"run={run.status} nodes={node_status}")

    # W3 approve
    engine.approve(run, approver="张工", decision="approve", comment="几何与工艺均达标，放行")
    check("W3", "审批通过后 run 成功", run.status == RUN_SUCCEEDED and run.approval.get("approver") == "张工",
          f"run={run.status} approver={run.approval.get('approver')}")

    # W4 reject
    run_r = engine.create_run(defn, {"ir": ir, "target": TARGET, "process": PROCESS, "mesh": MESH_GOOD})
    engine.run_until_gate(run_r)
    engine.approve(run_r, approver="李工", decision="reject", comment="外观评审未过")
    check("W4", "审批驳回后 run 失败", run_r.status == RUN_FAILED and "审批驳回" in (run_r.error or ""),
          f"run={run_r.status} error={run_r.error}")

    # W5 v1 白模 -> 物理否决，审批门不打开
    run_bad = engine.create_run(defn, {"ir": ir, "target": TARGET, "process": PROCESS, "mesh": v1_mesh()})
    engine.run_until_gate(run_bad)
    st = run_bad.nodes["n3_mesh_dfm"]
    check("W5", "白模物理 DFM 不达标即阻断（审批门永不打开）",
          run_bad.status == RUN_FAILED and st.status == "failed"
          and st.error.get("verdict") == "failed"
          and run_bad.nodes["n4_human_approval"].status not in ("ok", "waiting_approval"),
          f"run={run_bad.status}, n3={st.status}, 违规规则={st.error.get('rules')}, "
          f"审批节点={run_bad.nodes['n4_human_approval'].status}")

    # W6 非法 IR -> n1 失败 + 后续 skipped
    bad_ir = json.loads(IR.read_text(encoding="utf-8"))
    bad_ir["features"].append({"id": "evil", "type": "execute_script", "params": {"code": "rm -rf /"}})
    run_ir = engine.create_run(defn, {"ir": bad_ir, "target": TARGET, "process": PROCESS, "mesh": MESH_GOOD})
    engine.run_until_gate(run_ir)
    check("W6", "非法 CAD-IR 在 n1 被拒且后续节点跳过",
          run_ir.status == RUN_FAILED and run_ir.nodes["n1_cad_build"].status == "failed"
          and run_ir.nodes["n2_cad_harness"].status == "skipped"
          and run_ir.nodes["n4_human_approval"].status == "skipped",
          f"run={run_ir.status}, n1={run_ir.nodes['n1_cad_build'].status}, "
          f"n2={run_ir.nodes['n2_cad_harness'].status}, n4={run_ir.nodes['n4_human_approval'].status}")

    # W7 事件流
    evs = store.all(run.run_id)
    seqs = [e.seq for e in evs]
    monotonic = all(b > a for a, b in zip(seqs, seqs[1:]))
    replay = store.replay(run.run_id, 0)
    tail = store.since(run.run_id, seqs[len(seqs) // 2])
    frame = SSEFormatter.frame(evs[-1])
    persisted = (tmpdir / "events" / f"{run.run_id}.jsonl").exists()
    check("W7", "事件流单调/可重放/可补拉/落盘/SSE",
          monotonic and len(replay) == len(evs) and len(tail) < len(evs)
          and frame.startswith("event: ") and "data: " in frame and persisted,
          f"{len(evs)} 事件, seq {seqs[0]}..{seqs[-1]} 单调={monotonic}, 补拉 {len(tail)} 条, jsonl={persisted}")

    # W8 幂等
    dup = False
    try:
        engine.create_run(defn, {"ir": ir}, run_id=run.run_id)
    except WorkflowError:
        dup = True
    rerun = False
    try:
        engine.run_until_gate(run)
    except WorkflowError:
        rerun = True
    check("W8", "幂等约束（重复 run_id / 已结束续跑均拒绝）", dup and rerun,
          f"重复 run_id 被拒={dup}, 已结束续跑被拒={rerun}")

    shutil.rmtree(tmpdir, ignore_errors=True)
    return _write(checks, ok_all, store, run)


def _write(checks, ok_all, store=None, run=None):
    lines = ["# M2 门禁报告 · 工作流引擎（DAG / 事件流 / 审批门）", "",
             f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 结论：{'**通过**' if ok_all else '**未通过**'}",
             f"- 工作流：`housing.design-to-delivery@1.0.0`（4 节点：CAD 构建 → CAD Harness → 网格 DFM Harness → 人工审批）", "",
             "| 门禁 | 检查项 | 结果 | 证据 |", "|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['id']} | {c['name']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    if store and run:
        lines += ["", "## 事件流（合规数据这一跑）", "", "| seq | 事件 | 节点 | 关键负载 |", "|---|---|---|---|"]
        for e in store.all(run.run_id):
            payload = json.dumps(e.payload, ensure_ascii=False)
            lines.append(f"| {e.seq} | {e.type} | {e.node_id or '-'} | {payload[:110]} |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告已写入 {REPORT}")
    print("M2_GATE:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
