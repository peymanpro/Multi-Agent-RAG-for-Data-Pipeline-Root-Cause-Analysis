import pytest

from pipeline_rca.retrieval.dense import DenseRetriever
from pipeline_rca.retrieval.hybrid import HybridRetriever
from pipeline_rca.retrieval.lexical import BM25Retriever
from pipeline_rca.retrieval.models import DocumentChunk


class StubEmbeddingProvider:
    def __init__(self, vectors: dict[str, tuple[float, ...]]) -> None:
        self.vectors = vectors

    def embed_texts(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(self.vectors[text] for text in texts)


def _chunk(chunk_id: str, content: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id=chunk_id,
        title=chunk_id,
        source_uri=f"file:{chunk_id}.md",
        start_line=1,
        end_line=1,
        section_path=(),
        text=content,
    )


def test_hybrid_retriever_fuses_rankings_and_preserves_provenance() -> None:
    lexical_chunks = (
        _chunk("schema", "schema customer contract missing required column"),
        _chunk("duplicates", "duplicate business key retry idempotent load"),
    )
    lexical = BM25Retriever(lexical_chunks)
    dense = DenseRetriever(
        lexical_chunks,
        ((1.0, 0.0), (0.0, 1.0)),
        StubEmbeddingProvider({"customer identifier": (0.9, 0.1)}),
    )
    retriever = HybridRetriever(lexical, dense, rrf_constant=10)

    hits = retriever.search("customer identifier", top_k=2)

    assert [hit.chunk.chunk_id for hit in hits] == ["schema", "duplicates"]
    assert hits[0].score > hits[1].score
    assert hits[0].chunk.source_uri == "file:schema.md"


def test_hybrid_retriever_rejects_mismatched_indices_and_bad_weights() -> None:
    lexical_chunk = _chunk("lexical", "schema contract")
    dense_chunk = _chunk("dense", "schema contract")
    lexical = BM25Retriever((lexical_chunk,))
    dense = DenseRetriever(
        (dense_chunk,),
        ((1.0, 0.0),),
        StubEmbeddingProvider({"schema": (1.0, 0.0)}),
    )

    with pytest.raises(ValueError, match="same chunk identifiers"):
        HybridRetriever(lexical, dense)
    with pytest.raises(ValueError, match="dense_weight"):
        HybridRetriever(lexical, DenseRetriever(
            (lexical_chunk,),
            ((1.0, 0.0),),
            StubEmbeddingProvider({"schema": (1.0, 0.0)}),
        ), dense_weight=0)


def test_hybrid_retriever_handles_empty_indexes_and_validates_top_k() -> None:
    provider = StubEmbeddingProvider({})
    retriever = HybridRetriever(
        BM25Retriever(()),
        DenseRetriever((), (), provider),
    )

    assert retriever.search("query") == ()
    with pytest.raises(ValueError, match="positive"):
        retriever.search("query", top_k=0)
