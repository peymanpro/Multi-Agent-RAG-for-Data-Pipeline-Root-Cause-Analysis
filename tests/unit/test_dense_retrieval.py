import math

import pytest

from pipeline_rca.retrieval.dense import DenseRetriever
from pipeline_rca.retrieval.models import DocumentChunk


class StubEmbeddingProvider:
    def __init__(self, query_vectors: dict[str, tuple[float, ...]]) -> None:
        self.query_vectors = query_vectors

    def embed_texts(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(self.query_vectors[text] for text in texts)


def _chunk(chunk_id: str, text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id=chunk_id,
        title=chunk_id,
        source_uri=f"file:{chunk_id}.md",
        start_line=1,
        end_line=1,
        section_path=(),
        text=text,
    )


def test_dense_retriever_ranks_by_cosine_similarity_and_stable_ties() -> None:
    chunks = (_chunk("schema", "Schema contract"), _chunk("duplicate", "Duplicate key"))
    provider = StubEmbeddingProvider({"customer schema": (1.0, 0.0)})
    retriever = DenseRetriever(chunks, ((4.0, 0.0), (0.0, 2.0)), provider)

    hits = retriever.search("customer schema", top_k=2)

    assert [hit.chunk.chunk_id for hit in hits] == ["schema", "duplicate"]
    assert hits[0].score == pytest.approx(1.0)
    assert hits[1].score == pytest.approx(0.0)
    assert retriever.dimension == 2


def test_dense_retriever_requires_one_finite_nonzero_vector_per_chunk() -> None:
    provider = StubEmbeddingProvider({})
    chunk = _chunk("one", "one chunk")

    with pytest.raises(ValueError, match="one embedding vector"):
        DenseRetriever((chunk,), (), provider)
    with pytest.raises(ValueError, match="all zeros"):
        DenseRetriever((chunk,), ((0.0, 0.0),), provider)
    with pytest.raises(ValueError, match="finite"):
        DenseRetriever((chunk,), ((math.nan, 1.0),), provider)
    with pytest.raises(ValueError, match="dimensions"):
        DenseRetriever((chunk,), ((1.0, 0.0, 2.0),), provider)


def test_dense_retriever_rejects_query_dimension_mismatch() -> None:
    chunk = _chunk("one", "one chunk")
    provider = StubEmbeddingProvider({"query": (1.0, 0.0, 0.0)})
    retriever = DenseRetriever((chunk,), ((1.0, 0.0),), provider)

    with pytest.raises(ValueError, match="dimensions"):
        retriever.search("query")


def test_empty_dense_index_and_blank_query_return_no_hits() -> None:
    provider = StubEmbeddingProvider({})
    retriever = DenseRetriever((), (), provider)

    assert retriever.search("anything") == ()
    assert retriever.search("   ") == ()
