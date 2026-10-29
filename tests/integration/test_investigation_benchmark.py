import json
from pathlib import Path

import pytest

from pipeline_rca.evaluation.investigation_benchmark import run_investigation_benchmark

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "data" / "benchmark" / "v1"
RUNBOOKS = ROOT / "data" / "runbooks"


def test_investigation_benchmark_compares_offline_baselines() -> None:
    report = run_investigation_benchmark(BENCHMARK, RUNBOOKS)

    assert report["benchmark_version"] == "1.1.0"
    assert report["runtime_mode"] == "offline_deterministic_multi_agent"
    assert report["case_count"] == 9
    assert report["root_cause"]["baseline"]["top_1_accuracy_on_positive_cases"] == 1.0
    assert report["root_cause"]["multiagent"]["top_1_accuracy_on_positive_cases"] == 1.0
    assert report["root_cause"]["multiagent"]["clean_case_abstention_rate"] == 1.0
    assert (
        report["multiagent_evidence_reference_integrity"]["validity_rate"] == 1.0
    )
    assert (
        report["multiagent_evidence_reference_integrity"]["invalid_references"] == 0
    )
    assert all(case["baseline_seconds"] >= 0 for case in report["cases"])
    assert all(case["multiagent_seconds"] >= 0 for case in report["cases"])

    cases = {case["case_id"]: case for case in report["cases"]}
    compound = cases["compound-failure-001"]
    assert set(compound["expected_fault_classes"]) == {
        "duplicate_records",
        "schema_drift",
    }
    assert set(compound["multiagent_ranked_fault_classes"]) >= {
        "duplicate_records",
        "schema_drift",
    }
    insufficient = cases["insufficient-evidence-001"]
    assert insufficient["expected_fault_classes"] == []
    assert insufficient["multiagent_ranked_fault_classes"] == []
    assert insufficient["abstained"] is True


def test_runtime_input_cannot_smuggle_evaluator_labels(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "version": "test",
                "cases": [
                    {
                        "case_id": "leak-001",
                        "input": "input.json",
                        "truth": "truth.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "input.json").write_text(
        json.dumps(
            {
                "case_id": "leak-001",
                "question": "Investigate",
                "ground_truth": {"expected_fault_classes": ["schema_drift"]},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "truth.json").write_text(
        json.dumps(
            {
                "case_id": "leak-001",
                "expected_fault_classes": [],
                "expected_finding_codes": [],
                "expected_affected_nodes": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evaluator-only"):
        run_investigation_benchmark(tmp_path, RUNBOOKS)


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
        run_investigation_benchmark(tmp_path, RUNBOOKS)



class EmptyHypothesisModel:
    """Return valid empty hypotheses to exercise optional model-evaluation plumbing."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1_000,
    ) -> str:
        assert system_prompt
        assert user_prompt
        assert temperature == 0.0
        assert max_tokens > 0
        self.calls += 1
        return '{"hypotheses": []}'


def test_investigation_benchmark_supports_optional_model_adapter() -> None:
    model = EmptyHypothesisModel()
    report = run_investigation_benchmark(
        BENCHMARK,
        RUNBOOKS,
        model=model,
        model_name="test-chat-model",
    )

    assert report["runtime_mode"] == "model_assisted_multi_agent"
    evaluation = report["model_evaluation"]
    assert evaluation["enabled"] is True
    assert evaluation["model_name"] == "test-chat-model"
    assert evaluation["total_model_calls"] == model.calls
    assert evaluation["total_model_calls"] > 0
    assert evaluation["provider_usage_available"] is False
    assert evaluation["provider_cost_usd"] is None
    assert "usage metadata" in evaluation["cost_note"]
    assert all("model_calls" in case for case in report["cases"])
