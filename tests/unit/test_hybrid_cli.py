from pathlib import Path
from typing import Any

import pipeline_rca.agents.cli as investigation_cli
from pipeline_rca.retrieval.corpus import MarkdownCorpus

ROOT = Path(__file__).resolve().parents[2]
CASE_PATH = ROOT / "examples" / "cases" / "schema-drift.json"
RUNBOOKS = ROOT / "data" / "runbooks"


def test_hybrid_cli_builds_an_injected_hybrid_corpus_without_network(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    class StubProvider:
        pass

    monkeypatch.setattr(
        investigation_cli.OpenAICompatibleEmbeddingProvider,
        "from_env",
        lambda **kwargs: StubProvider(),
    )
    monkeypatch.setattr(
        investigation_cli.HybridMarkdownCorpus,
        "from_directory",
        lambda directory, provider: MarkdownCorpus.from_directory(directory),
    )

    exit_code = investigation_cli.main(
        [str(CASE_PATH), "--retrieval-mode", "hybrid", "--runbooks", str(RUNBOOKS)]
    )

    assert exit_code == 0
    report = capsys.readouterr().out
    assert '"case_id": "example-schema-drift-001"' in report


def test_hybrid_mode_cannot_be_combined_with_disabled_runbooks(
    capsys: Any,
) -> None:
    exit_code = investigation_cli.main(
        [str(CASE_PATH), "--retrieval-mode", "hybrid", "--no-runbooks"]
    )

    assert exit_code == 2
    assert "--retrieval-mode hybrid cannot be combined" in capsys.readouterr().err
