# Quality Targets

CodeCortex treats measurable quality signals as release inputs, not decorative badges.

## Coverage

The first repository-wide branch-coverage measurement added on 2026-08-31 was **66.36%** across the `codecortex` package. CI currently enforces a 65% floor so coverage cannot silently fall below the measured baseline, while Codecov patch coverage targets 90% for newly changed code.

The project target is **90% repository-wide coverage**. The threshold should be raised progressively as uncovered CLI, backend lifecycle, MCP server, dashboard, and evaluation paths receive focused tests.

## Required local checks

```bash
ruff check .
pytest -q
pytest -q --cov=codecortex --cov-report=term-missing
```

## Release quality

Tagged releases must pass the release matrix, package validation, smoke installation, security checks, SBOM generation, checksums, signing, and provenance attestation before publication.
