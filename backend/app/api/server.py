# -*- coding: utf-8 -*-
"""HyperDesign 2.0 API 服务（FastAPI + SSE）。

单进程即可托管：REST + 事件流 + Studio 静态前端 —— 这是"离线单机可部署"的工程证据。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.harness.engine import RulePack  # noqa: E402
from app.skills.registry import build_default_registry  # noqa: E402
from app.workflow.engine import (RUN_WAITING_APPROVAL, WorkflowDefinition,  # noqa: E402
                                 WorkflowEngine, WorkflowError)
from app.workflow.events import EventStore, SSEFormatter  # noqa: E402

APP_VERSION = "2.0.0-m3"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
RULES = ROOT / "backend" / "app" / "harness" / "rules"
WF_PATH = ROOT / "backend" / "app" / "workflow" / "definitions" / "housing_v1.json"
IR_PATH = ROOT / "examples" / "sensor_housing.m0.ir.json"
V1_MANIFEST = Path(r"D:\hyperdesign\workspace\proj_20261014_001\manifest.json")

TARGET = {"bbox_mm": {"x": 120.0, "y": 80.0, "z": 45.0}, "tolerance_mm": 1.5}
PROCESS = {"min_wall_mm": 2.4, "rib_max_mm": 1.44, "min_draft_deg": 1.8,
           "max_bulk_wall_mm": 4.5, "pc_abs_yield_mpa": 50.0, "max_allowable_stress_mpa": 25.0}
MESH_GOOD = {"is_watertight": True, "p10_wall_mm": 3.1, "p90_wall_mm": 4.0,
             "median_draft_deg": 2.2, "bbox_mm": {"x": 120.0, "y": 80.3, "z": 45.1}}


def _v1_mesh() -> Dict[str, Any]:
    m = json.loads(V1_MANIFEST.read_text(encoding="utf-8"))
    d = m["phase7_dfm_report"]
    bb = m["mesh_metrics"]["actual_bbox_mm"]
    return {"is_watertight": d["is_watertight"], "p10_wall_mm": d["measured_p10_wall_mm"],
            "p90_wall_mm": d["measured_p90_wall_mm"],
            "median_draft_deg": d["measured_median_draft_deg"],
            "bbox_mm": {"x": bb["x"], "y": bb["y"], "z": bb["z"]}}


def _bad_ir() -> Dict[str, Any]:
    ir = json.loads(IR_PATH.read_text(encoding="utf-8"))
    ir["features"] = ir["features"] + [{"id": "evil", "type": "execute_script",
                                        "params": {"code": "import os; os.system('rm -rf /')"}}]
    return ir


def _presets() -> Dict[str, Dict[str, Any]]:
    ir = json.loads(IR_PATH.read_text(encoding="utf-8"))
    return {
        "compliant": {
            "title": "合规链路（几何达标 + 白模 DFM 达标）",
            "description": "CAD-IR 构建通过 → 两层 Harness 全过 → 停在人工审批门",
            "expect": "waiting_approval",
            "context": {"ir": ir, "target": TARGET, "process": PROCESS, "mesh": MESH_GOOD},
        },
        "v1-mesh": {
            "title": "v1 生成式白模（真实数据，物理 DFM 不达标）",
            "description": "非水密 / p10 壁厚 1.51mm / 拔模 0.84° / 包络漂移 → 在网格 Harness 被否决，审批门不打开",
            "expect": "failed@n3_mesh_dfm",
            "context": {"ir": ir, "target": TARGET, "process": PROCESS, "mesh": _v1_mesh()},
        },
        "bad-ir": {
            "title": "恶意 CAD-IR（试图执行任意代码）",
            "description": "IR 中注入 execute_script → 解释器以 CAD_FEATURE_UNSUPPORTED 拒绝，后续节点跳过",
            "expect": "failed@n1_cad_build",
            "context": {"ir": _bad_ir(), "target": TARGET, "process": PROCESS, "mesh": MESH_GOOD},
        },
    }


registry = build_default_registry()
store = EventStore(persist_dir=DATA / "events")
engine = WorkflowEngine(registry, store)
definition = WorkflowDefinition.load(WF_PATH)

app = FastAPI(title="HyperDesign 2.0 API", version=APP_VERSION)


# ----------------------------------------------------------------------------- models
class CreateRunRequest(BaseModel):
    preset: str = Field(default="compliant")
    run_id: Optional[str] = None


class ApproveRequest(BaseModel):
    approver: str = Field(default="engineer")
    decision: str = Field(default="approve")
    comment: str = ""


class KbSearchRequest(BaseModel):
    query: str
    role: str = Field(default="engineer")
    top_k: int = 5


class AssistantRequest(BaseModel):
    session: str = Field(default="default")
    text: str


# ----------------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    return {"ok": True, "version": APP_VERSION, "workflow": definition.id,
            "workflow_version": definition.version,
            "skills": len(registry.list()), "runs": len(store.run_ids()),
            "engine": "freecad_occt", "python": sys.version.split()[0]}


@app.get("/api/skills")
def skills():
    return {"skills": registry.list()}


@app.get("/api/harness/packs")
def harness_packs():
    out = []
    for p in sorted(RULES.glob("*.json")):
        pack = RulePack.load(p)
        out.append({"pack_id": pack.pack_id, "version": pack.version, "stage": pack.stage,
                    "part_type": pack.part_type, "file": p.name,
                    "rules": [{"rule_id": r.rule_id, "title": r.title, "severity": r.severity,
                               "blocking": r.is_blocking,
                               "citation": r.citation.get("clause"),
                               "document": r.citation.get("document")} for r in pack.rules]})
    return {"packs": out}


@app.get("/api/presets")
def presets():
    return {"presets": [{"key": k, "title": v["title"], "description": v["description"],
                         "expect": v["expect"]} for k, v in _presets().items()]}


@app.post("/api/assistant/message")
def assistant_message(req: AssistantRequest):
    from app.assistant import service as asvc
    if not req.text.strip():
        raise HTTPException(400, "text 不能为空")
    try:
        return asvc.handle(req.session, req.text)
    except Exception as exc:                      # 助手内部错误不让前端 500
        raise HTTPException(500, f"assistant failed: {exc}")


@app.get("/api/assistant/state")
def assistant_state(session: str = Query("default")):
    from app.assistant import service as asvc
    st = asvc.state(session)
    if st is None:
        return {"session": session, "stage": "new", "turns": 0, "params": {}, "history": []}
    return st


@app.post("/api/assistant/reset")
def assistant_reset(req: AssistantRequest):
    from app.assistant import service as asvc
    return asvc.reset(req.session)


@app.get("/api/kb/stats")
def kb_stats():
    from app.kb.service import get_kb
    return get_kb().stats()


@app.post("/api/kb/search")
def kb_search_api(req: KbSearchRequest):
    from app.kb.service import kb_search as _search
    if req.role not in ("viewer", "engineer", "admin"):
        raise HTTPException(400, f"非法 role '{req.role}'")
    try:
        return _search({"query": req.query, "role": req.role, "top_k": req.top_k})
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/kb/documents")
def kb_documents(role: str = Query("engineer")):
    from app.kb.service import get_kb
    kb = get_kb()
    return {"role": role, "documents": [d.to_dict() for d in kb.visible_docs(role)]}


@app.post("/api/runs")
def create_run(req: CreateRunRequest):
    ps = _presets()
    if req.preset not in ps:
        raise HTTPException(400, f"未知预设 '{req.preset}'（可选：{', '.join(ps)}）")
    try:
        run = engine.create_run(definition, ps[req.preset]["context"], run_id=req.run_id)
        engine.run_until_gate(run)
    except WorkflowError as exc:
        raise HTTPException(409, str(exc))
    return {"run": run.to_dict(), "preset": req.preset, "expect": ps[req.preset]["expect"]}


@app.get("/api/runs")
def list_runs():
    out = []
    for rid in store.run_ids():
        try:
            out.append(engine.get(rid).to_dict())
        except WorkflowError:
            out.append({"run_id": rid, "status": "archived"})
    return {"runs": out}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        return {"run": engine.get(run_id).to_dict()}
    except WorkflowError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str, since: int = Query(0)):
    return {"events": store.replay(run_id, since)}


@app.get("/api/runs/{run_id}/stream")
def stream_events(run_id: str, since: int = Query(0)):
    """SSE：先补拉历史事件，再轮询增量（无第三方依赖）。"""
    try:
        engine.get(run_id)
    except WorkflowError as exc:
        raise HTTPException(404, str(exc))

    def gen():
        last = since
        idle = 0
        while True:
            evs = store.since(run_id, last)
            for ev in evs:
                last = ev.seq
                yield SSEFormatter.frame(ev)
            if not evs:
                idle += 1
                if idle > 60:            # 约 60s 无新事件则结束流
                    yield ": keep-alive\n\n"
                    return
            else:
                idle = 0
            try:
                if engine.get(run_id).status not in ("running", "waiting_approval", "pending"):
                    if not store.since(run_id, last):
                        yield "event: stream.end\ndata: {}\n\n"
                        return
            except WorkflowError:
                return
            time.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: str, req: ApproveRequest):
    try:
        run = engine.get(run_id)
        engine.approve(run, approver=req.approver, decision=req.decision, comment=req.comment)
        return {"run": run.to_dict()}
    except WorkflowError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/runs/{run_id}/artifacts/{name}")
def artifact(run_id: str, name: str):
    try:
        run = engine.get(run_id)
    except WorkflowError:
        raise HTTPException(404, "run 不存在")
    # 路径加固：只允许模型产物文件名，禁止目录穿越
    if name not in ("model.stl", "model.step", "cad_report.json"):
        raise HTTPException(400, "非法产物名")
    out_dir = None
    for st in run.nodes.values():
        od = (st.output or {}).get("out_dir")
        if od:
            out_dir = Path(od)
            break
    if not out_dir:
        raise HTTPException(404, "该 run 无 CAD 产物（可能未到达构建节点）")
    path = (out_dir / name).resolve()
    if out_dir.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "产物不存在")
    return FileResponse(path, filename=name)


# Studio 静态前端（最后挂载，避免吃掉 /api）
FRONTEND = ROOT / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="studio")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("HD2_PORT", "8010"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
