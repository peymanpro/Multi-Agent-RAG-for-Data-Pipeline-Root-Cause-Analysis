"""Command-line interface for local runbook retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.retrieval.models import RetrievalHit


def hits_to_dict(hits: tuple[RetrievalHit, ...]) -> list[dict[str, Any]]:
    """Convert ranked hits into stable JSON-compatible records."""
    return [
        {
            "rank": rank,
            "score": round(hit.score, 8),
            "chunk_id": hit.chunk.chunk_id,
            "document_id": hit.chunk.document_id,
            "title": hit.chunk.title,
            "source": hit.chunk.source_uri,
            "start_line": hit.chunk.start_line,
            "end_line": hit.chunk.end_line,
            "section_path": list(hit.chunk.section_path),
            "text": hit.chunk.text,
        }
        for rank, hit in enumerate(hits, start=1)
    ]


def main(argv: list[str] | None = None) -> int:
    """Search a local Markdown corpus and print cited results as JSON."""
    parser = argparse.ArgumentParser(
        prog="pipeline-rca-search",
        description="Search local pipeline runbooks using deterministic BM25 retrieval.",
    )
    parser.add_argument("directory", type=Path, help="directory containing Markdown files")
    parser.add_argument("query", help="natural-language or keyword query")
    parser.add_argument("--top-k", type=int, default=5, help="maximum results (default: 5)")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=900,
        help="maximum characters per indexed chunk (default: 900)",
    )
    args = parser.parse_args(argv)

    try:
        corpus = MarkdownCorpus.from_directory(args.directory, max_chars=args.max_chars)
        hits = corpus.search(args.query, top_k=args.top_k)
    except (OSError, ValueError) as exc:
        print(f"pipeline-rca-search: error: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "query": args.query,
                "document_count": len(corpus.documents),
                "chunk_count": len(corpus.chunks),
                "result_count": len(hits),
                "results": hits_to_dict(hits),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
