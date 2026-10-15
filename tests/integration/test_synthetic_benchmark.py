import json
from pathlib import Path

import pytest

from pipeline_rca.evaluation.benchmark import run_benchmark


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "data" / "benchmark" / "v1"


def test_benchmark_v1_runs_all_cases_with_expected_diagnostics() -> None:
    report = run_benchmark(BENCHMARK)

    assert report["benchmark_version"] == "1.0.0"
    assert report["system"] == "deterministic_diagnostics_baseline"
    assert report["case_count"] == 7
    assert report["metrics"]["fault_class_detection"]["exact_match_rate"] == 1.0
    assert report["metrics"]["finding_code_detection"]["exact_match_rate"] == 1.0
    assert report["metrics"]["affected_node_detection"]["exact_match_rate"] == 1.0
    assert report["metrics"]["evidence_reference_validity"]["invalid_references"] == 0
    assert all(case["elapsed_seconds"] >= 0 for case in report["cases"])


def test_runtime_input_cannot_contain_ground_truth(tmp_path: Path) -> None:
    case_input = {
        "case_id": "leakage-001",
        "question": "Diagnose the failure",
        "ground_truth": {"expected_fault_classes": ["schema_drift"]},
    }
    truth = {
        "case_id": "leakage-001",
        "expected_fault_classes": [],
        "expected_finding_codes": [],
        "expected_affected_nodes": [],
    }
    (tmp_path / "case-input.json").write_text(json.dumps(case_input), encoding="utf-8")
    (tmp_path / "case-truth.json").write_text(json.dumps(truth), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "version": "test",
                "cases": [
                    {
                        "case_id": "leakage-001",
                        "input": "case-input.json",
                        "truth": "case-truth.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evaluator-only"):
        run_benchmark(tmp_path)


def test_manifest_rejects_paths_outside_benchmark_root(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "version": "test",
                "cases": [
                    {
                        "case_id": "unsafe-001",
                        "input": "../outside.json",
                        "truth": "truth.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes the benchmark directory"):
        run_benchmark(tmp_path)
