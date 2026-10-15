from pathlib import Path

from pipeline_rca.retrieval.hybrid_corpus import HybridMarkdownCorpus


ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS = ROOT / "data" / "runbooks"


class RunbookEmbeddingStub:
    def embed_texts(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        vectors = []
        for text in texts:
            lower = text.casefold()
            if "schema" in lower or "customer" in lower:
                vectors.append((1.0, 0.0, 0.0))
            elif "duplicate" in lower or "idempotent" in lower:
                vectors.append((0.0, 1.0, 0.0))
            else:
                vectors.append((0.0, 0.0, 1.0))
        return tuple(vectors)


def test_hybrid_corpus_keeps_local_sources_and_ranks_related_chunks() -> None:
    corpus = HybridMarkdownCorpus.from_directory(
        RUNBOOKS,
        RunbookEmbeddingStub(),
        max_chars=700,
    )

    hits = corpus.search("customer schema contract", top_k=5)

    assert len(corpus.documents) == 5
    assert corpus.chunks
    assert hits
    assert hits[0].chunk.source_uri.startswith("file:")
    evidence = hits[0].chunk.to_evidence_record()
    assert evidence.evidence_id == hits[0].chunk.chunk_id
    assert "lines:" in evidence.locator
