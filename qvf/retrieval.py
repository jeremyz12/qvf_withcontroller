"""Memory representation and lexical retrieval.

QVF operates *after* retrieval, so the retriever here is deliberately simple
and held constant across all experimental conditions (baseline vs QVF): a BM25
ranker over memory contents. The scientific comparison is about what happens
between retrieval and generation, not about retriever quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi


@dataclass
class MemoryItem:
    """One unit of external memory with its real metadata.

    metadata keys used by the benchmarks:
    - session_id: source session identifier
    - session_date: timestamp string of the session ("memory creation time")
    - speaker / role information where available
    """

    memory_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25Retriever:
    """BM25 retrieval over a fixed memory store."""

    def __init__(self, memories: List[MemoryItem]):
        self.memories = memories
        corpus = [_tokenize(m.content) for m in memories]
        # BM25Okapi cannot handle a fully empty corpus
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def retrieve(self, query: str, top_k: int = 10) -> List[MemoryItem]:
        if not self.memories:
            return []
        if self._bm25 is None or top_k >= len(self.memories):
            return list(self.memories)
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            range(len(self.memories)), key=lambda i: scores[i], reverse=True
        )
        top = ranked[:top_k]
        # Preserve original (chronological) order within the selected set so
        # the downstream model sees memories in their natural temporal order.
        top_sorted = sorted(top)
        return [self.memories[i] for i in top_sorted]


class OllamaDenseRetriever:
    """Dense retrieval via a local Ollama embedding model.

    Motivation (from the decisive-experiment decomposition): current-state
    queries mention the OLD value while the answer round mentions the NEW value
    — zero lexical overlap, so BM25 structurally misses it. Semantic embeddings
    can match "does the user still live in Seattle" to "settled into my new
    place in Austin".
    """

    _cache: dict = {}

    def __init__(
        self,
        memories: List[MemoryItem],
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
    ):
        import numpy as np

        self.memories = memories
        self.model = model
        self.base_url = base_url.rstrip("/")
        cache_key = (model, memories[0].memory_id if memories else "", len(memories))
        if cache_key in self._cache:
            self._embs = self._cache[cache_key]
        else:
            self._embs = self._embed([m.content for m in memories])
            self._cache[cache_key] = self._embs
        norms = np.linalg.norm(self._embs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._embs = self._embs / norms

    def _embed(self, texts: List[str]):
        import numpy as np
        import requests

        out = []
        for i in range(0, len(texts), 64):
            batch = texts[i : i + 64]
            r = requests.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": batch},
                timeout=600,
            )
            r.raise_for_status()
            out.extend(r.json()["embeddings"])
        return np.asarray(out, dtype="float32")

    def retrieve(self, query: str, top_k: int = 10) -> List[MemoryItem]:
        import numpy as np

        if not self.memories:
            return []
        if top_k >= len(self.memories):
            return list(self.memories)
        q = self._embed([query])[0]
        qn = q / (np.linalg.norm(q) or 1.0)
        scores = self._embs @ qn
        top = sorted(
            range(len(self.memories)), key=lambda i: float(scores[i]), reverse=True
        )[:top_k]
        return [self.memories[i] for i in sorted(top)]


class OpenAIDenseRetriever(OllamaDenseRetriever):
    """Dense retrieval via the OpenAI embeddings API — removes the local
    Ollama dependency for a pure-API stack. Same interface and scoring as
    OllamaDenseRetriever; only the embedding backend differs, so switching
    backends changes the retrieval protocol and must not happen mid-campaign.

    Select with QVF_EMBED_BACKEND=openai[:<model>] (default model
    text-embedding-3-small, ~$0.02/M tokens).
    """

    _cache: dict = {}

    def __init__(
        self,
        memories: List[MemoryItem],
        model: str = "text-embedding-3-small",
    ):
        import numpy as np

        from openai import OpenAI

        self.memories = memories
        self.model = model
        self._client = OpenAI()
        cache_key = (model, memories[0].memory_id if memories else "", len(memories))
        if cache_key in self._cache:
            self._embs = self._cache[cache_key]
        else:
            self._embs = self._embed([m.content for m in memories])
            self._cache[cache_key] = self._embs
        norms = np.linalg.norm(self._embs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._embs = self._embs / norms

    def _embed(self, texts: List[str]):
        import numpy as np

        out = []
        for i in range(0, len(texts), 256):
            batch = [t if t.strip() else " " for t in texts[i : i + 256]]
            r = self._client.embeddings.create(model=self.model, input=batch)
            out.extend(d.embedding for d in r.data)
        return np.asarray(out, dtype="float32")


def deduplicate_memories(memories: List[MemoryItem]) -> List[MemoryItem]:
    """Drop exact duplicate contents, keeping the first occurrence."""
    seen: set = set()
    out: List[MemoryItem] = []
    for m in memories:
        key = m.content.strip()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out
