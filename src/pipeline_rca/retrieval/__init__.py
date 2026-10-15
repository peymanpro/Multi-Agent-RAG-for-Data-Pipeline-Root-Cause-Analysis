"""Source-addressable lexical and hybrid retrieval primitives."""

from pipeline_rca.retrieval.chunking import chunk_document
from pipeline_rca.retrieval.corpus import MarkdownCorpus, SearchableCorpus
from pipeline_rca.retrieval.dense import DenseRetriever
from pipeline_rca.retrieval.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    OpenAICompatibleEmbeddingProvider,
)
from pipeline_rca.retrieval.hybrid import HybridRetriever
from pipeline_rca.retrieval.hybrid_corpus import HybridMarkdownCorpus
from pipeline_rca.retrieval.ingestion import load_markdown_directory
from pipeline_rca.retrieval.lexical import BM25Retriever
from pipeline_rca.retrieval.models import Document, DocumentChunk, RetrievalHit

__all__ = [
    "BM25Retriever",
    "DenseRetriever",
    "Document",
    "DocumentChunk",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "HybridMarkdownCorpus",
    "HybridRetriever",
    "MarkdownCorpus",
    "OpenAICompatibleEmbeddingProvider",
    "RetrievalHit",
    "SearchableCorpus",
    "chunk_document",
    "load_markdown_directory",
]
