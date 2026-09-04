# Precision Code Intelligence provenance record

CodeCortex's Precision Code Intelligence layer consumes an existing
compiler/indexer-produced code index. It does **not** define a new code-index
protocol; it implements a reader for an established open protocol so that any
conforming indexer can feed CodeCortex.

## Upstream source

- Upstream project: SCIP (SCIP Code Intelligence Protocol)
- Upstream repository: `scip-code/scip`
- Upstream URL: https://github.com/scip-code/scip
- Recorded upstream branch: `main` (informational only)
- Recorded upstream commit: `1c2b6db7e560d5233c944f36e4ac1377cc6963fc`
- License observed at the recorded revision: Apache License, Version 2.0
  (verified from `LICENSE` at that revision)

## Integration mode

**Protocol consumption.** No upstream implementation source code is copied into
the CodeCortex package. One upstream file — the `scip.proto` schema itself,
plus its licence — is vendored byte-identical under
`tests/fixtures/upstream/scip/` as a *test fixture*, so that schema-conformance
tests run deterministically and offline instead of fetching a floating branch.
That fixture is not imported by `src/codecortex`, not shipped in the wheel, and
not a runtime dependency. Its exact digests and upstream URLs are recorded in
`tests/fixtures/upstream/scip/PROVENANCE.json`, and
`scripts/refresh_upstream_fixtures.py` re-verifies them against upstream.

`src/codecortex/precision/schema.py` transcribes the field numbers, role bit
flags, position encodings, and range encodings published in the upstream
`scip.proto` schema at the recorded revision;
`tests/test_precision_conformance.py` asserts every one of those constants
against the vendored schema, so the transcription is verified rather than
trusted. `src/codecortex/precision/wire.py` implements the subset of
the standard protocol-buffer binary encoding needed to decode those fields, and
`src/codecortex/precision/identity.py` implements the published symbol-identity
string grammar. These are original implementations written against the public
schema, not derived from upstream Go, Rust, or TypeScript bindings.

Consuming a documented wire format is an interoperability implementation. The
attribution above is recorded because the schema and its documentation are the
source of the field numbering and semantics CodeCortex relies on.

## Real-index conformance fixtures

`tests/fixtures/real_index/` holds two small source projects together with the
`index.scip` that a real, pinned language indexer produced for each, and the
official CLI's decode of the same bytes:

| Project | Indexer | Version | Generator commit |
| --- | --- | --- | --- |
| `python_project/` | scip-python | 0.6.6 | `8b60bbce1f2a4c7a517776cb395bbafb2e731e4f` |
| `typescript_project/` | scip-typescript | 0.4.0 | `891eb4293709a6a587bf4468dfa1b45a85182fd9` |

No indexer source is vendored. The indexers are built from those revisions only
to generate the fixtures, are not runtime dependencies, and are not installed by
normal CI. Both indexes pass `scip lint` from the official CLI built at the
recorded protocol revision, and `scip print --json` output is committed as an
independent decode oracle. Digests and commands are recorded per project in
`PROVENANCE.json`; `scripts/regenerate_real_index_fixtures.sh` reproduces them.

## Measured indexer behaviour

`src/codecortex/precision/compatibility.py` records column encodings that were
*measured* from those indexes rather than assumed. Both pinned indexers omit
`Document.position_encoding` and emit UTF-16 code-unit columns — including the
Python indexer, for which the schema's guidance suggests UTF-32. A declared
encoding always overrides this table, and a tool or version the measurement
does not cover falls back to code points and is reported as an assumption
rather than as exact evidence.

`scip-python` 0.6.6 additionally does not emit a definition occurrence for a
class, resolving `class Foo:` to `builtins/Foo#` with a read role. This
reproduces in that indexer's own upstream snapshot inputs. CodeCortex reports
what the index contains and does not compensate for it.

## Compatibility scope

- Schema protocol versions accepted: `0` (`UnspecifiedProtocolVersion`).
- Range encodings accepted: the typed single-line and multi-line ranges, and
  the compact three- or four-element repeated-integer encoding.
- Unknown fields are skipped rather than rejected, so an index produced by a
  newer indexer still loads.
- An index that cannot be decoded produces a typed error and a documented
  fallback to CodeCortex's own structural and heuristic resolution. It never
  produces a partially-decoded or silently wrong navigation result.

## What this record does not claim

This record does not imply endorsement by, affiliation with, or sponsorship
from the upstream project or its contributors, and it does not transfer any
copyright. CodeCortex's reader, evidence model, graph fusion, staleness
detection, caching, MCP tools, CLI, and tests are original work governed by
this repository's own license and history.
