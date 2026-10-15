# Multi-Agent RAG for Data Pipeline Root Cause Analysis

> An evidence-grounded investigation system for diagnosing data-pipeline failures by combining deterministic diagnostics, retrieval, lineage, and bounded multi-agent reasoning.

[![CI](https://github.com/peymanpro/Multi-Agent-RAG-for-Data-Pipeline-Root-Cause-Analysis/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/peymanpro/Multi-Agent-RAG-for-Data-Pipeline-Root-Cause-Analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://www.python.org/)

## Project status

**Stage: deterministic diagnostics, synthetic benchmark v1, lexical retrieval, and bounded multi-agent investigation are implemented on the current feature branch; release automation is still pending.** The default path runs offline; model-assisted generation and review are explicit opt-ins. A feature is considered complete only after CI and its acceptance tests pass.

## Problem

When a data pipeline produces incomplete, stale, duplicated, or inconsistent output, an engineer often has to correlate evidence scattered across task logs, schema contracts, data-quality checks, lineage metadata, and operational runbooks. A text-only chatbot can summarize documents, but it cannot reliably establish a root cause without structured observations, testable hypotheses, and traceable evidence.

This project investigates the following question:

> Can a bounded multi-agent investigation system identify known data-pipeline failure causes more accurately or explainably than simpler RAG and single-agent baselines, while keeping latency, cost, and unsupported claims measurable?

## Intended workflow

1. Ingest structured incident observations and operational documents.
2. Run deterministic checks for schema drift, duplicate records, freshness, row-count anomalies, failed tasks, and broken dependencies.
3. Retrieve relevant runbooks and prior incidents with source provenance.
4. Generate a small, explicit set of competing hypotheses from the evidence.
5. Ask specialized investigators to gather evidence for or against each hypothesis.
6. Verify every material conclusion against source references and report uncertainty when evidence is insufficient.
7. Compare the multi-agent system against deterministic, RAG-only, and single-agent baselines on a reproducible benchmark.

The system is an **investigation assistant**, not an autonomous production remediation tool. It must not modify production data or execute destructive actions.

## Design principles

- **Evidence before prose:** conclusions must refer to concrete observations, document excerpts, or deterministic checks.
- **Deterministic where possible:** use ordinary code for arithmetic, schema comparison, rule checks, and graph traversal; use language models where interpretation or planning adds value.
- **Explicit uncertainty:** distinguish observed facts, hypotheses, and confirmed benchmark labels.
- **Bounded execution:** cap agent steps, retries, tool calls, time, and retrieved context.
- **Reproducibility:** version benchmark cases, record configuration, and preserve per-case results.
- **Baseline-first evaluation:** added complexity must earn its place through measured quality, latency, or cost.
- **Provider neutrality:** the core and offline test suite must work without model API keys or network access.
- **Least privilege:** evidence sources are read-only by default; external actions are out of scope.

## Planned architecture

```text
Incident / User Question
          |
          v
 Investigation API and Case Context
          |
          +------> Deterministic Diagnostics
          |          | schema / freshness / duplicates / row counts
          |          | task outcomes / lineage traversal
          |
          +------> Evidence Retrieval
          |          | lexical + semantic adapter boundary
          |          | ranked chunks + source provenance
          v
 Bounded Investigation Orchestrator
          |
          +------> Log Investigator
          +------> Contract / Schema Investigator
          +------> Lineage Investigator
          +------> Data-Quality Investigator
          +------> Runbook Retrieval Investigator
          |
          v
 Hypothesis & Evidence Verification
          |
          v
 Cited Incident Report + Evaluation Trace
```

This diagram represents the implemented investigation path. Dense semantic retrieval, a hosted HTTP API, and production integrations remain separate future work.

## Repository layout

```text
src/
  pipeline_rca/
    domain/          # typed incident, evidence, hypothesis, and report models
    diagnostics/     # deterministic, testable checks
    retrieval/       # document ingestion and retriever interfaces
    agents/           # specialized investigators and bounded orchestration
    evaluation/      # benchmark runner and metrics
    api/             # optional HTTP boundary
tests/
  unit/
  integration/
  contract/
data/
  benchmark/         # small, versioned, synthetic scenarios
docs/
  architecture.md
  benchmark-design.md
  roadmap.md
```

The repository now separates domain contracts, deterministic diagnostics, local retrieval, agent orchestration, benchmark evaluation, and integration/unit tests. Frameworks and hosted dependencies are added only behind explicit boundaries.

## Benchmark strategy

The project will use two complementary evidence sources:

- Public operational-log datasets and compatible metadata/artifacts where their terms and schemas permit.
- Small, deterministic synthetic incidents with known injected causes, negative controls, and explicit expected evidence.

Synthetic ground truth will be kept separate from the information available to the system during inference to prevent label leakage. Metrics should include top-k root-cause accuracy, evidence/citation validity, abstention quality on ambiguous cases, regression rate, latency, and estimated model/tool cost where available. Any published numeric result must be generated by a committed evaluation command and include its configuration.

## Technology direction

The initial implementation targets Python 3.12+, typed domain models, pytest, Ruff, and mypy. Storage, orchestration frameworks, embedding providers, and model APIs will sit behind narrow interfaces and will be added only when required by a tested capability. The initial core and tests should run offline.

## Development roadmap

- [x] **P0 — Charter and benchmark specification:** problem boundary, scenario schema, leakage controls, and evaluation protocol documented.
- [x] **P1 — Deterministic investigation core:** typed evidence, incident cases, schema/freshness/duplicate/row-count checks, lineage traversal, CLI, and unit tests.
- [x] **P2 — Reproducible synthetic benchmark v1:** seven versioned scenarios, separated runtime/evaluator files, metrics, CLI, and integration tests.
- [x] **P3 — Evidence retrieval baseline:** local Markdown ingestion, structure-aware chunking, deterministic BM25, stable source references, five runbooks, and tests.
- [x] **P4 — Bounded multi-agent workflow:** specialist diagnostics, optional model-based hypothesis generation and counter-evidence review, budgets, trace, fallback, and final citation-reference verification (pending merge/CI on the feature branch).
- [ ] **P5 — Evaluation and security:** RAG-only and single-agent comparisons, adversarial inputs, abstention tests, and regression gates.
- [ ] **P6 — API and operational quality:** API contracts, containerized local run, observability, and reproducible examples.
- [ ] **P5 — Evaluation and security:** retrieval relevance benchmark, agent-vs-baseline comparison, prompt-injection and abstention cases.
- [ ] **P6 — API and operational quality:** optional HTTP API, containerized local run, observability, and integration examples.
- [ ] **P7 — Release engineering:** automated version validation, package artifacts, release notes, and a verified GitHub Release.

## Run the current deterministic core

Install the package and development tools:

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
mypy
```

Run the offline schema-drift example:

```bash
pipeline-rca examples/cases/schema-drift.json
# or: python -m pipeline_rca examples/cases/schema-drift.json
```

Freshness checks intentionally require an explicit timezone-aware `--as-of` timestamp so results do not silently depend on the machine clock. The `pipeline-rca` command exposes the original deterministic diagnostic baseline; `pipeline-rca-investigate` runs the bounded specialist workflow.

## Run a bounded multi-agent investigation

Install the package and development tools:

    python -m pip install -e ".[dev]"
    pytest -q
    ruff check .
    mypy

Run offline; no model key or network is required:

    pipeline-rca-investigate examples/cases/schema-drift.json

Include deterministic freshness analysis with an explicit timestamp:

    pipeline-rca-investigate examples/cases/schema-drift.json --as-of 2026-10-15T10:05:00Z

Opt in to two bounded model calls (hypothesis generation and independent counter-evidence review):

    # configure RCA_API_KEY, RCA_MODEL, and optionally RCA_API_BASE_URL in the environment
    pipeline-rca-investigate examples/cases/schema-drift.json --with-model

The report separates incident observations from runbook context, includes agent trace and verification issues, and marks confidence as uncalibrated. Invalid model output falls back to deterministic synthesis; the final evidence-reference verifier runs even when model use is enabled. This is an investigation assistant, not an autonomous remediation tool. See [agent orchestration design](docs/agent-orchestration.md).

## Run the deterministic benchmark

Install the package and run the offline benchmark:

```bash
python -m pip install -e ".[dev]"
pipeline-rca-benchmark
```

The default benchmark directory is `data/benchmark/v1`. To save the machine-readable report:

```bash
pipeline-rca-benchmark data/benchmark/v1 --output artifacts/benchmark-v1.json
```

The runner evaluates the deterministic diagnostic baseline only. It reports fault-class detection, finding-code detection, affected-node detection, evidence-reference validity, and per-case runtime. These measurements do **not** claim language-model root-cause accuracy. See [benchmark design](docs/benchmark-design.md) for the case contract, metrics, leakage boundaries, and limitations.

## Search the local runbook corpus

The repository includes an offline lexical retriever over operational Markdown runbooks. It keeps document-relative source paths, line spans, and section headings on every result.

```bash
pipeline-rca-search data/runbooks "duplicate business keys idempotent retry" --top-k 3
```

The first retrieval baseline is BM25. It does not need a hosted embedding service or API key and is intended to provide a measurable lexical baseline before semantic/hybrid retrieval is considered. See [retrieval design](docs/retrieval.md).

## Dense and hybrid retrieval (optional)

The default remains offline BM25. To opt into hybrid retrieval, configure `RCA_API_KEY`, `RCA_EMBEDDING_MODEL`, and optionally `RCA_API_BASE_URL`, then run:

    pipeline-rca-investigate examples/cases/schema-drift.json --retrieval-mode hybrid

Hybrid retrieval combines BM25 and cosine-similarity ranking with reciprocal-rank fusion. The current hybrid corpus re-embeds local chunks on each construction and does not persist a vector cache, so provider cost/latency must be considered. See [hybrid retrieval design](docs/hybrid-retrieval.md).

## Architecture and benchmark contracts

- [Architecture](docs/architecture.md) — deterministic core, evidence flow, budgets, failure handling, and security constraints.
- [Agent orchestration](docs/agent-orchestration.md) — specialist roles, model boundary, counter-evidence review, trace, and limitations.
- [Retrieval design](docs/retrieval.md) — chunking, BM25, provenance, and retrieval limitations.
- [Hybrid retrieval](docs/hybrid-retrieval.md) — optional embeddings, cosine search, reciprocal-rank fusion, costs, and limits.
- [Benchmark design](docs/benchmark-design.md) — scenario contract, ground-truth separation, metrics, and release gate.
- [Contributing](CONTRIBUTING.md) — small changes, verification expectations, and review workflow.

## Contributing and quality gates

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow. Changes should be small, tested, and documented. Do not claim support for an integration, benchmark result, or production guarantee without an executable test or reproducible artifact.

## License

MIT. Dataset terms remain separate: each external dataset must retain its own license and attribution, and datasets with incompatible terms must not be redistributed through this repository.
