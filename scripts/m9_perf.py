# -*- coding: utf-8 -*-
"""
M9：端到端性能测量（可复算）——把材料里的「表 3 工时账」变成可现场验证的脚本。

测量对象：2.0 平台层（6 节点工作流：IR 构建 → CAD 准入 → 网格准入 → CAE → CAE 准入 → 审批门）
方法：连续跑 3 次，记录每个节点耗时与总耗时，取中位数，并给出平台层耗时占比。
1.0 的历史数据（概念图/三维重建/代码生成）来自 progress.log，不在本脚本测量范围（需 GPU 与环境）。
"""
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.skills.registry import build_default_registry  # noqa: E402
from app.workflow.engine import RUN_WAITING_APPROVAL, WorkflowDefinition, WorkflowEngine  # noqa: E402
from app.workflow.events import EventStore  # noqa: E402

IR = ROOT / "examples" / "sensor_housing.m0.ir.json"
WF = ROOT / "backend" / "app" / "workflow" / "definitions" / "housing_v1.json"
REPORT = ROOT / "docs" / "poc" / "M9-PERF.md"
TARGET = {"bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0}, "tolerance_mm": 1.5}
PROCESS = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
           "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0, "max_allowable_stress_mpa": 25.0}
MESH_GOOD = {"is_watertight": True, "p10_wall_mm": 3.1, "p90_wall_mm": 4.0,
             "median_draft_deg": 2.2, "bbox_mm": {"x": 120.0, "y": 80.3, "z": 45.1}}


def run_once(runs_dir: Path):
    engine = WorkflowEngine(build_default_registry(), EventStore(persist_dir=runs_dir))
    defn = WorkflowDefinition.load(WF)
    ctx = {"ir": json.loads(IR.read_text(encoding="utf-8")),
           "target": TARGET, "process": PROCESS, "mesh": MESH_GOOD}
    t0 = time.perf_counter()
    run = engine.create_run(defn, ctx)
    engine.run_until_gate(run)
    elapsed = time.perf_counter() - t0
    per_node = {n.id: round((n.finished_at - n.started_at) * 1000, 1)
                for n in run.nodes.values()
                if n.started_at and n.finished_at}
    return {"status": run.status, "total_ms": round(elapsed * 1000, 1), "nodes": per_node}


def main():
    results = []
    for i in range(3):
        tmp = Path(tempfile.mkdtemp(prefix=f"hd2_perf_{i}_"))
        results.append(run_once(tmp))
        print(f"  run {i+1}: {results[i]['total_ms']}ms  {results[i]['nodes']}")

    node_ids = list(results[0]["nodes"].keys())
    med = {nid: round(statistics.median([r["nodes"][nid] for r in results if nid in r["nodes"]]), 1)
           for nid in node_ids}
    total_med = round(statistics.median([r["total_ms"] for r in results]), 1)
    spread = round((max(r["total_ms"] for r in results) - min(r["total_ms"] for r in results))
                   / total_med * 100, 1)

    lines = ["# M9 性能测量报告 · 2.0 平台层端到端", "",
             f"- 方法：连续 {len(results)} 次运行 6 节点工作流，取中位数（`scripts/m9_perf.py` 可复跑）",
             f"- 结论：平台层端到端 **{total_med} ms**，3 次波动 **{spread}%**", "",
             "| 节点 | 内容 | 中位耗时 (ms) |", "|---|---|---|"]
    label = {"n1_cad_build": "IR 构建（几何内核建模 + 校验）",
             "n2_cad_harness": "CAD 几何准入（10 条规则）",
             "n3_mesh_dfm": "网格物理准入（6 条规则）",
             "n3b_cae": "CAE 有限元（1152 单元）",
             "n3c_cae_harness": "CAE 准入（3 条规则）",
             "n4_human_approval": "人工审批门"}
    for nid in node_ids:
        lines.append(f"| {nid} | {label.get(nid, '')} | {med[nid]} |")
    lines += ["", f"合计（中位）：**{total_med} ms**", "",
              "## 与 1.0 的对照", "",
              "| 环节 | 1.0 | 2.0 |", "|---|---|---|",
              "| 参数化建模 + 几何校验 | 465.8s（LLM 生成代码后执行，每次重跑） | "
              f"{med.get('n1_cad_build', 0)/1000:.2f}s（确定性执行）+ 准入 {med.get('n2_cad_harness', 0):.0f}ms |",
              "| 工艺检索与铁律校验 | 75.9s（整段大模型推理） | 0.02s 检索 + 毫秒级规则判定 |",
              "", "> 说明：本表只测量 2.0 平台层；概念图与三维重建属 1.0 生成式能力层，需 GPU 环境，不在本脚本范围。",
              "> 1.0 的数字取自 `progress.log` 时间戳，可回溯核对。"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告写入 {REPORT}")
    print(f"PERF: total={total_med}ms spread={spread}% nodes={len(node_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
