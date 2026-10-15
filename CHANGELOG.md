# Changelog

All notable changes to this project are documented here.

This project follows semantic versioning. Version tags use the `vMAJOR.MINOR.PATCH` form.

## [0.2.0] — 2026-10-15

### Added

- Typed incident, schema, dataset, task, lineage, evidence, finding, and investigation-report contracts.
- Deterministic diagnostics for schema drift, row-count mismatch, duplicate keys, null counts, stale inputs, task failure, lineage cycles, and downstream impact.
- An offline command-line interface for deterministic investigation.
- A versioned seven-case synthetic diagnostic benchmark with separate runtime inputs and evaluator truth.
- A reproducible BM25 runbook retriever with Markdown ingestion, heading-aware chunking, stable chunk IDs, and source-line provenance.
- A hand-judged document-level retrieval benchmark reporting Precision@k, Recall@k, Hit@k, MRR, and nDCG@k.
- Bounded specialist-agent orchestration with optional model-assisted hypothesis generation and counter-evidence review.
- Explicit evidence-reference verification, low-evidence demotion, step/evidence/prompt/model-call budgets, execution traces, and deterministic fallback behavior.
- An optional OpenAI-compatible embeddings adapter, cosine-similarity retrieval, and weighted reciprocal-rank fusion for hybrid retrieval.
- Offline evaluation comparing deterministic and multi-agent investigation behavior.
- Automated quality checks and an automated versioned GitHub Release workflow.
- Immutable release-tag handling that distinguishes absent tags from API lookup failures and refuses to move an existing version tag.

### Scope and limitations

- The standard investigation and CI paths are offline and do not require provider credentials.
- Hosted chat and embedding providers are opt-in. Hybrid retrieval currently builds its vector index in memory and does not persist an embedding cache.
- The included incident cases and runbook relevance judgments are synthetic or hand-authored regression fixtures, not a representative production benchmark.
- The deterministic verifier checks citation reference/provenance contracts; it does not prove semantic entailment of every generated claim.
- Model confidence values are explicitly uncalibrated. The system generates investigation hypotheses and does not automatically remediate pipelines.

### Validation

The release workflow runs Ruff, mypy, pytest, source/wheel builds, and package metadata checks before creating the release and attaching artifacts.
