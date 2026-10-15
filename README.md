# Multi-Agent RAG for Data Pipeline Root Cause Analysis

> An evidence-grounded investigation system for diagnosing data-pipeline failures by combining deterministic diagnostics, retrieval, lineage, and bounded multi-agent reasoning.

[![CI](https://github.com/peymanpro/Multi-Agent-RAG-for-Data-Pipeline-Root-Cause-Analysis/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/peymanpro/Multi-Agent-RAG-for-Data-Pipeline-Root-Cause-Analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://www.python.org/)

## Project status

**P8b implementation complete; v0.4.0 is the next automated release candidate.** The release is not considered published until its GitHub Actions release workflow succeeds. The implementation now includes per-user Bearer tokens with scope checks (static tokens, not OIDC/SSO), redacted JSON-line request telemetry, pre-parse body limits, Redis-backed fixed-window rate limiting shared across API workers, and read-only Airflow REST, dbt artifact, and OpenLineage event connectors. Production mode fails closed without per-user identity configuration and Redis. The core remains offline-first; hosted chat and hybrid embeddings are opt-in. No automatic remediation or PyPI publication is included.

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

This diagram represents the implemented investigation path. The API is optional and read-only; hybrid retrieval requires an explicitly configured embedding provider. Production-system integrations and automated remediation remain out of scope.

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

## Read-only production data connectors

The connector package normalizes Airflow REST task runs, dbt `manifest.json`/`run_results.json`, and OpenLineage JSON Lines exports into typed evidence, task observations, schemas, and lineage edges. HTTP connectors are GET-only, timeout-bounded, TLS-enforcing outside loopback, redirect-disabled, and response-size-limited. The adapters never trigger production jobs or mutate source data.

See [Read-only Production Data Connectors](docs/connectors.md) for setup examples, credentials, supported fields, and safety boundaries.

## Production API hardening

The API supports separate static Bearer credentials per subject with explicit scopes, structured JSON-line request telemetry, request correlation IDs, pre-parse request-byte limits, and fixed-window rate limiting. The development limiter is process-local; production mode requires a shared Redis backend so multiple workers and replicas consume the same counters. Per-user credentials are supplied through protected runtime configuration and are never committed to the repository.

- [API authentication and telemetry](docs/api.md)
- [Distributed rate limiting](docs/rate-limiting.md)
- [Read-only connector contracts](docs/connectors.md)

These are service-level controls, not an OIDC/SSO implementation or a production secret-management system. Deploy behind TLS and an authenticated gateway, use least-privilege source credentials, and keep external source access read-only.

## Technology direction

The initial implementation targets Python 3.12+, typed domain models, pytest, Ruff, and mypy. Storage, orchestration frameworks, embedding providers, and model APIs will sit behind narrow interfaces and will be added only when required by a tested capability. The initial core and tests should run offline.

## Development roadmap

- [x] **P0 — Problem and evaluation contract:** incident schema, data boundaries, benchmark protocol, and leakage controls.
- [x] **P1 — Deterministic investigation core:** typed cases/evidence, data-quality checks, lineage traversal, CLI, and unit tests.
- [x] **P2 — Synthetic diagnostic benchmark:** versioned scenarios with separate runtime inputs and evaluator-only truth.
- [x] **P3 — Evidence retrieval:** Markdown ingestion, stable chunks, source-line provenance, BM25, and hand-judged retrieval relevance.
- [x] **P4 — Bounded multi-agent investigation:** specialist roles, budgets, trace, model opt-in, deterministic fallback, and evidence-reference verification.
- [x] **P5 — Evaluation:** deterministic-versus-agent benchmark, retrieval metrics, abstention-related cases, and reproducible per-case reports.
- [x] **P6 — Optional API and local operations:** bounded read-only FastAPI endpoint, health/readiness checks, Docker image, Compose, and API contract tests.
- [x] **P7 — Automated GitHub Releases:** version/tag validation, source/wheel builds, metadata checks, installed-wheel smoke tests, three benchmark artifacts, SHA-256 checksums, and immutable published tags.
- [x] **P8a — Initial security and cache hardening:** prompt-injection regression tests, pre-parse HTTP body limits, persistent SQLite embedding cache with opaque provider namespaces, and optional shared-token Bearer authentication.
- [x] **P8b — Production hardening:** per-user token authentication and scope-based authorization, structured/redacted JSON telemetry, pre-parse body limits, Redis-backed multi-worker rate limiting, and tested read-only Airflow/dbt/OpenLineage connectors. Static tokens are not a substitute for OIDC/SSO, and connectors do not execute SQL or mutate source systems.

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

## Evaluate retrieval quality

Run the versioned relevance benchmark against the local runbooks:

    pipeline-rca-evaluate-retrieval

The benchmark reports document-level Precision@k, Recall@k, Hit@k, MRR, and nDCG@k. It uses hand-judged relevance for the five included runbooks and makes no claim about production-scale relevance or final answer correctness.

## Evaluate end-to-end investigation

Run the offline comparison between the original deterministic diagnostics baseline and the multi-agent orchestrator:

    pipeline-rca-evaluate-investigation

The report includes root-cause class Top-1/Top-k metrics, MRR, clean-case abstention, finding-code detection, affected-node detection, evidence-reference integrity, per-case timings, and exact labels for each synthetic case. Both execution paths run before each evaluator truth file is read. Results do not involve an LLM and do not establish production root-cause accuracy.

## Dense and hybrid retrieval (optional)

The default remains offline BM25. To enable hybrid retrieval, configure `RCA_API_KEY`, `RCA_EMBEDDING_MODEL`, and optionally `RCA_API_BASE_URL`, `RCA_EMBEDDING_CACHE`, and `RCA_EMBEDDING_CACHE_NAMESPACE`, then run:

```bash
pipeline-rca-investigate examples/cases/schema-drift.json --retrieval-mode hybrid
```

Hybrid retrieval combines BM25 and cosine-similarity ranking with reciprocal-rank fusion (RRF). It caches vectors in SQLite by exact text and an opaque provider/model namespace, avoiding repeat embeddings for unchanged runbook chunks. The in-memory dense index is still rebuilt on each invocation; uncached input and query embeddings can incur provider cost. The CI path uses test doubles and does not require API credentials. See [hybrid retrieval design](docs/hybrid-retrieval.md).

## Architecture and benchmark contracts

- [Architecture](docs/architecture.md) — deterministic core, evidence flow, budgets, failure handling, and security constraints.
- [Agent orchestration](docs/agent-orchestration.md) — specialist roles, model boundary, counter-evidence review, trace, and limitations.
- [Retrieval design](docs/retrieval.md) — chunking, BM25, provenance, and retrieval limitations.
- [Hybrid retrieval](docs/hybrid-retrieval.md) — optional embeddings, cosine similarity, RRF, and provider constraints.
- [Read-only API](docs/api.md) — HTTP contracts, bounds, and authentication.
- [Distributed rate limiting](docs/rate-limiting.md) — Redis-backed quotas across workers.
- [Data connectors](docs/connectors.md) — Airflow REST, dbt artifacts, and OpenLineage exports.
- [Benchmark design](docs/benchmark-design.md) — scenario contract, ground-truth separation, metrics, and release gate.
- [Release process](docs/release-process.md) — automatic versioned releases, wheel smoke tests, and checksums.
- [Contributing](CONTRIBUTING.md) — small changes, verification expectations, and review workflow.

## Contributing and quality gates

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow. Changes should be small, tested, and documented. Do not claim support for an integration, benchmark result, or production guarantee without an executable test or reproducible artifact.

## License

MIT. Dataset terms remain separate: each external dataset must retain its own license and attribution, and datasets with incompatible terms must not be redistributed through this repository.
