"""Convenience boundary for local Markdown runbook indexes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipeline_rca.retrieval.chunking import chunk_document
from pipeline_rca.retrieval.ingestion import load_markdown_directory
from pipeline_rca.retrieval.lexical import BM25Retriever
from pipeline_rca.retrieval.models import Document, DocumentChunk, RetrievalHit


@dataclass(frozen=True, slots=True)
class MarkdownCorpus:
    """A reproducible local corpus retaining original documents and indexed chunks."""

    documents: tuple[Document, ...]
    chunks: tuple[DocumentChunk, ...]
    retriever: BM25Retriever

    @classmethod
    def from_directory(
        cls, directory: str | Path, *, max_chars: int = 900
    ) -> MarkdownCorpus:
        """Load Markdown, chunk it, and construct an in-memory lexical index."""
        documents = load_markdown_directory(directory)
        chunks = tuple(
            chunk
            for document in documents
            for chunk in chunk_document(document, max_chars=max_chars)
        )
        retriever = BM25Retriever(chunks)
        return cls(documents=documents, chunks=chunks, retriever=retriever)

    def search(self, query: str, *, top_k: int = 5) -> tuple[RetrievalHit, ...]:
        """Search the corpus, preserving source paths and line references."""
        return self.retriever.search(query, top_k=top_k)
