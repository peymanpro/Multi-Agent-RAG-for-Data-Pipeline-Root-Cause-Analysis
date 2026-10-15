# Evidence Retrieval

## Scope

The first retriever is an offline, dependency-free BM25 index over local Markdown runbooks. It provides a reproducible lexical baseline and makes source provenance explicit before adding dense embeddings or model-backed query expansion.

## Ingestion contract

- Only local Markdown files are loaded; the ingestion layer does not fetch remote URLs.
- Documents are visited in stable relative-path order.
- Empty Markdown files are skipped.
- The source URI uses a relative path (for example, `file:schema-drift.md`) rather than a machine-specific absolute path.
- Original document line numbers are retained in each chunk.

## Chunking

The Markdown chunker groups paragraphs under their current heading hierarchy. It recognizes nested headings, handles fenced code blocks without interpreting their contents as headings, and splits overlong paragraphs near word boundaries. Every chunk stores document identity, title, source URI, inclusive start/end line numbers, section path, text, and a stable content-derived ID.

When one long paragraph is split into several chunks, each chunk currently refers to the source paragraph's full line span. This is intentionally conservative: line citations remain valid, although their granularity may be coarser than a future token/line-aware chunker.

## BM25 ranking

The retriever uses classic BM25 term-frequency saturation and document-length normalization. Tokenization is case-folded and keeps underscores in technical identifiers. Results with zero lexical overlap are omitted. Equal scores are ordered by stable chunk ID, making ranking deterministic for a fixed corpus and configuration.

The first version does not perform semantic similarity, query rewriting, cross-encoder reranking, or hybrid Reciprocal Rank Fusion. These are separate experiments that must be compared with this lexical baseline.

## Provenance and citations

Every returned hit includes:
- a stable chunk ID;
- the source-relative path;
- the original inclusive line range;
- the section path;
- the ranking score and retrieved text.

A chunk can be converted into the shared `EvidenceRecord` contract. A future agent must pass the returned chunk/evidence identifier rather than inventing a source citation from generated prose.

## Command line

```bash
pipeline-rca-search data/runbooks "duplicate business keys idempotent retry" --top-k 3
```

The command prints JSON and does not need a provider key or network access. To use another local corpus, pass its directory as the first argument.

## Current limitations

- Retrieval is lexical and English-oriented rather than multilingual semantic search.
- The index is built in memory per process and is not persisted.
- The current evidence locator contains source lines and section path, but no immutable checksum is included in the printed report yet.
- Ranking relevance must be evaluated with labeled query/chunk examples; a plausible first result is not a benchmark claim.
- Runbooks in this repository are controlled project documents, not a substitute for an organization's approved operational procedures.
