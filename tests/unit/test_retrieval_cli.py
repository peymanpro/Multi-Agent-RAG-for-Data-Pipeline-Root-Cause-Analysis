import json
from pathlib import Path

from pipeline_rca.retrieval.cli import main

ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS = ROOT / "data" / "runbooks"


def test_search_cli_emits_ranked_json_with_source_lines(capsys: object) -> None:
    assert main([str(RUNBOOKS), "schema contract required column", "--top-k", "2"]) == 0
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]

    assert output["document_count"] >= 5
    assert output["result_count"] <= 2
    if output["results"]:
        result = output["results"][0]
        assert result["source"].startswith("file:")
        assert result["start_line"] >= 1
        assert result["end_line"] >= result["start_line"]
        assert result["score"] > 0
