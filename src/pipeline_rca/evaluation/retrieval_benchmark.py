"""Document-level retrieval evaluation for the local operational runbook corpus."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from pipeline_rca.retrieval.corpus import MarkdownCorpus


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _safe_child(root: Path, relative: object, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the benchmark directory") from exc
    if not candidate.is_file():
        raise ValueError(f"{label} does not identify a file: {relative}")
    return candidate


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _ranked_unique_documents(
    corpus: MarkdownCorpus, query: str, *, candidate_limit: int
) -> list[str]:
    """Retrieve many chunks and preserve each document's highest-ranked occurrence."""
    hits = corpus.search(query, top_k=candidate_limit)
    ranked: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        document_id = hit.chunk.document_id
        if document_id not in seen:
            seen.add(document_id)
            ranked.append(document_id)
    return ranked


def _case_metrics(
    relevant: set[str], ranked: list[str], *, k: int
) -> dict[str, float | int | str | list[str]]:
    retrieved = ranked[:k]
    true_positives = len(relevant.intersection(retrieved))
    precision = true_positives / k
    recall = true_positives / len(relevant)
    first_relevant_rank = next(
        (index for index, document_id in enumerate(ranked, start=1) if document_id in relevant),
        None,
    )
    reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    dcg = sum(
        1.0 / math.log2(index + 2)
        for index, document_id in enumerate(retrieved)
        if document_id in relevant
    )
    ideal_relevant_count = min(k, len(relevant))
    ideal_dcg = sum(1.0 / math.log2(index + 2) for index in range(ideal_relevant_count))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return {
        "precision_at_k": precision,
        "recall_at_k": recall,
        "hit_at_k": float(true_positives > 0),
        "reciprocal_rank": reciprocal_rank,
        "ndcg_at_k": ndcg,
        "relevant_document_count": len(relevant),
        "retrieved_document_ids": retrieved,
    }


def run_retrieval_benchmark(
    benchmark_dir: str | Path,
    runbooks_dir: str | Path,
    *,
    k: int | None = None,
) -> dict[str, Any]:
    """Evaluate BM25 against explicit, document-level relevance judgments."""
    root = Path(benchmark_dir).resolve()
    manifest_path = _safe_child(root, "manifest.json", label="manifest")
    manifest = _read_object(manifest_path)
    unknown = sorted(set(manifest) - {"version", "k", "cases"})
    if unknown:
        raise ValueError(f"Manifest contains unsupported fields: {', '.join(unknown)}")
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Manifest version must be a non-empty string")
    cutoff = _positive_int(k if k is not None else manifest.get("k"), label="k")
    specs = manifest.get("cases")
    if not isinstance(specs, list) or not specs:
        raise ValueError("Manifest cases must be a non-empty array")

    corpus = MarkdownCorpus.from_directory(runbooks_dir)
    if not corpus.documents:
        raise ValueError("Runbook corpus is empty")
    available_documents = {document.document_id for document in corpus.documents}
    candidate_limit = max(100, cutoff * len(corpus.documents) * 4)

    case_results: list[dict[str, Any]] = []
    expected_queries: set[str] = set()
    expected_case_ids: set[str] = set()

    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise ValueError(f"cases[{index}] must be an object")
        if set(spec) != {"case_id", "query", "relevant_document_ids"}:
            raise ValueError(f"cases[{index}] has unsupported or missing fields")
        case_id = spec.get("case_id")
        query = spec.get("query")
        expected_ids = spec.get("relevant_document_ids")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"cases[{index}].case_id must be non-empty")
        if case_id in expected_case_ids:
            raise ValueError(f"Duplicate retrieval case_id: {case_id}")
        expected_case_ids.add(case_id)
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{case_id}.query must be non-empty")
        if query in expected_queries:
            raise ValueError(f"Duplicate retrieval query text: {query!r}")
        expected_queries.add(query)
        if (
            not isinstance(expected_ids, list)
            or not expected_ids
            or any(not isinstance(value, str) or not value for value in expected_ids)
        ):
            raise ValueError(f"{case_id}.relevant_document_ids must be a non-empty string array")
        if len(expected_ids) != len(set(expected_ids)):
            raise ValueError(f"{case_id}.relevant_document_ids must be unique")
        unknown_ids = sorted(set(expected_ids) - available_documents)
        if unknown_ids:
            raise ValueError(
                f"{case_id} references documents not present in the runbook corpus: "
                + ", ".join(unknown_ids)
            )

        ranked = _ranked_unique_documents(corpus, query, candidate_limit=candidate_limit)
        relevant = set(expected_ids)
        metrics = _case_metrics(relevant, ranked, k=cutoff)
        case_results.append(
            {
                "case_id": case_id,
                "query": query,
                "expected_relevant_document_ids": sorted(relevant),
                "ranked_document_ids": ranked[:cutoff],
                **metrics,
            }
        )

    metric_names = (
        "precision_at_k",
        "recall_at_k",
        "hit_at_k",
        "reciprocal_rank",
        "ndcg_at_k",
    )
    aggregate = {
        f"mean_{metric_name}": (
            sum(float(case[metric_name]) for case in case_results) / len(case_results)
        )
        for metric_name in metric_names
    }
    return {
        "benchmark_version": version,
        "retriever": "bm25_lexical",
        "ranking_unit": "unique_document",
        "k": cutoff,
        "query_count": len(case_results),
        "document_count": len(corpus.documents),
        "chunk_count": len(corpus.chunks),
        "aggregate_metrics": aggregate,
        "cases": case_results,
        "limitations": [
            "Relevance judgments are hand-authored for this repository's small runbook corpus.",
            (
                "Results evaluate lexical document retrieval only, not answer correctness "
                "or root-cause accuracy."
            ),
            "Duplicate chunks from a document count only once at their best observed rank.",
            (
                "The corpus and relevance manifest must be versioned together; changing "
                "runbooks can change rankings."
            ),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Evaluate local BM25 retrieval and print or save the JSON report."""
    parser = argparse.ArgumentParser(
        prog="pipeline-rca-evaluate-retrieval",
        description="Evaluate document-level BM25 relevance on the versioned runbook benchmark.",
    )
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=Path("data/retrieval-benchmark/v1"),
    )
    parser.add_argument("--runbooks-dir", type=Path, default=Path("data/runbooks"))
    parser.add_argument("--k", type=int, help="override the manifest's cutoff")
    parser.add_argument("--output", type=Path, help="optional path for the JSON report")
    args = parser.parse_args(argv)

    try:
        report = run_retrieval_benchmark(
            args.benchmark_dir, args.runbooks_dir, k=args.k
        )
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"pipeline-rca-evaluate-retrieval: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
