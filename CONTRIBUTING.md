# Contributing

Thank you for improving CodeCortex. Focused, tested changes are easier to review and safer to release.

## First contribution

Start with the repository's [good first issues](https://github.com/BehnamJalaliCo/CodeCortex/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22). They are intentionally scoped to be reviewable without requiring knowledge of the entire engine.

If an issue is unclear, ask a question on that issue before building a large change. Do not create speculative rewrites for unassigned work.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest -q
```

## Pull requests

Keep each pull request focused on one problem. Add tests for behavior changes, document user-visible changes, and explain architecture decisions that cross subsystem boundaries.

Before opening a pull request:

```bash
ruff check .
pytest --cov=codecortex --cov-report=term-missing
```

Never include credentials, customer data, private repository content, or vulnerability details in a public contribution.

## Architecture

Keep provider-specific behavior behind explicit contracts. Prefer deterministic local behavior, bounded side effects, testable adapters, and compatibility-preserving interfaces.

## Security

Potential vulnerabilities must be reported privately according to `SECURITY.md`, not through public issues.

## Community

Participation is governed by `CODE_OF_CONDUCT.md` and project decisions follow `GOVERNANCE.md`.
