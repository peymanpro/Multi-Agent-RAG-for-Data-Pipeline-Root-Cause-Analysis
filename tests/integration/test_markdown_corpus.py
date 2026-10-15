from pathlib import Path

from pipeline_rca.retrieval import MarkdownCorpus

ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS = ROOT / "data" / "runbooks"


def test_runbook_corpus_retrieves_source_addressable_evidence() -> None:
    corpus = MarkdownCorpus.from_directory(RUNBOOKS, max_chars=600)

    hits = corpus.search("duplicate business keys idempotent retry", top_k=3)

    assert len(corpus.documents) >= 5
    assert hits
    assert hits[0].chunk.source_uri.startswith("file:")
    evidence = hits[0].chunk.to_evidence_record()
    assert evidence.evidence_id == hits[0].chunk.chunk_id
    assert evidence.source == hits[0].chunk.source_uri
    assert evidence.locator.startswith("lines:")
    assert evidence.kind == "retrieved_document_chunk"


def test_corpus_can_retrieve_task_failure_and_lineage_runbook() -> None:
    corpus = MarkdownCorpus.from_directory(RUNBOOKS)
    hits = corpus.search("failed producer downstream lineage cycle", top_k=3)

    assert hits
    assert any("task-failure-and-lineage" in hit.chunk.source_uri for hit in hits)
