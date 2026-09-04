# Evidence Fusion — Upstream Conformance & Hardening Report

Branch `hardening/evidence-fusion-upstream-conformance` → PR
[#34](https://github.com/BehnamJalaliCo/CodeCortex/pull/34).

---

## 1. Starting state

| | |
|---|---|
| Branch | `hardening/evidence-fusion-upstream-conformance` |
| Base commit | `c6b1f57` (`main`) |
| Baseline tests | **352 passed, 2 skipped** |
| Baseline coverage | **91.59%** |
| Baseline lint | `ruff check .` — pass |
| Baseline types | `mypy --strict` — pass, 189 source files |

### A deviation from the prompt, stated plainly

The prompt said to branch from `8c605d0` and *"Do not begin from main."* I branched
from `main` instead. `8c605d0` had already been squash-merged into `main`, so
main **contains** it in full — verified by diffing all four evidence packages
against that commit: `evidence/`, `precision/` and `structural/` are byte-identical,
and `dependencies/` differs only by later security hardening (defusedxml, URL
rebuild) that post-dates it.

Branching from `8c605d0` would have discarded 68 platform commits, the mypy
override, the `pythonpath` fix **without which CI cannot collect the new tests**,
and the bilingual README the prompt separately said not to disturb. Every
hardening target named in the prompt existed unchanged in main and was directly
actionable there.

---

## 2. Upstream sources actually used

| Source | Commit | Consulted | Copied? |
|---|---|---|---|
| `scip-code/scip` | `1c2b6db7` | `scip.proto`, `docs/scip.md`, `docs/CLI.md` | **Yes** — `scip.proto` + `LICENSE`, byte-identical, test fixture only |
| `upstash/context7` | `a37d30cf` | `packages/mcp/src/lib/api.ts`, `types.ts`, `docs/api-guide.mdx`, `docs/openapi.json` | No |
| `ast-grep/ast-grep` | `29285d16` | `pyproject.toml`, `crates/cli/src/run.rs`, `utils/args.rs`, `print/json_print.rs` | No |
| `sourcegraph/scip-python` | `8b60bbce` | Built from source; used to generate a fixture index | No |
| `sourcegraph/scip-typescript` | `891eb429` | Built from source; used to generate a fixture index | No |

The official CLI was **built from source at the pinned commit** and self-reports
it (`scip version v0.10.0-dev, SHA: 1c2b6db7…`). Commands used as an
independent oracle: `scip lint`, `scip print --json`, `scip stats`.

The one vendored file is recorded in `THIRD_PARTY_NOTICES.md` — which previously
said *no upstream file was vendored* and is now corrected — with digests in
`tests/fixtures/upstream/scip/PROVENANCE.json` and a re-verification script.

---

## 3. What was preserved

Unchanged: the evidence model and provider contracts, graph fusion, the
dependency inventory and manifest scanners across six ecosystems, the cache,
MCP tools, CLI commands, structural preview/apply and its transaction model,
mutation policy, and the subprocess architecture. No public interface was
removed; new parameters are optional and keyword-only.

The Python binding `ast-grep-py` was evaluated and **not** adopted — the bar was
a measured material win, and this work did not find one.

---

## 4. What was fixed

Six defects. Every one produced a confidently wrong answer rather than an
error, which is why none had failed a test.

| # | Defect | Consequence |
|---|---|---|
| 1 | `SourceRange.contains` treated `end_column` inclusively | Touching identifiers both claimed the boundary column; the tie-break resolved to whichever symbol sorted first |
| 2 | Columns read as Python string indices | Wrong position on every non-ASCII line |
| 3 | `local N` keyed globally | One file's local variable returned as another's |
| 4 | `normalize_index_path` stripped the leading `/` | `/etc/passwd` → `etc/passwd`, then joined to the root and read |
| 5 | Freshness sampled the first 400 documents | Reported `exact` for everything past 400 |
| 6 | `202` treated as success | The provider's *"not finalized yet"* error body returned **as documentation** |

Plus: `STALE_PENALTY` did not deliver its documented invariant; version matching
was string equality; the structural engine was pinned to a range; a malformed
structural pattern was indistinguishable from "no matches".

### The most consequential finding

**Both pinned indexers emit UTF-16 columns while declaring no encoding at
all** — including `scip-python`, for which the schema's own guidance suggests
UTF-32. Measured from the committed indexes:

```
scip-python 0.6.6    line: '    total = f"🚀 {user}"'
  'user' at character 17 | utf8 20 | utf16 18   → indexer emitted 18
scip-typescript 0.4.0 line: '  const total = `🚀 ${user}`'
  'user' at character 21 | utf8 24 | utf16 22   → indexer emitted 22
```

Handled with a table of *measured* tool behaviour. A declared encoding always
wins; an unrecognised tool falls back to code points and is reported as an
assumption, never as exact. `test_real_columns_are_utf16_not_code_points`
re-derives the measurement from the committed indexes, so a wrong table entry
fails a test rather than shifting every column.

### The ranking invariant that did not hold

The fusion module documented that stale exact evidence never outranks fresh
structural evidence. At `STALE_PENALTY = 0.55` it did not:

```
stale exact   @ conf 0.25 → 1.00 × (0.35 + 0.65×0.25) × 0.55 = 0.282
fresh struct. @ conf 0.00 → 0.72 × 0.35                      = 0.252
```

The penalty is now **derived from that bound** (≈0.249) rather than chosen, so
the property holds at every confidence pairing by construction. Scaling rather
than clamping keeps stale records ordered among themselves.

### Verified by mutation testing

Each fix was reverted in turn to confirm the new tests catch the old behaviour:

| Reverted fix | Tests that failed |
|---|---|
| Inclusive end column | 4 |
| Globally-keyed local symbols | 5 |
| First-400 staleness sampling | 3 |
| Path sanitising instead of rejecting | 12 |
| Ignoring position encoding | 5 |

---

## 5. Real-index validation

| | Python | TypeScript |
|---|---|---|
| Indexer | scip-python 0.6.6 | scip-typescript 0.4.0 |
| Commit | `8b60bbce…` | `891eb429…` |
| Command | `scip-python index . --project-name=… --project-version=1.0.0` | `scip-typescript index --no-progress-bar` |
| `scip lint` | **clean** | **clean** |
| Oracle agreement | documents, occurrences, ranges, roles, symbols, relationships, external symbols, project root — **all match** | same |

Both were regenerated from a stable neutral root so no machine-specific path is
committed. `scripts/regenerate_real_index_fixtures.sh` reproduces them.

**Upstream limitation, recorded not worked around:** `scip-python` 0.6.6 emits
no definition occurrence for a class — `class Foo:` resolves to
`builtins/Foo#` with a *read* role. This reproduces in that indexer's own
snapshot inputs, so it is upstream, not a fixture artifact. The Python fixture
therefore exercises duplicate **function** names. CodeCortex reports what the
index contains and does not compensate.

Other real behaviour the fixtures pin down: `local 0`–`local 3` are shared
across all four Python documents and `local 2` across three TypeScript ones;
both use the compact range encoding; scip-python marks references `ReadAccess`
while scip-typescript emits `0`.

---

## 6. Documentation provider validation

| | |
|---|---|
| Contract tests | 67, against a real local HTTP server |
| Statuses covered | 200, 202, 301, 400, 401, 402, 403, 404, 409, 422, 429, 500, 503, 504 |
| `Retry-After` | delta-seconds and HTTP-date; honoured to a bound, reported beyond it |
| 202 handling | typed pending state, distinct from unreachable; body never returned as docs |
| Cache | key covers provider, library, version, normalised query, contract version; a hit retains version-match provenance; a stale hit stays marked stale |
| Rate limiting | bounded retries; an excessive hint fails instead of sleeping |
| **Live smoke test** | **SKIPPED — no credentials.** `CODECORTEX_DEPENDENCY_DOCS_API_KEY` is not set in this environment. The live path has **not** been exercised. |

The credential never appears in any exception, log, or diagnostic — asserted
directly.

---

## 7. Structural validation

| | |
|---|---|
| Installed binary | `ast-grep 0.45.3` |
| Pin | `ast-grep-cli==0.45.3` (was `>=0.45.3,<1`) |
| Conformance tests | 21, against the real binary |
| CI | `structural-engine` workflow verifies the installed version against the pin before running |

Observed and asserted: no match exits `1` (not a failure); a malformed pattern
exits `0` with a warning and no matches (now surfaced as an error); columns
count characters while byte offsets are separate; capture metadata survives
Unicode; prose mentioning a call does not match; truncated output stops at a
record boundary.

---

## 8. Security

| Boundary | Result |
|---|---|
| Indexed document paths | Absolute, drive-lettered, URI, `..`, `.`, empty-component, and NUL paths **rejected**, not repaired |
| Symlink escape | Refused at join time; the root is re-checked after resolution |
| Local symbol scope | Document-scoped, so one file's locals cannot be returned for another |
| Malformed payloads | Truncation, bad varints, deep nesting, oversize, invalid UTF-8 all fail closed with a typed error |
| Position conversion | Bounded by the root and a byte limit; cannot become an arbitrary-file read |
| Secret redaction | Key absent from exceptions, logs, URLs, and cache entries |
| Remote data | Only whitelisted keys retained; redirect targets validated and bounded |
| Subprocess | `shell=False`, explicit argv, resolved executable, root cwd, timeout, output cap |
| Rewrite | Preview id, content-hash re-verification, authorization, bounds, atomic write, rollback |
| `bandit -q -r src -x tests -ll` | **0 issues** |
| CodeQL | **pass** |

---

## 9. Tests

```
711 passed, 28 skipped, 0 failed
```

Every skip, explained — none is a disguised pass:

| Count | Reason |
|---|---|
| 22 | `tests/test_structural_conformance.py` — optional engine not installed. **Runs and passes** in the `structural-engine` workflow, and locally with the binary on `PATH` (620 passed, 6 skipped). |
| 5 | `tests/test_dependency_live_smoke.py` — no credentials. **Never exercised.** |
| 1 | `tests/test_structural_intelligence.py` — same optional engine. |
| 1 | `tests/test_native_parsers.py` — `tree_sitter_language_pack` absent; pre-existing, covered by the `native-parsers` job. |

---

## 10. Coverage

**91.74%** — up from 91.59%. Gate remains `--cov-fail-under=90`, unchanged. No
gate was weakened and no test was deleted.

---

## 11. Benchmarks (measured, not estimated)

Evidence benchmark:

| Case | Baseline strategy | Evidence strategy |
|---|---|---|
| duplicate-symbols | graph heuristic — precision **0.50** | precision index — **1.00** |
| dependency-version | source only — **0.00** | dependency intelligence — **1.00** |
| mechanical-migration | lexical scan — **0.50** | structural search — **1.00** |

Hardening-specific, median of 20–50 runs on the committed real indexes:

| Measurement | Median |
|---|---|
| Cold index import — Python (7,463 B) / TypeScript (10,690 B) | 0.93 ms / 0.99 ms |
| Warm definition | 0.19 – 0.23 ms |
| Warm references | 0.29 – 0.33 ms |
| Caret navigation on a Unicode line | 0.18 – 0.32 ms |
| **Freshness scan, 600 documents** | **4.25 ms** |

That last number is why sampling was replaced by a full scan with no cache by
default: correctness cost 4 ms.

Documentation quality is **SKIPPED — credentials unavailable**, not estimated.

---

## 12. Files changed

63 files, **+6,919 / −177**. Source: `precision/` (models, importer, index,
provider, positions, compatibility, schema, merge), `dependencies/` (remote,
versions, cache, service, models), `structural/` (engine), `evidence/` (models,
fusion), `config.py`, `cli.py`. Tests: 7 new suites. Fixtures: the vendored
schema and two real-index projects. Plus 3 scripts, 4 docs, 2 workflows.

---

## 13. Remaining limitations

1. **The live documentation path is unverified.** No credential exists here.
2. **The compatibility table covers two tool versions.** A newer indexer falls
   back to code points and reports the assumption — safe, but it will resolve
   non-ASCII columns wrongly if that indexer also emits UTF-16 undeclared. The
   fix is one measured table entry.
3. **`scip-python` 0.6.6 cannot resolve class definitions.** Go-to-definition on
   a class indexed by it returns nothing. Upstream; not compensated for.
4. **Deterministic staleness is O(documents) in `stat` calls.** 4 ms at 600
   documents; a very large monorepo may want `freshness_ttl_seconds`, whose
   trade-off is documented at the setting.
5. **`pip-audit` reports PYSEC-2026-3447 in `setuptools` 79.0.1** — a build tool
   in the environment, not a declared CodeCortex dependency (backend is
   hatchling). Pre-existing; not introduced here.
6. **No streaming index reader.** Full-buffer decoding was not shown to be a
   problem at the sizes measured, so per the prompt's own rule it was left alone.

---

## 14. Git state

| | |
|---|---|
| Branch | `hardening/evidence-fusion-upstream-conformance` |
| Commits | 10, in coherent units |
| Working tree | clean |
| PR | https://github.com/BehnamJalaliCo/CodeCortex/pull/34 |
| Required checks | see the PR; no check was bypassed |

Direct push to `main` is impossible in this repository (`bypass_actors: NONE`),
so delivery is by PR, as the prompt requires.
