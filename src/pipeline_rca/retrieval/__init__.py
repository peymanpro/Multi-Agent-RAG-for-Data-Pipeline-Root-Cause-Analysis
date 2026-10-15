"""Source-addressable document ingestion and lexical retrieval."""

from pipeline_rca.retrieval.chunking import chunk_document
from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.retrieval.ingestion import load_markdown_directory
from pipeline_rca.retrieval.lexical import BM25Retriever
from pipeline_rca.retrieval.models import Document, DocumentChunk, RetrievalHit

__all__ = [
    "BM25Retriever",
    "Document",
    "MarkdownCorpus",
    "DocumentChunk",
    "RetrievalHit",
    "chunk_document",
    "load_markdown_directory",
]
