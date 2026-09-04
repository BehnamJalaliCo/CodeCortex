# Structural Intelligence provenance record

CodeCortex's Structural Search and Structural Rewrite capabilities drive an
external syntax-aware matching engine as an optional subprocess. The engine is
not vendored, embedded, or reimplemented.

## Upstream source

- Upstream project: ast-grep
- Upstream repository: `ast-grep/ast-grep`
- Upstream URL: https://github.com/ast-grep/ast-grep
- Recorded upstream branch: `main` (informational only)
- Recorded upstream commit: `29285d16757371a70a93190929940886e68618d3`
- Version tested against: `0.45.3` (published as the `ast-grep-cli` package)
- License observed at the recorded revision: MIT License
- Copyright notice at the recorded revision: Copyright (c) 2022 Herrington Darkholme

## Integration mode

**Optional external dependency, invoked as a subprocess.** No upstream source
code is copied into CodeCortex, and no upstream Rust code is embedded.

`src/codecortex/structural/engine.py` resolves the executable and invokes it
with an explicit argument vector. CodeCortex parses the engine's documented
newline-delimited JSON match records and normalizes them into its own
`StructuralMatch` model, converting the engine's zero-based positions to the
one-based convention of the CodeCortex public surface.

The engine is declared as the optional `structural` extra in `pyproject.toml`
and pinned to `>=0.45.3,<1`. CodeCortex Core does not depend on it: when it is
absent, structural capabilities report `unavailable` and CodeCortex falls back
to lexical and symbol search.

## Test independence

CodeCortex's structural tests do not require the engine to be installed. They
drive the same subprocess code path against a deterministic in-repository stub
(`tests/fixtures/structural_engine.py`) invoked through `sys.executable`, so CI
is reproducible on every platform. Tests that exercise the real engine are
skipped automatically when it is not installed.

## What this record does not claim

This record does not imply endorsement by, affiliation with, or sponsorship
from the upstream project or its author, and it does not transfer any
copyright. CodeCortex's adapter, path containment, limits, preview model,
content-hash transaction, rollback, MCP tools, CLI, and tests are original work
governed by this repository's own license and history.
