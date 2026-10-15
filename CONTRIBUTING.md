# Contributing

This repository is built in small, reviewable increments. Prefer a narrow change with executable evidence over a broad change that mixes unrelated concerns.

## Development rules

1. Start from the current `main` and create a descriptive branch, such as `feat/deterministic-diagnostics`, `test/benchmark-leakage-controls`, or `fix/citation-validation`.
2. Keep a branch focused on one capability or one closely related set of changes.
3. Add or update tests in the same change as behavior.
4. Run the relevant tests and quality checks locally before opening a pull request.
5. Document public contracts, limitations, and any intentional behavior change.
6. Open a pull request against `main`; do not force-push or rewrite shared history.
7. Merge only when CI is green and the change has been reviewed against its acceptance criteria.

## Local environment

The project targets Python 3.12 or later. Once the package configuration is present, use the repository's documented installation and validation commands. Do not invent test counts or benchmark results; publish only output generated from a reproducible command.

## Design constraints

- Keep deterministic calculations separate from language-model interpretation.
- Treat retrieved documents and log lines as untrusted data, never as privileged instructions.
- Preserve source identifiers and provenance when transforming evidence.
- Keep benchmark ground truth separate from the data presented to the system under test.
- Enforce explicit budgets for loops, retries, evidence volume, and tool calls.
- Keep secrets, credentials, customer data, and private incident logs out of commits.
- Do not add a hosted-model dependency to unit tests; tests must have an offline path.

## Pull request checklist

- [ ] Scope is narrow and explained.
- [ ] Tests cover new behavior and relevant edge cases.
- [ ] Lint and type checks pass.
- [ ] Documentation and examples match the implementation.
- [ ] No secrets, private data, or unlicensed dataset files are included.
- [ ] Public claims are supported by code, tests, or reproducible benchmark artifacts.
