"""Dependency-free BM25 retrieval with deterministic tie-breaking."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

from pipeline_rca.retrieval.chunking import chunk_document
from pipeline_rca.retrieval.models import Document, DocumentChunk, RetrievalHit

_TOKEN = re.compile(r"[\w]+", re.UNICODE)


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize words, identifiers, and underscore-separated technical terms."""
    return tuple(_TOKEN.findall(text.casefold()))


class BM25Retriever:
    """A small in-memory BM25 index suitable for runbooks and local evaluation."""

    def __init__(
        self,
        chunks: Iterable[DocumentChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")

        self._chunks = tuple(chunks)
        chunk_ids = [chunk.chunk_id for chunk in self._chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk_id values must be unique")

        self._k1 = k1
        self._b = b
        self._terms = tuple(Counter(tokenize(chunk.text)) for chunk in self._chunks)
        self._lengths = tuple(sum(terms.values()) for terms in self._terms)
        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )

        document_frequency: Counter[str] = Counter()
        for terms in self._terms:
            document_frequency.update(terms.keys())
        count = len(self._chunks)
        self._idf = {
            term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[Document],
        *,
        max_chars: int = 900,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> BM25Retriever:
        """Chunk documents and create an in-memory lexical index."""
        chunks = (
            chunk
            for document in documents
            for chunk in chunk_document(document, max_chars=max_chars)
        )
        return cls(chunks, k1=k1, b=b)

    @property
    def chunk_count(self) -> int:
        """Number of indexed chunks."""
        return len(self._chunks)

    @property
    def chunk_ids(self) -> tuple[str, ...]:
        """Stable identifiers in the index insertion order."""
        return tuple(chunk.chunk_id for chunk in self._chunks)

    def search(self, query: str, *, top_k: int = 5) -> tuple[RetrievalHit, ...]:
        """Return positive-scoring chunks ranked by BM25 then stable chunk ID."""
        if top_k < 1:
            raise ValueError("top_k must be positive")
        query_terms = tokenize(query)
        if not query_terms or not self._chunks:
            return ()

        hits: list[RetrievalHit] = []
        for chunk, terms, length in zip(
            self._chunks, self._terms, self._lengths, strict=True
        ):
            score = 0.0
            normalization = (
                self._k1 * (1 - self._b + self._b * length / self._average_length)
                if self._average_length
                else self._k1
            )
            for term in query_terms:
                frequency = terms.get(term, 0)
                if frequency == 0:
                    continue
                score += self._idf.get(term, 0.0) * (
                    frequency * (self._k1 + 1) / (frequency + normalization)
                )
            if score > 0:
                hits.append(RetrievalHit(chunk=chunk, score=score))

        hits.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
        return tuple(hits[:top_k])
