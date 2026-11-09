# -*- coding: utf-8 -*-
"""助手会话服务：按 session id 维护多轮上下文（进程内，重启即清空）。"""
from __future__ import annotations

from typing import Dict, Optional

from .engine import Assistant, Session

_SESSIONS: Dict[str, Session] = {}
_MAX = 50


def handle(session_id: str, text: str) -> Dict:
    sid = (session_id or "default").strip() or "default"
    s = _SESSIONS.get(sid)
    if s is None:
        if len(_SESSIONS) >= _MAX:            # 简单上限保护
            _SESSIONS.pop(next(iter(_SESSIONS)))
        s = Session(sid=sid)
        _SESSIONS[sid] = s
    return Assistant(s).message(text)


def state(session_id: str) -> Optional[Dict]:
    s = _SESSIONS.get(session_id)
    if s is None:
        return None
    return {**s.to_dict(), "history": s.history[-20:]}


def reset(session_id: str) -> Dict:
    _SESSIONS.pop(session_id, None)
    return {"session": session_id, "reset": True}
