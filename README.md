# Evidence-Grounded Multi-Agent RAG for Data-Pipeline Root-Cause Analysis

> An offline-first Python system that combines deterministic diagnostics, provenance-aware runbook retrieval, bounded specialist investigation, and reproducible evaluation to help engineers investigate data-pipeline failures.

[![CI](https://github.com/peymanpro/Multi-Agent-RAG-for-Data-Pipeline-Root-Cause-Analysis/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/peymanpro/Multi-Agent-RAG-for-Data-Pipeline-Root-Cause-Analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](https://www.python.org/)

## What this project does

Data-pipeline incidents rarely have a single obvious signal. Schema changes, stale inputs, duplicate records, task failures, broken dependencies, and misleading runbook matches can overlap. Engineers must correlate those signals before they can explain what might have gone wrong.

**Pipeline RCA** turns that investigation into a bounded, inspectable workflow. It combines deterministic checks with source-grounded retrieval and optional model-assisted hypothesis generation, then validates evidence references and records an execution trace. Its purpose is not to make a confident-sounding guess; it is to help an engineer understand what the available evidence supports, what remains uncertain, and what should be investigated next.

The project evaluates a specific engineering question:

> When operational evidence is incomplete or ambiguous, what value does bounded multi-agent investigation add over deterministic diagnostics and retrieval baselines—and can that value be measured without hiding cost, latency, or unsupported claims?

## Project status

**Latest tagged release: [v0.5.0](https://github.com/peymanpro/Multi-Agent-RAG-for-Data-Pipeline-Root-Cause-Analysis/releases/tag/v0.5.0).** The release contains a Python wheel, source distribution, diagnostic/retrieval/investigation benchmark reports, and SHA-256 checksums. The offline investigation benchmark includes compound-fault and insufficient-evidence cases; optional model-backed evaluation is available separately.

The default diagnostic and lexical-retrieval paths run locally without model credentials. Hosted chat and embedding calls are opt-in. The optional HTTP API is read-only; Airflow, dbt, and OpenLineage integrations normalize source metadata rather than triggering jobs or changing data.

**Important boundaries:** the system does not automatically remediate production incidents, its included benchmarks do not establish production-wide accuracy, evidence-reference validity is not proof of semantic entailment, and model confidence is not calibrated. API authentication uses static Bearer credentials and scopes—not OIDC/SSO—and the project does not publish to PyPI.

## Why this design

| Capability | Engineering approach | Why it matters |
|---|---|---|
| Deterministic diagnostics | Typed incident contracts and explicit checks for schema, data quality, task state, and lineage | Keeps rules and graph traversal testable without an LLM |
| Evidence retrieval | Markdown ingestion, stable chunks, source-line provenance, BM25, and optional dense/hybrid retrieval | Makes retrieved context traceable to its source |
| Bounded investigation | Specialist roles, explicit budgets, execution traces, and deterministic fallback | Makes model-assisted work inspectable and limits uncontrolled work |
| Evidence verification | Validate cited evidence identifiers and distinguish observations from hypotheses | Reduces unsupported references without pretending to prove semantic entailment |
| Reproducible evaluation | Versioned cases, evaluator-only truth, retrieval relevance labels, and per-case reports | Makes behavior measurable and helps guard against benchmark leakage |
| Read-only integrations | Optional API plus Airflow REST, dbt-artifact, and OpenLineage adapters | Reuses the investigation core without giving it production write capabilities |

## Investigation flow

```text
Incident observations + investigation question
                    |
                    v
          Typed case and evidence
                    |
          +---------+----------+
          |                    |
          v                    v
 Deterministic checks     Runbook retrieval
 schema / freshness       BM25 by default
 duplicates / counts      optional dense + hybrid
 task state / lineage     source provenance
          |                    |
          +---------+----------+
                    v
       Bounded investigation workflow
       competing hypotheses and specialists
       optional model-assisted generation/review
                    |
                    v
       Evidence-reference verification
       deterministic fallback where needed
                    |
                    v
       Cited report + trace + uncertainty
                    |
                    v
      Offline evaluation against baselines
```

The CLI can run the deterministic baseline or the bounded specialist workflow. Hybrid retrieval and model calls require explicit configuration. The HTTP API does not expose a model-provider switch or remediation tools.

## Quick start

Requirements: Python 3.12 or newer.

Install the project and its development tools:

```bash
python -m pip install -e ".[dev]"
```

Run the deterministic diagnostic baseline:

```bash
pipeline-rca examples/cases/schema-drift.json
```

Run a bounded multi-agent investigation offline. No API key or network call is required for this path:

```bash
pipeline-rca-investigate examples/cases/schema-drift.json
```

For deterministic freshness checks, supply an explicit timezone-aware timestamp so results do not silently depend on the machine clock:

```bash
pipeline-rca-investigate examples/cases/schema-drift.json --as-of 2026-10-15T10:05:00Z
```

To opt into model-assisted hypothesis generation and independent counter-evidence review, configure the compatible provider credentials in the environment and use `--with-model`:

```bash
# Set RCA_API_KEY, RCA_MODEL, and optionally RCA_API_BASE_URL in your environment.
pipeline-rca-investigate examples/cases/schema-drift.json --with-model
```

The model-assisted path is optional. Invalid model output falls back to deterministic synthesis, and the final evidence-reference verifier still runs. See [agent orchestration](docs/agent-orchestration.md) for the exact boundaries and budgets.

## Retrieval and RAG

### Offline lexical retrieval

The default retriever is BM25 over local operational Markdown. Chunks retain document-relative source paths, line spans, section headings, and stable identifiers.

```bash
pipeline-rca-search data/runbooks "duplicate business keys idempotent retry" --top-k 3
```

This provides a measurable lexical baseline without an embedding service, hosted model, or API credential.

### Optional dense and hybrid retrieval

Hybrid mode combines BM25 and cosine-similarity ranking with reciprocal-rank fusion (RRF). Configure `RCA_API_KEY`, `RCA_EMBEDDING_MODEL`, and optionally `RCA_API_BASE_URL`, `RCA_EMBEDDING_CACHE`, and `RCA_EMBEDDING_CACHE_NAMESPACE`:

```bash
pipeline-rca-investigate examples/cases/schema-drift.json --retrieval-mode hybrid
```

The SQLite embedding cache stores vectors under hashed keys scoped to an opaque provider/model namespace; it does not store the original runbook or query text. The dense index is rebuilt in memory for each invocation, and uncached text/query embeddings may incur provider cost. CI uses test doubles and does not require provider credentials.

See [retrieval design](docs/retrieval.md) and [hybrid retrieval design](docs/hybrid-retrieval.md).

## Evaluation: measure before adding complexity

The repository includes three offline evaluation commands:

```bash
# Deterministic diagnostic baseline
pipeline-rca-benchmark --output artifacts/diagnostic-benchmark.json

# Retrieval relevance
pipeline-rca-evaluate-retrieval --output artifacts/retrieval-benchmark.json

# Deterministic versus bounded investigation (offline; no provider calls)
pipeline-rca-evaluate-investigation --output artifacts/investigation-benchmark.json

# Optional model-backed evaluation (requires RCA_API_KEY and RCA_MODEL; may incur provider cost)
pipeline-rca-evaluate-investigation --with-model --output artifacts/model-investigation-benchmark.json
```

- **Diagnostic benchmark:** evaluates injected fault classes, finding codes, affected nodes, evidence-reference validity, and per-case runtime.
- **Retrieval benchmark:** reports document-level Precision@k, Recall@k, Hit@k, MRR, and nDCG@k against hand-judged relevance for the included runbook corpus.
- **Investigation evaluation:** compares the deterministic diagnostic baseline with the multi-agent orchestrator and reports root-cause Top-1/Top-k, MRR, clean-case abstention, multi-label precision/recall/F1 and exact match, finding/node detection, evidence integrity, and per-case timing.

Runtime inputs are separated from evaluator-only ground truth. The end-to-end evaluation runs both execution paths before loading evaluator labels. The versioned incident suite includes compound-fault and insufficient-evidence fixtures to test multi-label diagnosis and abstention. The default benchmark remains offline; `--with-model` opts into actual provider calls and records model name, calls, model-step time, and fallback outcomes. The current chat interface does not expose provider token-usage metadata, so model cost is not calculated. These benchmarks use synthetic cases and hand-authored relevance judgments; the results do **not** establish production incident accuracy or prove that an LLM improves root-cause identification on real data. See [benchmark design](docs/benchmark-design.md) for the protocols, metrics, leakage controls, and limitations.

## Optional read-only API

Install the API extras and start the local service:

```bash
python -m pip install -e ".[api,dev]"
uvicorn pipeline_rca.api.app:app --host 127.0.0.1 --port 8000
```

The API provides:

- `GET /health/live` — process liveness.
- `GET /health/ready` — readiness of the local runbook corpus.
- `POST /v1/investigations` — a bounded, read-only investigation.

It enforces request-body limits before JSON parsing, supports static per-user Bearer tokens with explicit scopes, emits redacted JSON-line request telemetry with correlation IDs, and rate-limits investigation requests. In production mode, startup requires an identity registry and distributed Redis rate limiting; unavailable Redis fails closed. The development limiter is process-local. The included Compose configuration binds to loopback and is intended for local evaluation, not direct exposure to untrusted networks.

```bash
docker compose up --build
```

See [API authentication and operational boundaries](docs/api.md) and [distributed rate limiting](docs/rate-limiting.md). Static tokens do not provide OIDC/SSO, automatic revocation, or an enterprise identity lifecycle.

## Read-only data connectors

The connector layer converts external operational metadata into typed task observations, lineage edges, schema snapshots, and source-addressable evidence.

- **Apache Airflow REST:** reads a DAG run, task instances, and task dependencies. Task-instance pagination is bounded (500 per page by default, with a configurable maximum of 10,000).
- **dbt artifacts:** reads `manifest.json` and `run_results.json` from a completed run.
- **OpenLineage:** reads a bounded JSON Lines event export and extracts run states, dataset lineage, and available output-schema metadata.

The HTTP transport uses GET requests, timeouts, response-size limits, redirect rejection, path/origin validation, and TLS outside loopback. The adapters do not execute warehouse SQL, trigger jobs, mutate source systems, or automatically remediate failures. Source credentials, filesystem permissions, egress policies, and least privilege remain deployment responsibilities.

See [connector setup and contracts](docs/connectors.md).

## Repository structure

```text
src/pipeline_rca/
  agents/       # bounded specialists, orchestration, synthesis, verification
  api/          # optional FastAPI boundary, auth, limits, telemetry
  connectors/   # read-only Airflow, dbt, and OpenLineage adapters
  diagnostics/  # deterministic schema, task, and data-quality checks
  evaluation/   # diagnostic, retrieval, and investigation evaluation
  retrieval/    # chunking, BM25, embeddings, hybrid search, SQLite cache
  models.py     # shared typed incident and evidence contracts
  lineage.py    # dependency graph analysis
  investigation.py
  serialization.py

tests/
  unit/
  integration/
  security/

data/
  benchmark/             # versioned synthetic diagnostic cases and evaluator truth
  retrieval-benchmark/   # retrieval evaluation contract
  runbooks/              # local operational Markdown corpus

docs/                    # architecture, evaluation, security, API, and release contracts
```

## Development and quality checks

Run the same core checks used by CI:

```bash
python -m pip install -e ".[dev]"
ruff check .
mypy
pytest -q
docker build --tag pipeline-rca-api:local .
```

The automated release workflow additionally validates the version/tag, generates all three benchmark reports, builds wheel and source distributions, checks distribution metadata, smoke-tests the installed wheel outside the repository, and publishes checksummed artifacts. It does not publish to PyPI.

## Technical documentation

- [Architecture](docs/architecture.md) — components, evidence flow, budgets, and failure handling.
- [Agent orchestration](docs/agent-orchestration.md) — specialist roles, model boundary, and deterministic fallback.
- [Retrieval](docs/retrieval.md) — ingestion, chunking, BM25, and provenance.
- [Hybrid retrieval](docs/hybrid-retrieval.md) — embeddings, cosine similarity, RRF, and cache behavior.
- [Benchmark design](docs/benchmark-design.md) — datasets, metrics, leakage boundaries, and release gates.
- [Read-only API](docs/api.md) — request contracts, authentication, and operational limits.
- [Rate limiting](docs/rate-limiting.md) — Redis-backed quotas for multi-worker deployments.
- [Connectors](docs/connectors.md) — source configuration, normalized fields, and transport boundaries.
- [Release process](docs/release-process.md) — versioning, artifacts, checksums, and verification.
- [Contributing](CONTRIBUTING.md) — development and review expectations.

## License

MIT. External dataset licenses and attribution remain separate: only redistribute datasets when their terms permit it, and do not bundle data with incompatible licenses.
