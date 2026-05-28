"""Optional RAG-style memory store — vector recall over markdown blobs.

Uses :mod:`chromadb` when installed; otherwise falls back to a small
keyword-frequency scorer so the API works in test envs without C extensions.

Public surface::

    rag = RAGMemory()  # auto-detects backend
    rag.add(text, metadata={"scope": "project"})
    rag.search("question", top_k=4) -> list[(text, score, metadata)]
"""
from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # pragma: no cover — optional
    import chromadb

    _CHROMA = True
except ImportError:  # pragma: no cover
    chromadb = None  # type: ignore[assignment]
    _CHROMA = False


def _tokenize(s: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", s)]


@dataclass
class _MemRecord:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class _BM25Lite:
    """Tiny BM25-ish scorer used when chromadb isn't around."""

    k1 = 1.4
    b = 0.75

    def __init__(self) -> None:
        self.docs: list[_MemRecord] = []
        self.df: Counter[str] = Counter()
        self.avgdl: float = 0.0

    def add(self, rec: _MemRecord) -> None:
        toks = set(_tokenize(rec.text))
        self.docs.append(rec)
        for t in toks:
            self.df[t] += 1
        self.avgdl = sum(len(_tokenize(d.text)) for d in self.docs) / max(1, len(self.docs))

    def search(self, query: str, top_k: int) -> list[tuple[_MemRecord, float]]:
        q_toks = _tokenize(query)
        if not q_toks or not self.docs:
            return []
        n_docs = len(self.docs)
        scored: list[tuple[_MemRecord, float]] = []
        for d in self.docs:
            d_toks = _tokenize(d.text)
            tf = Counter(d_toks)
            score = 0.0
            for t in q_toks:
                if t not in tf:
                    continue
                idf = math.log(1 + (n_docs - self.df[t] + 0.5) / (self.df[t] + 0.5))
                num = tf[t] * (self.k1 + 1)
                den = tf[t] + self.k1 * (1 - self.b + self.b * len(d_toks) / max(self.avgdl, 1))
                score += idf * num / den
            scored.append((d, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(r, s) for r, s in scored[:top_k] if s > 0]


class RAGMemory:
    """Persistent vector-or-bm25 memory store.

    Parameters
    ----------
    persist_dir:
        On-disk directory used by chromadb. Ignored for the BM25 fallback
        (which is in-memory only).
    collection:
        Logical bucket name. You can use multiple collections from one
        process by spinning multiple instances.
    """

    def __init__(self, persist_dir: str | Path | None = None,
                 collection: str = "agentic_memory") -> None:
        self.collection_name = collection
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self._bm25 = _BM25Lite()
        self._chroma_coll: Any = None
        if _CHROMA:
            try:
                client = (
                    chromadb.PersistentClient(path=str(self.persist_dir))
                    if self.persist_dir
                    else chromadb.Client()
                )
                self._chroma_coll = client.get_or_create_collection(collection)
            except Exception:  # pragma: no cover
                self._chroma_coll = None

    # ---------- write ----------
    def add(self, text: str, metadata: dict[str, Any] | None = None,
            id_: str | None = None) -> str:
        rid = id_ or uuid.uuid4().hex[:12]
        meta = metadata or {}
        if self._chroma_coll is not None:  # pragma: no cover — opt
            self._chroma_coll.add(documents=[text], metadatas=[meta], ids=[rid])
        else:
            self._bm25.add(_MemRecord(id=rid, text=text, metadata=meta))
        return rid

    # ---------- read ----------
    def search(self, query: str, top_k: int = 4) -> list[tuple[str, float, dict[str, Any]]]:
        if self._chroma_coll is not None:  # pragma: no cover — opt
            res = self._chroma_coll.query(query_texts=[query], n_results=top_k)
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0] or [{}] * len(docs)
            dists = res.get("distances", [[0.0] * len(docs)])[0]
            # Chroma distances are 0=identical → flip into a similarity-ish score.
            return [(d, 1.0 - float(s), m) for d, m, s in zip(docs, metas, dists, strict=False)]
        hits = self._bm25.search(query, top_k)
        return [(r.text, score, r.metadata) for r, score in hits]

    def __len__(self) -> int:
        if self._chroma_coll is not None:  # pragma: no cover — opt
            return int(self._chroma_coll.count())
        return len(self._bm25.docs)


__all__ = ["RAGMemory"]
