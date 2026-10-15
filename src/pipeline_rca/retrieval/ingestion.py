"""Local, offline Markdown document ingestion."""

from __future__ import annotations

from pathlib import Path

from pipeline_rca.retrieval.models import Document


def load_markdown_directory(directory: str | Path) -> tuple[Document, ...]:
    """Load Markdown files below a directory in stable relative-path order.

    The ingestion layer does not fetch URLs or follow symlinked directory entries.
    Source URIs are repository-relative paths rather than machine-specific absolute paths.
    """
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"Markdown directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Expected a directory of Markdown files: {root}")

    root_resolved = root.resolve()
    documents: list[Document] = []
    candidates = sorted(
        (path for path in root.rglob("*.md") if path.is_file() and not path.is_symlink()),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )

    for path in candidates:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root_resolved).as_posix()
        except ValueError as exc:
            raise ValueError(f"Document path escapes ingestion root: {path}") from exc

        content = path.read_text(encoding="utf-8")
        if not content.strip():
            continue

        title = next(
            (
                line.lstrip("#").strip()
                for line in content.splitlines()
                if line.startswith("#") and line.lstrip("#").strip()
            ),
            path.stem.replace("-", " ").replace("_", " ").title(),
        )
        documents.append(
            Document(
                document_id=f"md:{relative}",
                title=title,
                source_uri=f"file:{relative}",
                content=content,
            )
        )

    return tuple(documents)
