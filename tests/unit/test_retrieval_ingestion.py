from pathlib import Path

import pytest

from pipeline_rca.retrieval.ingestion import load_markdown_directory


def test_directory_ingestion_is_sorted_and_uses_relative_source_uris(tmp_path: Path) -> None:
    (tmp_path / "zeta.md").write_text("# Zeta\n\nZeta runbook.", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "alpha.md").write_text(
        "# Alpha\n\nAlpha runbook.", encoding="utf-8"
    )
    (tmp_path / "ignored.txt").write_text("not Markdown", encoding="utf-8")

    documents = load_markdown_directory(tmp_path)

    assert [document.document_id for document in documents] == [
        "md:nested/alpha.md",
        "md:zeta.md",
    ]
    assert documents[0].title == "Alpha"
    assert documents[0].source_uri == "file:nested/alpha.md"


def test_missing_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_markdown_directory(tmp_path / "missing")


def test_empty_markdown_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_text("  \n", encoding="utf-8")
    assert load_markdown_directory(tmp_path) == ()
