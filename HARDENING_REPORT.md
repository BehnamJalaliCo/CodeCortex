# CodeCortex Hardening Report

This report records CodeCortex-owned hardening work and verification evidence.

## Scope

The hardening pass focused on:

- precision navigation and range handling;
- repository-scoped symbol resolution;
- position-encoding correctness;
- path and import security;
- staleness detection;
- dependency documentation transport hardening;
- structural search and guarded rewrite boundaries;
- evidence ranking and freshness behavior;
- release, security, and regression coverage.

## Verification

The repository enforces:

- Ruff linting;
- strict mypy checks;
- pytest across supported Python versions;
- coverage threshold at or above 90%;
- CodeQL and security workflows;
- package build and install smoke tests;
- Windows compatibility checks;
- Docker build smoke tests;
- signed release artifacts, checksums, SBOM, and provenance.

## Evidence principles

CodeCortex reports measured behavior only when it has a reproducible repository-owned test or benchmark. Optional capabilities that are unavailable are reported as unavailable rather than silently simulated.

## Release discipline

A release is considered valid only when the release matrix, package build, signing, publication, and configured distribution checks complete successfully for the exact release commit.

For current status, use the GitHub Actions results and release artifacts attached to the latest published release.
