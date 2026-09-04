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

**Protocol consumption.** No upstream source code is copied into CodeCortex.

`src/codecortex/precision/schema.py` transcribes the field numbers, role bit
flags, and range encodings published in the upstream `scip.proto` schema at the
recorded revision. `src/codecortex/precision/wire.py` implements the subset of
the standard protocol-buffer binary encoding needed to decode those fields, and
`src/codecortex/precision/identity.py` implements the published symbol-identity
string grammar. These are original implementations written against the public
schema, not derived from upstream Go, Rust, or TypeScript bindings.

Consuming a documented wire format is an interoperability implementation. The
attribution above is recorded because the schema and its documentation are the
source of the field numbering and semantics CodeCortex relies on.

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
