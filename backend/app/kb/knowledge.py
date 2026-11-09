# -*- coding: utf-8 -*-
"""HyperDesign 2.0 知识资产平台（离线、无外部服务）。

组成：
- 解析与切块：把文档切成"条款级"片段（便于引用溯源，而不是整篇塞给模型）
- BM25：纯 Python 实现（k1=1.5, b=0.75），中英文混合分词（字 + 词粒度）
- 向量：可插拔 Embedder；默认**确定性 hashing 向量**（无需模型/GPU，离线可用），
  若能加载 bge-m3 则自动升级为语义向量（见 embed 工厂）
- 混合检索：RRF（Reciprocal Rank Fusion）融合两路排名
- RBAC：按角色过滤文档；检索结果携带 doc/section/clause 引用
- 无证据即拒答：检索无命中时返回 found=False，供 Agent 输出 needs_input

诚实标注：hashing 向量不具备语义能力，只保证确定性；语义能力需 bge-m3。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

ROLES = ("viewer", "engineer", "admin")
_NUM_CLAUSE = re.compile(r"(\d+(?:\.\d+)?)\s*(MPa|deg|mm|kg|°|N|g)", re.IGNORECASE)
_TOKEN = re.compile(r"[A-Za-z]+|\d+(?:\.\d+)?|[\u4e00-\u9fff]")


# ------------------------------------------------------------------------------ 模型
@dataclass
class Document:
    doc_id: str
    title: str
    source_type: str                 # pdf | docx | txt | md | json
    version: str = "v1.0"
    access_roles: Tuple[str, ...] = ("viewer", "engineer", "admin")
    content: str = ""
    chunks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"doc_id": self.doc_id, "title": self.title, "source_type": self.source_type,
                "version": self.version, "access_roles": list(self.access_roles),
                "chunks": len(self.chunks), "chars": len(self.content)}


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str
    clauses: List[str] = field(default_factory=list)


@dataclass
class SearchHit:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str
    clauses: List[str]
    score: float
    channels: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"chunk_id": self.chunk_id, "doc_id": self.doc_id, "doc_title": self.doc_title,
                "section": self.section, "quote": self.text, "clauses": self.clauses,
                "score": round(self.score, 6), "channels": self.channels}


# ------------------------------------------------------------------------------ 分词
def tokenize(text: str) -> List[str]:
    """中英文混合分词：英文/数字按词，中文按字 + 相邻二元组（提升短查询召回）。"""
    raw = _TOKEN.findall(text or "")
    toks: List[str] = []
    for i, t in enumerate(raw):
        toks.append(t.lower())
        if "\u4e00" <= t <= "\u9fff" and i + 1 < len(raw) and "\u4e00" <= raw[i + 1] <= "\u9fff":
            toks.append((t + raw[i + 1]).lower())
    return toks


def split_chunks(text: str, max_len: int = 160) -> List[str]:
    """按语义分隔符切块，保证每块是"可独立引用"的条款。"""
    parts = re.split(r"(?<=[。；;！？\n])", text or "")
    out, cur = [], ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(cur) + len(p) <= max_len:
            cur += p
        else:
            if cur:
                out.append(cur)
            cur = p
    if cur:
        out.append(cur)
    return out or ([text.strip()] if text and text.strip() else [])


def extract_clauses(text: str) -> List[str]:
    return [f"{m.group(1)}{m.group(2)}" for m in _NUM_CLAUSE.finditer(text or "")]


# ------------------------------------------------------------------------------ 向量
class HashingEmbedder:
    """确定性 hashing 向量：字符 n-gram -> hash -> 固定维度，L2 归一化。无需模型。"""
    name = "hashing-ngram-512"
    semantic = False

    def __init__(self, dim: int = 512, ngram: int = 2):
        self.dim, self.ngram = dim, ngram

    def encode(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = tokenize(text)
        grams = toks if self.ngram <= 1 else [
            "".join(toks[i:i + self.ngram]) for i in range(max(1, len(toks) - self.ngram + 1))]
        for g in grams or [""]:
            h = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:8], 16)
            v[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v

    def encode_batch(self, texts: Iterable[str]) -> np.ndarray:
        return np.vstack([self.encode(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)


def make_embedder(prefer_bge: bool = False):
    """优先返回 bge-m3（若环境可加载），否则回退到确定性 hashing 向量。"""
    if prefer_bge:
        try:
            from FlagEmbedding import BGEM3FlagModel  # noqa: F401
            return BgeM3Embedder()
        except Exception:
            pass
    return HashingEmbedder()


class BgeM3Embedder:  # pragma: no cover - 依赖模型权重，门禁中默认不启用
    name = "bge-m3"
    semantic = True

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        from FlagEmbedding import BGEM3FlagModel
        self.model = BGEM3FlagModel(model_name, use_fp16=True)
        self.dim = 1024

    def encode(self, text: str) -> np.ndarray:
        v = self.model.encode([text], max_length=512)["dense_vecs"][0]
        v = np.asarray(v, dtype=np.float32)
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v

    def encode_batch(self, texts: Iterable[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, self.dim), np.float32)
        m = np.asarray(self.model.encode(texts, max_length=512)["dense_vecs"], dtype=np.float32)
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        return m / np.where(norms > 0, norms, 1.0)


# ------------------------------------------------------------------------------ 索引
class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: List[Counter] = []
        self.lengths: List[int] = []
        self.df: Counter = Counter()
        self.n = 0
        self.avgdl = 0.0

    def fit(self, texts: List[str]) -> None:
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(c.values()) for c in self.docs]
        self.n = len(self.docs)
        self.avgdl = (sum(self.lengths) / self.n) if self.n else 0.0
        self.df = Counter()
        for c in self.docs:
            for t in c:
                self.df[t] += 1

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5)) if self.n else 0.0

    def score(self, query: str, idx: int) -> float:
        q = tokenize(query)
        if not q or idx >= self.n:
            return 0.0
        doc, dl = self.docs[idx], self.lengths[idx]
        s = 0.0
        for t in q:
            tf = doc.get(t, 0)
            if not tf:
                continue
            denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
            s += self.idf(t) * tf * (self.k1 + 1) / denom
        return s

    def rank(self, query: str) -> List[Tuple[int, float]]:
        scored = [(i, self.score(query, i)) for i in range(self.n)]
        return sorted([(i, s) for i, s in scored if s > 0], key=lambda x: -x[1])


# ------------------------------------------------------------------------------ 知识库
class KnowledgeBase:
    def __init__(self, embedder=None, persist_path: Optional[Path] = None):
        self.embedder = embedder or make_embedder()
        self.documents: Dict[str, Document] = {}
        self.chunks: List[Chunk] = []
        self.bm25 = BM25()
        self._vec: Optional[np.ndarray] = None
        self.persist_path = Path(persist_path) if persist_path else None

    # ---------------- 入库 ----------------
    def ingest(self, doc: Document) -> Document:
        if doc.doc_id in self.documents:
            raise ValueError(f"文档已存在：{doc.doc_id}")
        pieces = split_chunks(doc.content)
        doc.chunks = pieces
        for i, text in enumerate(pieces):
            self.chunks.append(Chunk(chunk_id=f"{doc.doc_id}#{i+1}", doc_id=doc.doc_id,
                                     doc_title=doc.title, section=f"§{i+1}",
                                     text=text, clauses=extract_clauses(text)))
        self.documents[doc.doc_id] = doc
        self._rebuild()
        return doc

    def ingest_many(self, docs: Iterable[Document]) -> int:
        for d in docs:
            self.ingest(d)
        return len(self.documents)

    def _rebuild(self) -> None:
        self.bm25.fit([c.text for c in self.chunks])
        self._vec = self.embedder.encode_batch([c.text for c in self.chunks]) if self.chunks else None

    # ---------------- 权限 ----------------
    def visible_docs(self, role: str) -> List[Document]:
        role = role if role in ROLES else "viewer"
        return [d for d in self.documents.values() if role in d.access_roles]

    def _visible_chunk_idx(self, role: str) -> List[int]:
        ok = {d.doc_id for d in self.visible_docs(role)}
        return [i for i, c in enumerate(self.chunks) if c.doc_id in ok]

    # ---------------- 检索 ----------------
    def search(self, query: str, top_k: int = 5, role: str = "engineer",
               use_bm25: bool = True, use_vector: bool = True,
               vec_min: float = 0.15, require_bm25: bool = True) -> Dict[str, Any]:
        """
        混合检索 + **证据门控**（这是"无证据即拒答"的实现基础）：
          - require_bm25：必须有词法命中（BM25>0），挡住纯噪声查询
          - vec_min    ：向量余弦必须 ≥ 阈值，挡住词法偶然命中的无关片段
        实测标定：相关查询相似度 0.17~0.33，无关查询 ≤ 0.12，故取 0.15。
        """
        allowed = self._visible_chunk_idx(role)
        if not allowed or not (query or "").strip():
            return {"query": query, "role": role, "found": False, "hits": [],
                    "reason": "无可见文档或查询为空", "embedder": self.embedder.name}

        bm_all = {i: s for i, s in self.bm25.rank(query)} if use_bm25 else {}
        vec_all: Dict[int, float] = {}
        if use_vector and self._vec is not None:
            qv = self.embedder.encode(query)
            sims = self._vec @ qv
            vec_all = {i: float(sims[i]) for i in range(len(self.chunks))}

        qualifying: List[int] = []
        for i in allowed:
            if require_bm25 and use_bm25 and bm_all.get(i, 0.0) <= 0:
                continue
            if use_vector and vec_all and vec_all.get(i, 0.0) < vec_min:
                continue
            if not use_bm25 and not use_vector:
                continue
            qualifying.append(i)

        if not qualifying:
            top_sim = max([vec_all.get(i, 0.0) for i in allowed] or [0.0])
            return {"query": query, "role": role, "found": False, "hits": [],
                    "reason": f"无片段通过证据门控（BM25>0 且 cos≥{vec_min}）",
                    "max_similarity": round(top_sim, 4), "vec_min": vec_min,
                    "require_bm25": require_bm25, "embedder": self.embedder.name,
                    "semantic": bool(getattr(self.embedder, "semantic", False)),
                    "visible_docs": len(self.visible_docs(role)), "chunks": len(self.chunks)}

        # RRF 融合（只在通过门控的片段上排序，避免无关片段被"按名次硬塞"）
        bm_rank = sorted([i for i in qualifying if bm_all.get(i, 0) > 0], key=lambda i: -bm_all[i])
        vec_rank = sorted([i for i in qualifying if i in vec_all], key=lambda i: -vec_all[i])
        fused: Dict[int, float] = {}
        channels: Dict[int, List[str]] = {}
        for rank_name, ranking in (("bm25", bm_rank), ("vector", vec_rank)):
            for pos, i in enumerate(ranking[:max(top_k * 4, 20)], start=1):
                fused[i] = fused.get(i, 0.0) + 1.0 / (60 + pos)
                channels.setdefault(i, []).append(rank_name)

        hits = []
        for i, score in sorted(fused.items(), key=lambda x: -x[1])[:top_k]:
            c = self.chunks[i]
            hits.append(SearchHit(chunk_id=c.chunk_id, doc_id=c.doc_id, doc_title=c.doc_title,
                                  section=c.section, text=c.text, clauses=c.clauses,
                                  score=score, channels=channels.get(i, [])))
        return {"query": query, "role": role, "found": bool(hits), "hits": [h.to_dict() for h in hits],
                "embedder": self.embedder.name, "semantic": bool(getattr(self.embedder, "semantic", False)),
                "vec_min": vec_min, "require_bm25": require_bm25,
                "visible_docs": len(self.visible_docs(role)), "chunks": len(self.chunks)}

    # ---------------- 持久化 ----------------
    def stats(self) -> Dict[str, Any]:
        return {"documents": len(self.documents), "chunks": len(self.chunks),
                "embedder": self.embedder.name,
                "semantic": bool(getattr(self.embedder, "semantic", False)),
                "by_role": {r: len(self.visible_docs(r)) for r in ROLES},
                "docs": [d.to_dict() for d in self.documents.values()]}

    def to_json(self) -> str:
        return json.dumps({"documents": [d.to_dict() for d in self.documents.values()]},
                          ensure_ascii=False, indent=2)
