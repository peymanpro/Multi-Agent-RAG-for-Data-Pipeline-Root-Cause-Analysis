# Bounded Multi-Agent Investigation

## Workflow

The runtime combines narrow specialist responsibilities with a mandatory deterministic verifier.

1. **Schema investigator** compares observed schema snapshots with required-column contracts.
2. **Data-quality investigator** checks row counts, duplicate-key counts, null counts, and explicitly timed freshness.
3. **Task-failure investigator** turns failed task observations into structured findings.
4. **Lineage investigator** detects directed dependency cycles and computes downstream reachability from failed tasks.
5. **Runbook retrieval investigator** retrieves local Markdown guidance with BM25 and source-line provenance.
6. **Hypothesis synthesis agent** produces ranked suspected causes. In offline mode it groups deterministic findings; optional model mode asks a chat model for structured candidate hypotheses.
7. **Model counter-evidence reviewer** is enabled only when a model is configured. It can retain, downgrade, or reject a proposed hypothesis and must cite only provided incident observations.
8. **Evidence verifier** always runs last and checks citation existence, observation-vs-runbook boundaries, duplicate identifiers, and missing provenance.

The model reviewer is advisory. Even if it rejects a hypothesis, the report records a review opinion rather than replacing it with an invented confirmed cause. The verifier checks reference integrity; it does not establish semantic entailment on its own.

## Execution budgets

The AgentBudget contract bounds the run with:
- maximum agent steps;
- maximum retrieval hits;
- maximum total evidence records;
- maximum hypotheses;
- maximum model calls;
- maximum prompt characters;
- request timeout and output-token cap.

The orchestrator reserves the final available agent step for evidence verification. If the step budget prevents one or more investigation stages from running, the report records budget-exhausted or partial status rather than implying a complete investigation. Oversized incident evidence is rejected before agents execute.

A model-assisted investigation normally makes at most two model calls: one for hypothesis generation and one for counter-evidence review. The model-call budget is explicit and can be lowered. No model call occurs unless the with-model option is passed to the CLI.

## Retrieval mode

The default retrieval mode is offline BM25. The CLI can also opt into lexical+dense hybrid retrieval with `--retrieval-mode hybrid`; this requires `RCA_API_KEY`, `RCA_EMBEDDING_MODEL`, and optionally `RCA_API_BASE_URL`. The hybrid corpus embeds local runbook chunks when it is built, so repeated CLI runs may incur repeated embedding cost because no persistent cache is implemented yet. The final verifier treats retrieved runbooks as context, never as proof of an incident-specific event. See [hybrid retrieval design](hybrid-retrieval.md).

## Model provider configuration

The provider adapter uses the OpenAI-compatible chat-completions contract with the Python standard library. Configure these environment variables at runtime:

- RCA_API_KEY — secret API key;
- RCA_MODEL — model identifier;
- RCA_API_BASE_URL — optional compatible endpoint, defaulting to the OpenAI API base URL.

Do not commit credentials or place them in example case files. For local self-hosted providers, choose an endpoint reachable from the runtime environment. HTTP endpoints may be acceptable for loopback development but production credentials should use TLS.

## Model output controls

The hypothesis agent accepts strict JSON only. It rejects extra fields, invalid fault classes, out-of-range confidence values, duplicate classes, and evidence IDs that were not actually shown in the bounded prompt. Model-generated confidence is marked uncalibrated in the report. Proposals without supporting incident observations are capped at low confidence.

The reviewer accepts decisions only for hypotheses that already exist. Counter-evidence IDs must resolve to incident observations included in the review prompt; retrieved runbook chunks are deliberately excluded as counter-evidence. Invalid generation output falls back to deterministic synthesis. Invalid review output preserves the pre-review hypotheses and records a warning. The final verifier then runs regardless.

## Report fields

The JSON report includes:
- deterministic diagnostic findings;
- ranked hypotheses with supporting, contradicting, and runbook-context references separated;
- evidence records with source locators;
- verification issues;
- agent execution trace with step order, timings, and reference IDs;
- model usage metadata and budget status.

The report never claims the root cause is confirmed. A valid evidence identifier proves that a reference resolves; it does not prove the referenced text semantically entails the full generated claim.

## Run examples

Offline mode (no API key required):

    pipeline-rca-investigate examples/cases/schema-drift.json

Freshness checks need a reproducible, timezone-aware evaluation time:

    pipeline-rca-investigate examples/cases/schema-drift.json --as-of 2026-10-15T10:05:00Z

Opt in to hypothesis generation plus counter-evidence review with an OpenAI-compatible model:

    pipeline-rca-investigate examples/cases/schema-drift.json --with-model

## Limitations

- Specialist checks in the initial version are rule-based and cover only the represented observation fields.
- The model is not trained or fine-tuned for root-cause analysis; it proposes hypotheses over bounded evidence.
- The reviewer can miss counter-evidence or give an incorrect critique.
- Citation-reference validation is not full semantic entailment verification.
- Confidence values are not calibrated probabilities.
- The local runbook corpus is small, English-oriented, and intended for engineering examples.
- API/provider behavior and real-world effectiveness require separate evaluation.
