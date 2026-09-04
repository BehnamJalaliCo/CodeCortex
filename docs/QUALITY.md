# Quality Targets

CodeCortex treats measurable quality signals as release inputs, not decorative badges.

## Coverage

The first repository-wide branch-coverage measurement added on 2026-08-31 was **66.36%** across the `codecortex` package. CI now enforces the project target of **90% repository-wide branch coverage** (`--cov-fail-under=90`, matching `fail_under` in `pyproject.toml`), while Codecov patch coverage targets 90% for newly changed code.

A passing coverage number is one quality signal, not proof of correctness. High-value behavior still needs assertions that would fail for the wrong reason, and security boundaries still need adversarial tests.

## Type checking

`mypy` runs in strict mode over the whole `codecortex` package and is enforced in CI. The package ships a `py.typed` marker, so the strict run type-checks the distribution as consumers see it. The only configured relaxation is `ignore_missing_imports` for `sentence_transformers`, an optional extra that publishes no type information and is imported behind a guard.

## Required local checks

```bash
ruff check .
mypy
pytest -q
pytest -q --cov=codecortex --cov-report=term-missing
```

## Release quality

Tagged releases must pass the release matrix, package validation, smoke installation, security checks, SBOM generation, checksums, signing, and provenance attestation before publication.
