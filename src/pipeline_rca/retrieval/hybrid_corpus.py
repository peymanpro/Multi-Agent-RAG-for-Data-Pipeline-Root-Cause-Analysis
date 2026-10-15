"""Local Markdown corpus composed with lexical+dense hybrid retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipeline_rca.retrieval.chunking import chunk_document
from pipeline_rca.retrieval.dense import DenseRetriever
from pipeline_rca.retrieval.embeddings import EmbeddingProvider
from pipeline_rca.retrieval.hybrid import HybridRetriever
from pipeline_rca.retrieval.ingestion import load_markdown_directory
from pipeline_rca.retrieval.lexical import BM25Retriever
from pipeline_rca.retrieval.models import Document, DocumentChunk, RetrievalHit


@dataclass(frozen=True, slots=True)
class HybridMarkdownCorpus:
    """Hybrid runbook corpus; document embeddings are prepared at construction time."""

    documents: tuple[Document, ...]
    chunks: tuple[DocumentChunk, ...]
    retriever: HybridRetriever

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        provider: EmbeddingProvider,
        *,
        max_chars: int = 900,
        embedding_batch_size: int = 64,
        rrf_constant: int = 60,
        lexical_weight: float = 1.0,
        dense_weight: float = 1.0,
    ) -> HybridMarkdownCorpus:
        """Load and chunk Markdown, embed chunks, and build the hybrid index."""
        documents = load_markdown_directory(directory)
        chunks = tuple(
            chunk
            for document in documents
            for chunk in chunk_document(document, max_chars=max_chars)
        )
        lexical = BM25Retriever(chunks)
        dense = DenseRetriever.from_chunks(
            chunks, provider, batch_size=embedding_batch_size
        )
        retriever = HybridRetriever(
            lexical,
            dense,
            rrf_constant=rrf_constant,
            lexical_weight=lexical_weight,
            dense_weight=dense_weight,
        )
        return cls(documents=documents, chunks=chunks, retriever=retriever)

    def search(self, query: str, *, top_k: int = 5) -> tuple[RetrievalHit, ...]:
        """Retrieve hybrid-ranked chunks while preserving source provenance."""
        return self.retriever.search(query, top_k=top_k)
