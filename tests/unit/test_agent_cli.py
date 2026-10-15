import json
from pathlib import Path
from typing import Any

import pipeline_rca.agents.cli as investigation_cli
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
    capsys: Any,
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")

    assert main([str(invalid), "--no-runbooks"]) == 2
    assert "error" in capsys.readouterr().err



def test_default_runbooks_fall_back_to_packaged_resources(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)

    runbooks = investigation_cli._default_runbooks_dir()

    assert runbooks.is_dir()
    assert (runbooks / "schema-drift.md").is_file()
    assert len(list(runbooks.glob("*.md"))) >= 5
