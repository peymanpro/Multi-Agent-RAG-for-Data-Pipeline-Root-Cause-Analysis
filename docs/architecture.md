# Architecture

## Status

This document defines architectural boundaries to guide implementation. Components described as target components are not considered implemented until source code and tests exist.

## Layers

### Domain

Owns language-agnostic, typed concepts:
- incident case and observation;
- evidence item with source, locator, timestamp, and content digest;
- deterministic diagnostic finding;
- hypothesis with a normalized fault class and explicit evidence links;
- investigation trace and final incident report.

The domain layer must not depend on a model SDK, vector database, web framework, or orchestration library.

### Deterministic diagnostics

Performs checks that can be answered by ordinary code:
- schema and contract comparison;
- freshness thresholds;
- duplicate-key and null-rate checks;
- row-count and aggregate invariants;
- task status and lineage traversal.

A diagnostic finding records the rule, observed value, expected value, evidence references, and severity. A check must not label a cause as confirmed merely because it found a symptom.

### Evidence ingestion and retrieval

Transforms external documents and runtime observations into source-addressable evidence. Every returned item must preserve its source identity and location. Retrieval is read-only. The initial offline retrieval baseline may be lexical; dense embeddings and external providers are adapters, not hard requirements for the core.

### Investigation orchestration

The orchestrator owns the bounded workflow, not the specialist's domain logic. It:
- creates a scoped investigation state;
- chooses the minimum useful set of investigators;
- passes only the evidence each task needs;
- validates structured tool and agent outputs;
- limits steps, wall time, evidence volume, and retries;
- records decisions, handoffs, and failures;
- routes insufficient or conflicting evidence to verification or abstention.

Specialists return structured findings rather than directly modifying shared state. Updates pass through validated contracts.

### Verification and reporting

The verifier checks that referenced evidence exists in the current case, that source identifiers are stable, that required fields are present, and that claims do not exceed the evidence. It must distinguish:
- observed fact;
- deterministic diagnostic result;
- agent-generated hypothesis;
- benchmark ground truth, visible only to the evaluator.

The report includes likely cause(s), supporting and contradicting evidence, affected components, uncertainty, and safe next steps. It must not hide absent evidence behind fluent prose.

### Interfaces

The core uses protocols/typed interfaces for retrievers, language models, clock/time measurement, storage, and agent execution. Adapters can be added without importing the provider SDK throughout the domain.

The optional HTTP API validates input/output schemas and applies the same investigation budgets as the non-HTTP entry point.

## State and evidence flow

Each investigation carries a correlation ID and an append-only sequence of events. An event captures the stage, actor, input references, output references, elapsed time, and outcome. Secrets and unnecessary raw document contents should not be copied into traces.

Evidence identifiers must be case-scoped or content-addressed. A report must never cite a document that was not part of the case's allowed evidence set.

## Failure handling

- Invalid structured output: reject, record the validation error, and use a bounded retry only when configured.
- Retrieval unavailable: degrade to the configured deterministic evidence set and report the limitation.
- Agent timeout: preserve completed findings and mark the timed-out task as incomplete.
- Budget exhausted: stop execution and return a partial report with explicit incompleteness.
- Conflicting evidence: retain both sides and lower confidence; do not choose a cause solely because one agent is more persuasive.
- No sufficient evidence: abstain from root-cause assertion.

## Security

- Treat logs, documents, and retrieved snippets as untrusted input.
- Retrieved text cannot grant permissions or override tool policy.
- External connectors are read-only unless a separately reviewed feature explicitly says otherwise.
- No secrets or production credentials belong in test fixtures or traces.
- Benchmark truth is an evaluator-only boundary.
- Agent output is data, not executable code. SQL tools must use read-only, allowlisted queries and bounded results if added.

## Design decision: framework-free core

The first deterministic implementation should not require a multi-agent framework. This isolates core correctness and permits robust offline tests. A workflow framework may later implement orchestration behind the same contracts, with a documented comparison to the minimal internal runtime.
