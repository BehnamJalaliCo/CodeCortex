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
and pinned exactly to `==0.45.3` — not to a range. CodeCortex parses this
engine's structured output, so the record shape is part of the integration
contract, and a range would allow an untested release to change it silently.
`cortex doctor` reports an installed build that is not the verified version
rather than showing it as plainly available. CodeCortex Core does not depend on
the engine at all: when it is absent, structural capabilities report
`unavailable` and CodeCortex falls back to lexical and symbol search.

The Python binding published by the same project (`ast-grep-py`) was evaluated
and not adopted. The subprocess adapter meets the requirements, and the prompt
for migrating was a measured material win that this work did not find.

## Observed engine behaviour

Recorded from the pinned release, and asserted by
`tests/test_structural_conformance.py`:

- A search that matches nothing exits `1`. That is not a failure.
- A pattern the engine cannot parse cleanly exits `0` with a warning on stderr
  and no matches, so the warning is the only signal that a pattern was
  malformed rather than unmatched. CodeCortex surfaces it as an error.
- Match columns count characters; byte offsets are reported separately.
- An unsupported language exits `2`.

## Test independence

CodeCortex's structural tests do not require the engine to be installed. They
drive the same subprocess code path against a deterministic in-repository stub
(`tests/fixtures/structural_engine.py`) invoked through `sys.executable`, so CI
is reproducible on every platform. Tests that exercise the real engine
(`tests/test_structural_conformance.py`) are skipped automatically when it is
not installed, and run in the dedicated structural-engine workflow, which
verifies the installed version against the pin before running them.

## What this record does not claim

This record does not imply endorsement by, affiliation with, or sponsorship
from the upstream project or its author, and it does not transfer any
copyright. CodeCortex's adapter, path containment, limits, preview model,
content-hash transaction, rollback, MCP tools, CLI, and tests are original work
governed by this repository's own license and history.
