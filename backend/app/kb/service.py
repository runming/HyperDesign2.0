# -*- coding: utf-8 -*-
"""知识库单例 + 检索技能（API 与 Skill 共用同一份索引，避免重复灌库）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .knowledge import HashingEmbedder, KnowledgeBase

_KB: Optional[KnowledgeBase] = None


def get_kb(prefer_bge: bool = False) -> KnowledgeBase:
    global _KB
    if _KB is None:
        from .seed import seed
        _KB = KnowledgeBase(HashingEmbedder() if not prefer_bge else None)
        seed(_KB)
    return _KB


def kb_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    kb = get_kb()
    q = str(payload.get("query", ""))
    role = str(payload.get("role", "engineer"))
    top_k = int(payload.get("top_k", 5))
    if not q.strip():
        raise ValueError("query 不能为空")
    if role not in ("viewer", "engineer", "admin"):
        raise ValueError(f"非法 role '{role}'")
    return kb.search(q, top_k=top_k, role=role)
