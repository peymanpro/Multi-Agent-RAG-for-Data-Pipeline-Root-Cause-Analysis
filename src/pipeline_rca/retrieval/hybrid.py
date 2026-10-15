"""Hybrid lexical+dense retrieval with deterministic reciprocal-rank fusion."""

from __future__ import annotations

import math
from pipeline_rca.retrieval.dense import DenseRetriever
from pipeline_rca.retrieval.lexical import BM25Retriever
from pipeline_rca.retrieval.models import DocumentChunk, RetrievalHit


class HybridRetriever:
    """Fuse lexical and dense ranking lists without requiring calibrated scores."""

    def __init__(
        self,
        lexical: BM25Retriever,
        dense: DenseRetriever,
        *,
        rrf_constant: int = 60,
        lexical_weight: float = 1.0,
        dense_weight: float = 1.0,
    ) -> None:
        if (
            isinstance(rrf_constant, bool)
            or not isinstance(rrf_constant, int)
            or rrf_constant < 1
        ):
            raise ValueError("rrf_constant must be a positive integer")
        if not math.isfinite(lexical_weight) or lexical_weight <= 0:
            raise ValueError("lexical_weight must be finite and positive")
        if not math.isfinite(dense_weight) or dense_weight <= 0:
            raise ValueError("dense_weight must be finite and positive")
        if set(lexical.chunk_ids) != set(dense.chunk_ids):
            raise ValueError("lexical and dense indexes must contain the same chunk identifiers")
        self._lexical = lexical
        self._dense = dense
        self._rrf_constant = rrf_constant
        self._lexical_weight = lexical_weight
        self._dense_weight = dense_weight

    @property
    def chunk_count(self) -> int:
        """Number of chunks shared by lexical and dense indexes."""
        return self._lexical.chunk_count

    def search(self, query: str, *, top_k: int = 5) -> tuple[RetrievalHit, ...]:
        """Combine two ranked lists using weighted reciprocal-rank fusion."""
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if self.chunk_count == 0:
            return ()
        candidate_k = min(self.chunk_count, max(top_k * 4, top_k))
        lexical_hits = self._lexical.search(query, top_k=candidate_k)
        dense_hits = self._dense.search(query, top_k=candidate_k)

        chunks_by_id: dict[str, DocumentChunk] = {}
        scores: dict[str, float] = {}
        for weight, hits in (
            (self._lexical_weight, lexical_hits),
            (self._dense_weight, dense_hits),
        ):
            for rank, hit in enumerate(hits, start=1):
                chunk_id = hit.chunk.chunk_id
                chunks_by_id[chunk_id] = hit.chunk
                scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                    weight / (self._rrf_constant + rank)
                )

        fused = [
            RetrievalHit(chunk=chunks_by_id[chunk_id], score=score)
            for chunk_id, score in scores.items()
        ]
        fused.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
        return tuple(fused[:top_k])
