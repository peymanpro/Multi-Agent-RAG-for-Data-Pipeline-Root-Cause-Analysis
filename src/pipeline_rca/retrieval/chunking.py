"""Structure-aware Markdown chunking with stable source line references."""

from __future__ import annotations

import hashlib
import re

from pipeline_rca.retrieval.models import Document, DocumentChunk

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split text near word boundaries; split very long tokens as a last resort."""
    segments: list[str] = []
    current = ""

    for word in text.split():
        pieces = (
            [word[index : index + max_chars] for index in range(0, len(word), max_chars)]
            if len(word) > max_chars
            else [word]
        )
        for piece in pieces:
            candidate = f"{current} {piece}".strip()
            if current and len(candidate) > max_chars:
                segments.append(current)
                current = piece
            else:
                current = candidate

    if current:
        segments.append(current)
    return segments


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"chunk-{digest[:20]}"


def chunk_document(document: Document, *, max_chars: int = 900) -> tuple[DocumentChunk, ...]:
    """Split Markdown into paragraph-oriented chunks while tracking heading hierarchy.

    Source line references are 1-based and inclusive. If a paragraph must be split due
    to size, each resulting chunk points back to the original paragraph's line span.
    Code fences are kept together across blank lines, while Markdown headings inside a
    fenced block are treated as code rather than as section headings.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")

    lines = document.content.splitlines()
    section_titles: list[str] = []
    blocks: list[tuple[int, int, tuple[str, ...], str]] = []
    paragraph_lines: list[tuple[int, str]] = []
    fence_char: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            text = "\n".join(line for _, line in paragraph_lines).strip()
            if text:
                blocks.append(
                    (
                        paragraph_lines[0][0],
                        paragraph_lines[-1][0],
                        tuple(section_titles),
                        text,
                    )
                )
        paragraph_lines = []

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_fence = stripped.startswith(chr(96) * 3) or stripped.startswith("~~~")
        if is_fence:
            marker = stripped[0]
            if fence_char is None:
                fence_char = marker
            elif marker == fence_char:
                fence_char = None
            paragraph_lines.append((line_number, line))
            continue

        heading = _HEADING.match(stripped) if fence_char is None else None
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            section_titles = section_titles[: level - 1]
            section_titles.append(title)
            continue

        if not stripped and fence_char is None:
            flush_paragraph()
            continue

        paragraph_lines.append((line_number, line))

    flush_paragraph()

    chunks: list[DocumentChunk] = []
    for start_line, end_line, section_path, text in blocks:
        for segment_index, segment in enumerate(_split_text(text, max_chars)):
            section_label = " > ".join(section_path)
            chunk_id = _stable_id(
                document.document_id,
                str(start_line),
                str(end_line),
                section_label,
                str(segment_index),
                segment,
            )
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    title=document.title,
                    source_uri=document.source_uri,
                    start_line=start_line,
                    end_line=end_line,
                    section_path=section_path,
                    text=segment,
                )
            )

    return tuple(chunks)
