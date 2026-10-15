# Release Process

## Automatic releases

A push to `main` that changes one or more of the following paths starts `.github/workflows/release.yml`:

- `pyproject.toml`
- `CHANGELOG.md`
- `.github/workflows/release.yml`

The workflow is restricted to `main`, and manual dispatch is also available from the Actions page while selecting `main`.

Before creating a release, the workflow independently installs the package and development tools, runs Ruff, mypy, and pytest, builds both the source distribution and wheel, and runs Twine metadata checks. It writes SHA-256 checksums for the distribution artifacts.

The release version is read from `[project].version` in `pyproject.toml`. The release tag uses `vMAJOR.MINOR.PATCH`. If that tag already exists, the workflow skips publication rather than trying to mutate an existing release. The GitHub Release receives the build artifacts and `SHA256SUMS.txt`.

The workflow uses the repository-scoped `GITHUB_TOKEN` with `contents: write`; it does not publish to PyPI and does not require a second API secret. A separate PyPI publication workflow should only be added if public package-index distribution becomes an explicit requirement.

## Preparing a version

1. Update the project version in `pyproject.toml`.
2. Add user-facing changes and known limitations under the same version in `CHANGELOG.md`.
3. Run `ruff check .`, `mypy`, `pytest -q`, `python -m build`, and `python -m twine check dist/*` locally or in CI.
4. Open a small pull request to `main`.
5. After its normal CI checks pass and it is merged, the release workflow validates the main commit before creating a tag and Release.
6. Inspect the release page, attached wheel/sdist, and checksums after publication.

Never reuse a published semantic version for different source contents. Bump the version and add a changelog entry for each release.

## Scope

This automation publishes a GitHub Release with Python distribution artifacts. It does not publish to PyPI, deploy a hosted service, or declare the project production-certified. CI success means the configured checks passed; it does not establish external-provider availability, model correctness, or production root-cause accuracy.
