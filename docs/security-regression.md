# Prompt-Injection Regression Boundary

## Threat model

Incident questions, logs, source metadata, schema comments, operational runbooks, and retrieved document chunks are untrusted data. They may contain text that looks like instructions to the model, requests for secrets, claims of elevated authority, or directions to suppress uncertainty.

The hypothesis and counter-evidence agents use fixed system prompts that explicitly identify embedded content as untrusted. User-controlled content is serialized into a bounded JSON payload rather than interpolated into the system prompt. Hypothesis generation distinguishes observed incident evidence from general runbook context. The review stage receives incident observations only and does not treat runbooks as counter-evidence.

The regression tests under `tests/security/` verify these structural boundaries using a recording fake model. They check prompt placement and exclusion rules without network access or API credentials.

## What the tests establish

- Prompt-injection strings in a question or runbook remain inside the user-data payload; they are not appended to the trusted system prompt.
- Runbook content is labeled in the distinct `runbook_context` collection for hypothesis generation.
- The counter-evidence reviewer receives only incident observation evidence, not retrieved runbook text.
- Model output remains subject to strict JSON/schema checks and evidence-ID validation after the model call.

## What the tests do not establish

These tests do **not** prove that every hosted or local model will resist prompt injection. Models may still be influenced by hostile text within an otherwise correctly isolated user payload. Prompt wording and JSON separation are defense-in-depth, not a security boundary equivalent to authorization or sandboxing.

Consequently:

- Never place secrets, credentials, or unrestricted tool capabilities in the model context.
- Do not let model-authored text grant permissions, change budgets, select arbitrary file paths, or perform side effects.
- Keep retrieved documents separate from incident-specific observations and evaluator-only truth.
- Validate all model output using code; do not rely on a natural-language promise to follow policy.
- Run production retrieval behind source-level access control and redact sensitive records before constructing prompts.
- Treat citation existence as reference integrity, not semantic proof that the cited passage entails a claim.

The HTTP API deliberately exposes no model-provider switch or remediation tool. Its current Docker Compose setup binds to loopback and does not include production authentication/authorization, so it must not be exposed directly to untrusted networks.
