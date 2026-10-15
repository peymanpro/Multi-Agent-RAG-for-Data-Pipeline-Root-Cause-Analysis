"""Validate a release tag against the package version in pyproject.toml."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

_STABLE_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def validate_release_tag(tag: str, project_version: str) -> None:
    """Require a canonical stable version tag matching the project metadata."""
    if not _STABLE_TAG.fullmatch(tag):
        raise ValueError(
            "release tag must use stable semantic version form vMAJOR.MINOR.PATCH "
            "(for example, v1.2.3)"
        )

    tag_version = tag[1:]
    if tag_version != project_version:
        raise ValueError(
            f"tag version {tag_version!r} does not match pyproject.toml version "
            f"{project_version!r}"
        )


def read_project_version(pyproject_path: Path) -> str:
    """Read and validate the project version without importing project dependencies."""
    try:
        with pyproject_path.open("rb") as stream:
            metadata = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot read project metadata from {pyproject_path}: {exc}") from exc

    project = metadata.get("project")
    if not isinstance(project, dict):
        raise ValueError("pyproject.toml must define a [project] table")
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("pyproject.toml [project].version must be a non-empty string")
    return version


def main(argv: list[str] | None = None) -> int:
    """Validate the supplied tag against the current project's package version."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="stable release tag, such as v1.2.3")
    parser.add_argument(
        "--project-file",
        type=Path,
        default=Path("pyproject.toml"),
        help="path to project metadata (default: pyproject.toml)",
    )
    args = parser.parse_args(argv)

    try:
        version = read_project_version(args.project_file)
        validate_release_tag(args.tag, version)
    except ValueError as exc:
        print(f"release-version-check: error: {exc}", file=sys.stderr)
        return 2

    print(f"Validated release tag {args.tag} for package version {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
