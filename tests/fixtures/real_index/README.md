# Real-index conformance fixtures

Each subdirectory is a small source project plus the `index.scip` that a
**real, pinned language indexer** produced for it, and the official CLI's
decode of those same bytes (`expected.json`).

Nothing here is upstream source code. The indexers are built from their pinned
revisions only to generate these files; they are not vendored, not runtime
dependencies, and not installed by CI.

| Project | Indexer | Version | Pinned generator commit |
| --- | --- | --- | --- |
| `python_project/` | scip-python | 0.6.6 | `8b60bbce1f2a4c7a517776cb395bbafb2e731e4f` |
| `typescript_project/` | scip-typescript | 0.4.0 | `891eb4293709a6a587bf4468dfa1b45a85182fd9` |

Both indexes were validated with the official CLI built from
`scip-code/scip@1c2b6db7e560d5233c944f36e4ac1377cc6963fc`:

- `scip lint index.scip` — clean for both.
- `scip print --json index.scip` — committed as `expected.json` and used as an
  independent oracle in `tests/test_real_index_conformance.py`.

Each project's `PROVENANCE.json` records the generator repository and commit,
the exact command, and SHA-256 digests of the sources, the index, and the
oracle output. `scripts/regenerate_real_index_fixtures.sh` rebuilds everything
from those pins; `scripts/write_real_index_provenance.py` refreshes the
manifests.

## What these fixtures exist to prove

They exist because a hand-built fixture can only encode what its author already
believes. These recorded behaviours were measured, and two of them contradict
what the schema's guidance would suggest:

- **Neither indexer declares `Document.position_encoding`**, although the
  schema says a conforming indexer should.
- **Both emit UTF-16 code-unit columns** — including the Python indexer, for
  which the schema's guidance suggests UTF-32. This is the measurement behind
  `codecortex.precision.compatibility.MEASURED_INDEXERS`, and
  `test_real_columns_are_utf16_not_code_points` re-derives it from these files.
- **Both reuse `local` ids across documents**, which is the collision that
  document-scoped symbol keys exist to prevent.
- **They disagree about role bits on references**: scip-python sets
  `ReadAccess`, scip-typescript emits `0`.
- Both use the **compact repeated-integer range encoding**, not the typed
  range messages.

## Known upstream limitation

`scip-python` 0.6.6 does not emit a definition occurrence for a **class**: it
resolves `class Foo:` to `builtins/Foo#` with a read role instead of to the
project symbol with a definition role. This reproduces in the indexer's own
upstream snapshot inputs, so it is not a property of this fixture. `scip lint`
reports it whenever such a class is referenced from another file. The Python
fixture therefore exercises duplicate **function** names rather than duplicate
class names; CodeCortex reports what the index contains and does not
compensate. The TypeScript fixture covers classes and interfaces, where
scip-typescript emits definitions and implementation relationships correctly.
