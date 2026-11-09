# -*- coding: utf-8 -*-
"""工作流引擎：持久化 DAG 执行 + 节点状态机 + 人工审批门 + 断点续跑。

节点类型：
  skill    调用 Skill Registry 中的确定性技能
  harness  调用 Harness 规则包（等价于 skill=harness.evaluate 的语法糖）
  approval 人工审批门（不通过则整个 run 失败，不得自动越过）

纪律：
- Harness 判定为 failed / invalid 时，**阻断后续节点与审批**（物理信号一票否决）；
- 审批门只能由人工 approve，引擎永不自动放行；
- 任何节点失败都写入事件流（含错误码、引用、建议动作），run 停止但保留已完成产物；
- 相同 run_id 不允许并发重跑（幂等）；已结束的 run 不可再次执行。
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..skills.registry import SkillRegistry
from .events import EventStore

RUN_PENDING = "pending"
RUN_RUNNING = "running"
RUN_WAITING_APPROVAL = "waiting_approval"
RUN_SUCCEEDED = "succeeded"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

NODE_PENDING = "pending"
NODE_RUNNING = "running"
NODE_OK = "ok"
NODE_FAILED = "failed"
NODE_SKIPPED = "skipped"
NODE_WAITING = "waiting_approval"


class WorkflowError(Exception):
    pass


@dataclass
class Node:
    id: str
    type: str                       # skill | harness | approval
    title: str
    skill: Optional[str] = None
    version: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    harness_pack: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    on_fail: str = "stop"           # stop | continue
    approval_role: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Node":
        if d["type"] not in ("skill", "harness", "approval"):
            raise WorkflowError(f"节点 {d.get('id')}: 非法 type '{d['type']}'")
        return Node(id=d["id"], type=d["type"], title=d.get("title", d["id"]),
                    skill=d.get("skill"), version=d.get("version"),
                    payload=d.get("payload", {}), harness_pack=d.get("harness_pack"),
                    depends_on=d.get("depends_on", []), on_fail=d.get("on_fail", "stop"),
                    approval_role=d.get("approval_role"))


@dataclass
class WorkflowDefinition:
    id: str
    version: str
    title: str
    nodes: List[Node]
    description: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "WorkflowDefinition":
        nodes = [Node.from_dict(n) for n in d["nodes"]]
        ids = {n.id for n in nodes}
        for n in nodes:
            for dep in n.depends_on:
                if dep not in ids:
                    raise WorkflowError(f"节点 {n.id} 依赖不存在的节点 '{dep}'")
        if len(ids) != len(nodes):
            raise WorkflowError("节点 id 重复")
        wf = WorkflowDefinition(id=d["id"], version=d.get("version", "1.0.0"),
                                title=d.get("title", d["id"]), nodes=nodes,
                                description=d.get("description", ""))
        wf.topological()
        return wf

    @staticmethod
    def load(path: str | Path) -> "WorkflowDefinition":
        return WorkflowDefinition.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def topological(self) -> List[Node]:
        by_id = {n.id: n for n in self.nodes}
        done, order = set(), []

        def visit(nid: str, stack: List[str]) -> None:
            if nid in done:
                return
            if nid in stack:
                raise WorkflowError(f"工作流存在循环依赖：{' -> '.join(stack + [nid])}")
            node = by_id[nid]
            for dep in node.depends_on:
                visit(dep, stack + [nid])
            done.add(nid)
            order.append(node)

        for n in self.nodes:
            visit(n.id, [])
        return order


@dataclass
class NodeState:
    id: str
    status: str = NODE_PENDING
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "status": self.status, "started_at": self.started_at,
                "finished_at": self.finished_at, "output": self.output, "error": self.error,
                "elapsed_ms": int((self.finished_at - self.started_at) * 1000)
                if self.started_at and self.finished_at else None}


@dataclass
class WorkflowRun:
    run_id: str
    definition: WorkflowDefinition
    status: str = RUN_PENDING
    nodes: Dict[str, NodeState] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    approval: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"run_id": self.run_id, "workflow": self.definition.id,
                "workflow_version": self.definition.version, "status": self.status,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "error": self.error, "approval": self.approval,
                "nodes": [n.to_dict() for n in self.nodes.values()]}


class WorkflowEngine:
    def __init__(self, registry: SkillRegistry, events: Optional[EventStore] = None):
        self.registry = registry
        self.events = events or EventStore()
        self._runs: Dict[str, WorkflowRun] = {}

    # ---------------- 运行管理 ----------------
    def create_run(self, definition: WorkflowDefinition, context: Optional[Dict[str, Any]] = None,
                   run_id: Optional[str] = None) -> WorkflowRun:
        rid = run_id or f"run_{uuid.uuid4().hex[:10]}"
        if rid in self._runs:
            raise WorkflowError(f"run_id '{rid}' 已存在，禁止重跑（幂等约束）")
        run = WorkflowRun(run_id=rid, definition=definition, context=context or {},
                          nodes={n.id: NodeState(id=n.id) for n in definition.nodes})
        self._runs[rid] = run
        self.events.append(rid, "run.created", workflow=definition.id, version=definition.version)
        return run

    def run_until_gate(self, run: WorkflowRun, stop_at: Optional[str] = None) -> WorkflowRun:
        """执行到完成/失败/审批门。可重复调用以续跑。"""
        if run.status in (RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED):
            raise WorkflowError(f"run 已结束（{run.status}），不可续跑")
        run.status = RUN_RUNNING
        self.events.append(run.run_id, "run.started")
        order = run.definition.topological()
        for node in order:
            st = run.nodes[node.id]
            if st.status in (NODE_OK, NODE_SKIPPED):
                continue
            if stop_at and node.id == stop_at:
                self.events.append(run.run_id, "run.paused", node_id=node.id, reason="stop_at")
                run.status = RUN_PAUSED if False else RUN_RUNNING  # 保留外层可续跑
                return run
            deps_ok = all(run.nodes[d].status == NODE_OK for d in node.depends_on)
            if not deps_ok:
                st.status = NODE_SKIPPED
                st.error = {"code": "DEPENDENCY_NOT_OK", "message": "上游节点未成功，跳过"}
                self.events.append(run.run_id, "node.skipped", node_id=node.id, reason="dependency")
                continue

            if node.type == "approval":
                st.status = NODE_WAITING
                run.status = RUN_WAITING_APPROVAL
                self.events.append(run.run_id, "run.approval_required", node_id=node.id,
                                   role=node.approval_role, title=node.title)
                return run

            st.status = NODE_RUNNING
            st.started_at = time.time()
            self.events.append(run.run_id, "node.started", node_id=node.id,
                               type=node.type, skill=node.skill or node.harness_pack)
            try:
                if node.type == "skill":
                    res = self.registry.call(node.skill or "", self._render(node.payload, run),
                                             node.version)
                    if not res.ok:
                        raise WorkflowError(f"{res.error['code']}: {res.error['message']}")
                    st.output = res.output
                    st.status = NODE_OK
                elif node.type == "harness":
                    ctx = self._render(node.payload.get("context", {}), run)
                    res = self.registry.call("harness.evaluate",
                                             {"pack_path": node.harness_pack, "context": ctx})
                    if not res.ok:
                        raise WorkflowError(f"{res.error['code']}: {res.error['message']}")
                    st.output = res.output
                    verdict = res.output.get("verdict")
                    if verdict in ("failed", "invalid"):
                        st.status = NODE_FAILED
                        st.error = {"code": f"HARNESS_{verdict.upper()}",
                                    "message": f"Harness 判定 {verdict}",
                                    "verdict": verdict,
                                    "rules": [r["rule_id"] for r in res.output.get("results", [])
                                              if r["verdict"] != "passed"]}
                        self.events.append(run.run_id, "node.failed", node_id=node.id,
                                           code=st.error["code"], verdict=verdict,
                                           rules=st.error["rules"])
                        run.status = RUN_FAILED
                        run.error = f"{node.id}: {st.error['message']}"
                        run.finished_at = time.time()
                        self._abort_remaining(run)
                        self.events.append(run.run_id, "run.failed", node_id=node.id,
                                           error=run.error)
                        return run
                    st.status = NODE_OK
                st.finished_at = time.time()
                self.events.append(run.run_id, "node.finished", node_id=node.id, status="ok",
                                   elapsed_ms=int((st.finished_at - st.started_at) * 1000))
            except Exception as exc:
                st.status = NODE_FAILED
                st.finished_at = time.time()
                st.error = {"code": "NODE_FAILED", "message": f"{type(exc).__name__}: {exc}"}
                self.events.append(run.run_id, "node.failed", node_id=node.id,
                                   code=st.error["code"], message=st.error["message"])
                if node.on_fail == "continue":
                    continue
                run.status = RUN_FAILED
                run.error = f"{node.id}: {st.error['message']}"
                run.finished_at = time.time()
                self._abort_remaining(run)
                self.events.append(run.run_id, "run.failed", node_id=node.id, error=run.error)
                return run

        run.status = RUN_SUCCEEDED
        run.finished_at = time.time()
        self.events.append(run.run_id, "run.succeeded")
        return run

    def resume(self, run: WorkflowRun) -> WorkflowRun:
        if run.status != RUN_WAITING_APPROVAL:
            return self.run_until_gate(run)
        return run

    def approve(self, run: WorkflowRun, approver: str, decision: str = "approve",
                comment: str = "") -> WorkflowRun:
        if run.status != RUN_WAITING_APPROVAL:
            raise WorkflowError(f"run 不在审批门状态（当前 {run.status}）")
        if decision not in ("approve", "reject"):
            raise WorkflowError(f"非法 decision '{decision}'")
        waiting = [n for n in run.nodes.values() if n.status == NODE_WAITING]
        run.approval = {"approver": approver, "decision": decision, "comment": comment,
                        "ts": time.time(), "nodes": [n.id for n in waiting]}
        for st in waiting:
            if decision == "approve":
                st.status = NODE_OK
                st.finished_at = time.time()
            else:
                st.status = NODE_FAILED
                st.finished_at = time.time()
                st.error = {"code": "APPROVAL_REJECTED", "message": f"审批驳回：{comment}"}
        self.events.append(run.run_id, "run.approved" if decision == "approve" else "run.rejected",
                           approver=approver, comment=comment)
        if decision == "reject":
            run.status = RUN_FAILED
            run.error = f"审批驳回：{comment}"
            run.finished_at = time.time()
            self.events.append(run.run_id, "run.failed", error=run.error)
            return run
        return self.run_until_gate(run)

    # ---------------- 工具 ----------------
    def _abort_remaining(self, run: WorkflowRun) -> None:
        """run 中止时把尚未执行的节点显式标为 skipped（而不是让它停在 pending，前端语义更清晰）。"""
        for node in run.definition.topological():
            st = run.nodes[node.id]
            if st.status in (NODE_PENDING, NODE_RUNNING):
                st.status = NODE_SKIPPED
                st.finished_at = time.time()
                st.error = {"code": "RUN_ABORTED", "message": "上游失败，工作流中止"}
                self.events.append(run.run_id, "node.skipped", node_id=node.id, reason="run_aborted")

    def _render(self, payload: Dict[str, Any], run: WorkflowRun) -> Dict[str, Any]:
        """$node.<id>.<key> 引用上游节点输出，实现节点间数据传递（无需魔法字符串）。"""
        out: Dict[str, Any] = {}
        for k, v in payload.items():
            out[k] = self._resolve(v, run) if isinstance(v, (str, dict, list)) else v
        return out

    def _resolve(self, v: Any, run: WorkflowRun) -> Any:
        if isinstance(v, str) and v.startswith("$ctx."):
            cur: Any = run.context
            for p in v[5:].split("."):
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    raise WorkflowError(f"引用 $ctx.{v[5:]} 无法解析（运行上下文缺少 '{p}'）")
            return cur
        if isinstance(v, str) and v.startswith("$node."):
            parts = v[6:].split(".")
            nid = parts[0]
            cur: Any = run.nodes[nid].output
            for p in parts[1:]:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    raise WorkflowError(f"引用 $node.{v[6:]} 无法解析（节点 {nid} 输出缺少 '{p}'）")
            return cur
        if isinstance(v, dict):
            return {k: self._resolve(x, run) for k, x in v.items()}
        if isinstance(v, list):
            return [self._resolve(x, run) for x in v]
        return v

    def get(self, run_id: str) -> WorkflowRun:
        if run_id not in self._runs:
            raise WorkflowError(f"未知 run '{run_id}'")
        return self._runs[run_id]


RUN_PAUSED = "paused"
