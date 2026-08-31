# Release Process

CodeCortex releases are tag-driven and use trusted publishing.

1. Ensure Core CI, backend conformance, security audit, and production benchmark workflows have acceptable recent runs.
2. Update `CHANGELOG.md` and the version in `pyproject.toml`.
3. Create an annotated `vX.Y.Z` tag matching the package version and push it.
4. The Release workflow runs tests on Linux, macOS, and Windows, builds wheel/sdist artifacts, validates them, then publishes through the `pypi` GitHub environment using OIDC.
5. Never publish benchmark claims from an uncommitted local run. Attach or link the reproducible benchmark artifact and exact repository revisions.

The PyPI project must be configured for GitHub trusted publishing before the first tag is pushed. No long-lived PyPI token is required by the workflow.
