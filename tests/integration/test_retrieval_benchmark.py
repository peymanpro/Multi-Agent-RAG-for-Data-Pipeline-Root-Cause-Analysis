import json
from pathlib import Path

import pytest

from pipeline_rca.evaluation.retrieval_benchmark import run_retrieval_benchmark

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "data" / "retrieval-benchmark" / "v1"
RUNBOOKS = ROOT / "data" / "runbooks"


def test_retrieval_benchmark_reports_reproducible_document_level_metrics() -> None:
    report = run_retrieval_benchmark(BENCHMARK, RUNBOOKS)

    assert report["benchmark_version"] == "1.0.0"
    assert report["retriever"] == "bm25_lexical"
    assert report["ranking_unit"] == "unique_document"
    assert report["k"] == 3
    assert report["query_count"] == 10
    assert report["document_count"] == 5
    metrics = report["aggregate_metrics"]
    assert metrics["mean_hit_at_k"] >= 0.9
    assert metrics["mean_recall_at_k"] >= 0.9
    assert 0.0 <= metrics["mean_precision_at_k"] <= 1.0
    assert 0.0 <= metrics["mean_reciprocal_rank"] <= 1.0
    assert 0.0 <= metrics["mean_ndcg_at_k"] <= 1.0
    for case in report["cases"]:
        assert case["retrieved_document_ids"]
        assert case["retrieved_document_ids"][0] in {
            "md:schema-drift.md",
            "md:duplicate-records.md",
            "md:stale-input.md",
            "md:row-count-mismatch.md",
            "md:task-failure-and-lineage.md",
        }
        assert case["relevant_document_count"] == 1


def test_retrieval_benchmark_rejects_labels_outside_the_corpus(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "version": "test",
                "k": 3,
                "cases": [
                    {
                        "case_id": "unknown-doc-001",
                        "query": "schema drift",
                        "relevant_document_ids": ["md:not-in-corpus.md"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not present in the runbook corpus"):
        run_retrieval_benchmark(tmp_path, RUNBOOKS)


def test_retrieval_benchmark_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    manifest = {
        "version": "test",
        "k": 1,
        "cases": [
            {
                "case_id": "duplicate",
                "query": "missing required column",
                "relevant_document_ids": ["md:schema-drift.md"],
            },
            {
                "case_id": "duplicate",
                "query": "duplicate key retry",
                "relevant_document_ids": ["md:duplicate-records.md"],
            },
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate retrieval case_id"):
        run_retrieval_benchmark(tmp_path, RUNBOOKS)
