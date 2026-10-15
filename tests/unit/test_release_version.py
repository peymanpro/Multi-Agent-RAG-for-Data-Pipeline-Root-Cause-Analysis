import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_release_version.py"


def _run_check(tmp_path: Path, *, tag: str, version: str) -> subprocess.CompletedProcess[str]:
    project_file = tmp_path / "pyproject.toml"
    project_file.write_text(
        f'[project]\nname = "release-check-fixture"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            tag,
            "--project-file",
            str(project_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_tag_must_match_project_version(tmp_path: Path) -> None:
    result = _run_check(tmp_path, tag="v1.2.3", version="1.2.3")

    assert result.returncode == 0
    assert "Validated release tag v1.2.3" in result.stdout


def test_release_tag_rejects_version_mismatch(tmp_path: Path) -> None:
    result = _run_check(tmp_path, tag="v1.2.4", version="1.2.3")

    assert result.returncode == 2
    assert "does not match pyproject.toml version" in result.stderr


@pytest.mark.parametrize("tag", ["1.2.3", "release-1.2.3", "v1.2", "v01.2.3", "v1.2.3-rc.1"])
def test_release_tag_accepts_only_canonical_stable_versions(
    tmp_path: Path, tag: str
) -> None:
    result = _run_check(tmp_path, tag=tag, version="1.2.3")

    assert result.returncode == 2
    assert "stable semantic version form" in result.stderr


def test_release_tag_requires_project_version_metadata(tmp_path: Path) -> None:
    project_file = tmp_path / "pyproject.toml"
    project_file.write_text('[tool.example]\nname = "missing-project-table"\n', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "v1.2.3",
            "--project-file",
            str(project_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "must define a [project] table" in result.stderr
