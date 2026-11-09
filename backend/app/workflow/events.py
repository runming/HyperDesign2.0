# -*- coding: utf-8 -*-
"""工作流事件流：单调递增序号 + 可重放 + 可补拉。

设计要点（对标 04-workflow-events）：
- 事件必须带 `seq`，客户端按 `task_id + seq` 去重与补拉；
- 事件只追加，不可修改（审计友好）；
- 状态仍以快照为准，事件流用于审计与前端动画重建。
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class Event:
    run_id: str
    seq: int
    type: str                      # run.started / node.started / node.finished / run.approval_required ...
    ts: float
    node_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"run_id": self.run_id, "seq": self.seq, "type": self.type, "ts": self.ts,
                "node_id": self.node_id, "payload": self.payload}

    def iso(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.ts))


class EventStore:
    """线程安全的内存事件存储，可按 run 落盘为 JSONL（审计与回放）。"""

    def __init__(self, persist_dir: Optional[Path] = None):
        self._lock = threading.RLock()
        self._events: Dict[str, List[Event]] = {}
        self._seq: Dict[str, int] = {}
        self.persist_dir = Path(persist_dir) if persist_dir else None
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)

    def append(self, run_id: str, type_: str, node_id: Optional[str] = None,
               **payload: Any) -> Event:
        with self._lock:
            seq = self._seq.get(run_id, 0) + 1
            self._seq[run_id] = seq
            ev = Event(run_id=run_id, seq=seq, type=type_, ts=time.time(),
                       node_id=node_id, payload=payload)
            self._events.setdefault(run_id, []).append(ev)
            if self.persist_dir:
                path = self.persist_dir / f"{run_id}.jsonl"
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
            return ev

    def since(self, run_id: str, seq: int = 0) -> List[Event]:
        with self._lock:
            return [e for e in self._events.get(run_id, []) if e.seq > seq]

    def all(self, run_id: str) -> List[Event]:
        return self.since(run_id, 0)

    def replay(self, run_id: str, from_seq: int = 0) -> List[Dict[str, Any]]:
        """按 seq 去重后返回（模拟客户端补拉后的重建）。"""
        seen, out = set(), []
        for e in self.since(run_id, from_seq):
            if e.seq in seen:
                continue
            seen.add(e.seq)
            out.append(e.to_dict())
        return out

    def run_ids(self) -> List[str]:
        with self._lock:
            return sorted(self._events.keys())


class SSEFormatter:
    """把事件格式化为 Server-Sent Events 文本块。"""

    @staticmethod
    def frame(ev: Event) -> str:
        return "event: {t}\nid: {s}\ndata: {d}\n\n".format(
            t=ev.type, s=ev.seq, d=json.dumps(ev.to_dict(), ensure_ascii=False))
