# Benchmark Design

## Purpose

The benchmark measures whether an investigation system can diagnose controlled data-pipeline incidents from the evidence available at inference time. It is not a claim that synthetic incidents represent every production failure.

The benchmark must support repeatable comparison between:
- deterministic diagnostics;
- retrieval-augmented generation without multiple agents;
- one tool-using agent;
- bounded multi-agent investigation;
- bounded multi-agent investigation with a final evidence verifier.

The first implementation may expose these as staged baselines. A baseline must not be reported as measured until the runner has executed it and saved its raw per-case results.

## Scenario contract

Each benchmark case has two logically separate parts.

### Observable incident input

The system under test may receive:
- a stable case ID;
- a natural-language incident question;
- pipeline task/run observations;
- input and output dataset metadata;
- schema snapshots and declared contracts;
- deterministic data-quality check results;
- lineage edges;
- log excerpts and runbook documents;
- timestamps and source identifiers.

Only evidence available to an investigator belongs in this part. Ground-truth labels and hidden injection metadata must not be serialized into the runtime context.

### Hidden evaluation truth

The evaluator may read:
- the primary injected fault class;
- the responsible component or transformation;
- affected downstream nodes;
- expected supporting observations;
- expected counter-evidence or known ambiguity;
- whether a confident diagnosis is justified.

The evaluator must pass only the observable part to the system under test. A test should fail if a ground-truth field accidentally appears in an agent prompt, retriever corpus, tool response, or report context.

## Initial fault taxonomy

| Fault class | Example injection | Expected evidence |
|---|---|---|
| Schema drift | Rename or remove a required column | Contract mismatch between upstream and downstream snapshots |
| Duplicate records | Replay a batch without idempotency | Duplicate-key check and matching batch/run metadata |
| Stale input | Stop publishing new partitions | Dataset freshness threshold breach and last successful update |
| Transformation defect | Alter a deterministic transformation rule | Reproducible aggregate mismatch or failed invariant |
| Upstream task failure | Fail a producer task | Failed task outcome and dependent downstream runs |
| Partial load | Publish fewer rows than the source manifest declares | Source count versus loaded count discrepancy |
| Broken dependency | Remove or misconfigure a declared lineage edge | Expected dependency absent from observed graph; report as suspected only if evidence supports it |
| Ambiguous incident | Provide incomplete or conflicting observations | Correct abstention or calibrated uncertainty rather than invented certainty |

Each scenario should have a stable ID, version, fault family, observable fixture, hidden truth, and deterministic expected checks. Mutations should be isolated so the cause remains interpretable. Compound faults can be introduced after single-fault cases are reliable.

## Leakage controls

1. Runtime input and hidden truth are stored separately.
2. The runtime API accepts only the observable case payload.
3. The benchmark runner loads truth only after the investigation completes.
4. Hidden labels never enter retrieval indexes, prompts, tool results, or cached context.
5. Unit tests include sentinel values in hidden truth and assert that they do not appear in the runtime payload.
6. Any report artifact containing hidden truth must be explicitly marked as evaluator-only and never passed back to the system.
7. The benchmark manifest records fixture versions and hashes so a result can be reproduced.

## Metrics

Metrics are reported per case first, then aggregated. Missing or invalid outputs count as failures rather than being silently omitted.

- **Root-cause top-1/top-k accuracy:** reserved for a later agent baseline that emits explicit ranked cause hypotheses. The deterministic v1 baseline does not claim root-cause identification.
- **Evidence precision:** fraction of cited evidence references that resolve to evidence available for that case and actually support the attached claim under the benchmark's deterministic checks.
- **Evidence coverage:** fraction of required expected observations surfaced by the report or trace.
- **Abstention quality:** whether the system declines to assert a cause when the case is explicitly ambiguous or evidence is insufficient.
- **Affected-node F1:** precision/recall over the set of downstream components identified as affected.
- **Latency:** elapsed wall-clock time for a case, including retries.
- **Cost:** recorded provider usage or a clearly labeled estimate when provider usage data is unavailable.
- **Operational reliability:** malformed outputs, timeouts, budget overruns, and unhandled errors.

The v1 runner reports ranked fault-class metrics, multi-label precision/recall/F1 and exact match, finding-code detection, affected-node detection, evidence-reference validity, and per-case runtime. Future agent baselines must additionally report ranked root-cause accuracy, abstention quality, latency, and cost where applicable. Metrics must define their denominator and behavior for ties, abstentions, and missing fields. Do not collapse all dimensions into one score unless the weighting is documented and the component metrics remain available.

## Comparison protocol

1. Freeze the scenario manifest and benchmark version before comparing approaches.
2. Use the same observable incident input for each baseline.
3. Keep model, prompt, retrieval configuration, tool budget, and random seeds in a run manifest when applicable.
4. Save per-case outputs, evidence references, traces, timing, and errors.
5. Use paired per-case comparisons; do not compare aggregate numbers from different scenario sets.
6. Include a deterministic offline smoke suite in CI. Larger or model-backed runs may be optional and must be labeled separately.
7. Report failure cases and confidence intervals where the benchmark size supports them.
8. Do not present synthetic-fixture performance as a production accuracy guarantee.

## External datasets

Public log collections can exercise parsing and anomaly detection, but their labels may indicate an anomalous line or event rather than the underlying root cause of a data quality failure. Do not silently reinterpret such labels. Record source URL, license, dataset version, checksum, transformation steps, and the exact role the data plays in evaluation. Do not redistribute external data unless its license permits it.

## Release gate

A benchmark-related release must include:
- the benchmark version and fixture manifest;
- the invocation used to generate results;
- raw per-case results in a machine-readable format;
- aggregate metrics and metric definitions;
- a note identifying synthetic versus external cases;
- a clear limitations section.


## End-to-end investigation comparison

Run the separate deterministic-vs-multi-agent evaluator with:

    pipeline-rca-evaluate-investigation

The versioned benchmark includes compound-fault and insufficient-evidence cases to exercise multi-label diagnosis and abstention. Ranked top-k metrics are reported alongside full-set multi-label metrics so a case with two expected faults cannot be described as fully correct merely because one fault appears in the ranking. The default run stays offline. To opt into a real OpenAI-compatible chat model, configure `RCA_API_KEY`, `RCA_MODEL`, and optionally `RCA_API_BASE_URL`, then run:

    pipeline-rca-evaluate-investigation --with-model --output evaluation-artifacts/model-investigation-benchmark.json

Model-backed runs are opt-in and can incur provider charges. The report records the requested model name, model calls, model-assisted cases, and measured model-step time. The current `ChatModel` interface does not return provider token-usage metadata, so usage and cost are explicitly left unavailable rather than guessed.

The benchmark runs both the single-pass deterministic diagnostic function and the offline multi-agent orchestrator on the exact same observable case. The evaluator reads the matching truth file only after both predictions are complete. It reports cause-class Top-1/Top-k, MRR, clean-case abstention, finding-code set metrics, affected-node set metrics, incident-vs-runbook citation integrity, and per-case latency. It deliberately does not call a model provider; model-backed systems need a separately budgeted, provider-specific evaluation because outputs and costs are stochastic.

Ground-truth separation prevents accidental injection into the runtime case object; it is not a security boundary against a malicious process that can read the public repository files. The synthetic benchmark is intended as a regression harness and must not be described as proof of production effectiveness.
