import json
from pathlib import Path
from typing import Any

from pipeline_rca.agents.cli import main


ROOT = Path(__file__).resolve().parents[2]
CASE_PATH = ROOT / "examples" / "cases" / "schema-drift.json"


def test_investigation_cli_emits_traceable_report(
    capsys: Any,
) -> None:
    assert main([str(CASE_PATH), "--no-runbooks"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["case_id"] == "example-schema-drift-001"
    assert report["hypotheses"]
    assert report["trace"][-1]["agent"] == "evidence-verifier-agent"
    assert report["hypotheses"][0]["confidence_is_calibrated"] is False


def test_investigation_cli_returns_error_for_invalid_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")

    assert main([str(invalid), "--no-runbooks"]) == 2
    assert "error" in capsys.readouterr().err
