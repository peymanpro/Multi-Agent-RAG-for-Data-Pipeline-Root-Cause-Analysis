from pipeline_rca.retrieval.chunking import chunk_document
from pipeline_rca.retrieval.models import Document


def test_markdown_chunking_preserves_heading_path_and_line_numbers() -> None:
    document = Document(
        document_id="md:guide.md",
        title="Guide",
        source_uri="file:guide.md",
        content="# Root\n\nIntro text.\n\n## Schema Drift\n\nCompare the source schema.\nCheck required fields.",
    )

    chunks = chunk_document(document, max_chars=200)

    assert [chunk.text for chunk in chunks] == [
        "Intro text.",
        "Compare the source schema.\nCheck required fields.",
    ]
    assert chunks[0].section_path == ("Root",)
    assert chunks[0].start_line == 3
    assert chunks[0].end_line == 3
    assert chunks[1].section_path == ("Root", "Schema Drift")
    assert chunks[1].start_line == 7
    assert chunks[1].end_line == 8
    assert chunks[1].source_uri == "file:guide.md"


def test_long_paragraph_is_split_under_character_limit_and_ids_are_stable() -> None:
    document = Document(
        document_id="md:long.md",
        title="Long",
        source_uri="file:long.md",
        content="# Long\n\n" + "diagnostic " * 80,
    )

    first = chunk_document(document, max_chars=73)
    second = chunk_document(document, max_chars=73)

    assert len(first) > 1
    assert all(len(chunk.text) <= 73 for chunk in first)
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.start_line == 3 and chunk.end_line == 3 for chunk in first)


def test_headings_inside_fenced_code_are_not_treated_as_sections() -> None:
    fence = chr(96) * 3
    document = Document(
        document_id="md:code.md",
        title="Code",
        source_uri="file:code.md",
        content=(
            "# Root\n\n" + fence + "md\n## Not a heading\n\ncode body\n"
            + fence + "\n\nReal paragraph."
        ),
    )

    chunks = chunk_document(document)

    code_chunk = next(chunk for chunk in chunks if "Not a heading" in chunk.text)
    real_chunk = next(chunk for chunk in chunks if "Real paragraph" in chunk.text)
    assert code_chunk.section_path == ("Root",)
    assert real_chunk.section_path == ("Root",)


def test_invalid_chunk_size_is_rejected() -> None:
    document = Document("id", "title", "source", "body")

    try:
        chunk_document(document, max_chars=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("Expected a ValueError for a zero chunk size")
