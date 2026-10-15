import json
from pathlib import Path

import pytest

from pipeline_rca.cli import main
from pipeline_rca.serialization import incident_case_from_mapping


def test_runtime_case_rejects_evaluator_truth_fields() -> None:
    with pytest.raises(ValueError, match="evaluator-only"):
        incident_case_from_mapping(
            {
                "case_id": "leak-001",
                "question": "diagnose this",
                "ground_truth": {"fault_class": "schema_drift"},
            }
        )


def test_runtime_case_rejects_unknown_nested_fields() -> None:
    with pytest.raises(ValueError, match="unsupported field"):
        incident_case_from_mapping(
            {
                "case_id": "unknown-001",
                "question": "diagnose this",
                "tasks": [{"task_id": "load", "status": "failed", "oracle": "hidden"}],
            }
        )


def test_cli_emits_machine_readable_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "incident.json"
    input_path.write_text(
        json.dumps(
            {
                "case_id": "cli-001",
                "question": "Why did the task fail?",
                "tasks": [
                    {
                        "task_id": "load_orders",
                        "status": "failed",
                        "evidence_id": "task-log-1",
                    }
                ],
                "lineage": [
                    {"upstream": "load_orders", "downstream": "fact_orders"}
                ],
            }
        ),
        encoding="utf-8",
    )

    assert main([str(input_path)]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["case_id"] == "cli-001"
    assert report["findings"][0]["code"] == "PIPELINE_TASK_FAILED"
    assert report["affected_nodes"] == ["fact_orders"]


def test_cli_returns_nonzero_for_invalid_case(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "invalid.json"
    input_path.write_text('{"case_id": "missing-question"}', encoding="utf-8")

    assert main([str(input_path)]) == 2
    assert "question must be a non-empty string" in capsys.readouterr().err
