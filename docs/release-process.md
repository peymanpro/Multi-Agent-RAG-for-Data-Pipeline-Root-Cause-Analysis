# Release Process

## Automatic GitHub Releases

A push to `main` that changes `pyproject.toml` or `CHANGELOG.md` starts `.github/workflows/release.yml`. A maintainer may also run the workflow manually from the `main` branch.

The workflow derives the version from `[project].version` and validates the corresponding stable tag `vMAJOR.MINOR.PATCH`. It then:

1. Runs Ruff, mypy, and the full offline pytest suite.
2. Generates the deterministic diagnostic, runbook-retrieval, and end-to-end investigation evaluation reports.
3. Builds a Python wheel and source distribution and validates both with Twine.
4. Installs the built wheel into a temporary target outside the repository and runs the CLI against the packaged runbooks.
5. Creates SHA-256 checksums for package distributions and all evaluation reports.
6. Creates an annotated version tag pointing at the validated main commit if the version tag does not already exist.
7. Publishes a GitHub Release with generated release notes and the package, benchmark, and checksum assets, unless that version has already been published.

If a version tag points to another commit and a release for that version already exists, the workflow completes as a no-op and leaves both immutable objects unchanged. This allows non-versioning changes to `pyproject.toml` (such as optional dependencies) to pass release verification without trying to re-publish the same version. If a tag exists for another commit but no release exists, the workflow fails closed; it never moves an existing tag. An existing tag pointing at the validated commit is reused, and an existing release is never overwritten.

The workflow uses the repository-scoped `GITHUB_TOKEN` with `contents: write`. It does **not** publish to PyPI. Registry publication would be a separate change requiring a configured project and trusted-publishing permissions.

## Preparing a release

1. Update `project.version` in `pyproject.toml`.
2. Add the new version and user-facing changes to `CHANGELOG.md`.
3. Open a small pull request that passes the regular CI checks.
4. After it is merged into `main`, inspect the Release workflow run and verify the attached artifacts.
5. Do not claim the release is complete until the workflow is green and the GitHub Release contains the expected files.

Do not reuse a published version tag. If verification or packaging fails before tag creation, fix the source in a new commit and rerun validation. If tag creation succeeded but publication failed, rerun the workflow on the same commit; the workflow verifies the existing tag target before attempting to publish. Changes that do not bump the package version will not overwrite or re-create an already published release.

## Included artifacts

- Python wheel and source distribution.
- Diagnostic benchmark JSON.
- Retrieval relevance benchmark JSON.
- End-to-end investigation benchmark JSON.
- `SHA256SUMS.txt` covering distributions and benchmark evidence.

Evaluation artifacts document measurements on the committed synthetic and hand-judged local corpora. They are not proof of production root-cause accuracy or real-world reliability.
