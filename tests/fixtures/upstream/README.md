# Vendored upstream conformance fixtures

Files under this directory are **test fixtures only**. Nothing here is imported
by `src/codecortex`, shipped in the wheel, or part of the runtime dependency
graph. They exist so that conformance tests can run deterministically and
offline, pinned to an exact upstream revision, instead of fetching a floating
branch during CI.

Each subdirectory carries a `PROVENANCE.json` recording the upstream
repository, the exact commit, the upstream path, the SHA-256 of every vendored
file, and whether the file was modified. Vendored files are byte-identical to
upstream; where upstream ships a licence, a copy is vendored alongside.

`scripts/refresh_upstream_fixtures.py` re-downloads the pinned files and
verifies their digests against the manifest. Run it when a pin is intentionally
moved; it will not silently accept different content.

| Directory | Upstream | Commit | Licence |
| --- | --- | --- | --- |
| `scip/` | [scip-code/scip](https://github.com/scip-code/scip) | `1c2b6db7e560d5233c944f36e4ac1377cc6963fc` | Apache-2.0 |

Attribution for these fixtures is also recorded in `THIRD_PARTY_NOTICES.md`.
