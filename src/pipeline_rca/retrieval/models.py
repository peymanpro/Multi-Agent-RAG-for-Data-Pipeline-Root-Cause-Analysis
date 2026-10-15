"""Immutable contracts for documents, chunks, and retrieval hits."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline_rca.models import EvidenceRecord


@dataclass(frozen=True, slots=True)
class Document:
    """A local document with a stable identifier and source locator."""

    document_id: str
    title: str
    source_uri: str
    content: str


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """A chunk that preserves document identity and original line provenance."""

    chunk_id: str
    document_id: str
    title: str
    source_uri: str
    start_line: int
    end_line: int
    section_path: tuple[str, ...]
    text: str

    def to_evidence_record(self, *, observed_at: str | None = None) -> EvidenceRecord:
        """Convert this chunk to the shared evidence contract."""
        section = " > ".join(self.section_path) if self.section_path else "document"
        return EvidenceRecord(
            evidence_id=self.chunk_id,
            source=self.source_uri,
            locator=f"lines:{self.start_line}-{self.end_line}#{section}",
            summary=self.text,
            kind="retrieved_document_chunk",
            observed_at=observed_at,
        )


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """A ranked candidate chunk and the retriever's raw relevance score."""

    chunk: DocumentChunk
    score: float
