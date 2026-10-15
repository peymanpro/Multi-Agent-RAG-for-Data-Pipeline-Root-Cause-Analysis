import pytest

from pipeline_rca.retrieval.chunking import chunk_document
from pipeline_rca.retrieval.lexical import BM25Retriever
from pipeline_rca.retrieval.models import Document


def test_relevant_schema_runbook_ranks_above_unrelated_runbook() -> None:
    schema = Document(
        "schema",
        "Schema Runbook",
        "file:schema.md",
        "# Schema Drift\n\nA missing required column breaks a schema contract. Compare schemas.",
    )
    duplicate = Document(
        "duplicates",
        "Duplicates Runbook",
        "file:duplicates.md",
        "# Duplicates\n\nCheck duplicate business keys and idempotent loads.",
    )
    retriever = BM25Retriever.from_documents((schema, duplicate))

    hits = retriever.search("missing required column schema contract")

    assert hits
    assert hits[0].chunk.document_id == "schema"
    assert hits[0].score > 0


def test_search_is_deterministic_and_top_k_is_enforced() -> None:
    documents = (
        Document("a", "A", "file:a.md", "row count mismatch"),
        Document("b", "B", "file:b.md", "row count discrepancy"),
    )
    retriever = BM25Retriever.from_documents(documents)

    assert retriever.search("row count") == retriever.search("row count")
    assert len(retriever.search("row count", top_k=1)) == 1
    with pytest.raises(ValueError, match="positive"):
        retriever.search("row count", top_k=0)


def test_empty_query_and_nonmatching_query_return_no_hits() -> None:
    document = Document("a", "A", "file:a.md", "pipeline failure")
    retriever = BM25Retriever.from_documents((document,))

    assert retriever.search("   ") == ()
    assert retriever.search("quantum cryptography") == ()


def test_duplicate_chunk_identifiers_are_rejected() -> None:
    document = Document("a", "A", "file:a.md", "content")
    chunk = chunk_document(document)[0]
    with pytest.raises(ValueError, match="unique"):
        BM25Retriever((chunk, chunk))
