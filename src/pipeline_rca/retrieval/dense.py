"""In-memory dense vector retrieval with validated cosine similarity."""

from __future__ import annotations

import math
from collections.abc import Sequence

from pipeline_rca.retrieval.embeddings import EmbeddingProvider
from pipeline_rca.retrieval.models import DocumentChunk, RetrievalHit


def _validated_vector(values: Sequence[float], *, dimension: int | None = None) -> tuple[float, ...]:
    if not values:
        raise ValueError("embedding vectors must not be empty")
    parsed: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("embedding vector values must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("embedding vector values must be finite")
        parsed.append(number)
    if dimension is not None and len(parsed) != dimension:
        raise ValueError("embedding vector dimensions do not match")
    norm = math.sqrt(sum(value * value for value in parsed))
    if norm == 0:
        raise ValueError("embedding vector cannot be all zeros")
    return tuple(value / norm for value in parsed)


class DenseRetriever:
    """Dense retrieval over precomputed document chunk embeddings."""

    def __init__(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
        provider: EmbeddingProvider,
    ) -> None:
        chunk_rows = tuple(chunks)
        vector_rows = tuple(vectors)
        if len(chunk_rows) != len(vector_rows):
            raise ValueError("one embedding vector is required per chunk")
        chunk_ids = [chunk.chunk_id for chunk in chunk_rows]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk_id values must be unique")

        dimension = len(vector_rows[0]) if vector_rows else None
        normalized: list[tuple[float, ...]] = []
        for vector in vector_rows:
            if dimension is None:
                raise ValueError("cannot infer dimensions from an empty vector collection")
            normalized.append(_validated_vector(vector, dimension=dimension))

        self._chunks = chunk_rows
        self._vectors = tuple(normalized)
        self._provider = provider
        self._dimension = dimension

    @classmethod
    def from_chunks(
        cls,
        chunks: Sequence[DocumentChunk],
        provider: EmbeddingProvider,
        *,
        batch_size: int = 64,
    ) -> DenseRetriever:
        """Embed chunks in bounded batches, retaining the original chunk order."""
        if isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError("batch_size must be positive")
        chunk_rows = tuple(chunks)
        vectors: list[tuple[float, ...]] = []
        for offset in range(0, len(chunk_rows), batch_size):
            batch = chunk_rows[offset : offset + batch_size]
            vectors.extend(provider.embed_texts([chunk.text for chunk in batch]))
        if not chunk_rows:
            return cls((), (), provider)
        return cls(chunk_rows, vectors, provider)

    @property
    def chunk_count(self) -> int:
        """Number of indexed chunks."""
        return len(self._chunks)

    @property
    def dimension(self) -> int:
        """Vector dimension, or zero for an empty index."""
        return self._dimension or 0

    def search(self, query: str, *, top_k: int = 5) -> tuple[RetrievalHit, ...]:
        """Return top cosine-similarity hits with stable tie-breaking."""
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if not query.strip() or not self._chunks:
            return ()
        raw_query = self._provider.embed_texts((query,))
        if len(raw_query) != 1:
            raise ValueError("embedding provider must return one vector for the query")
        query_vector = _validated_vector(raw_query[0], dimension=self._dimension)

        hits = [
            RetrievalHit(
                chunk=chunk,
                score=sum(left * right for left, right in zip(query_vector, vector, strict=True)),
            )
            for chunk, vector in zip(self._chunks, self._vectors, strict=True)
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
        return tuple(hits[:top_k])
