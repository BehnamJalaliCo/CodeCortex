# Evidence Fusion

CodeCortex answers a coding agent's question by combining several kinds of
evidence and telling the agent, for every result, **how that result was
established**. The guiding rule is unchanged: *evidence before confidence*.

```
repository source truth
        + syntax/AST evidence
        + compiler/indexer-resolved symbol evidence
        + graph relationships
        + Git and pull-request history
        + version-aware dependency documentation
        + structural code matches
        + project and team memory
        + validation results
                 ↓
   ranked evidence with provenance
                 ↓
     query-specific compact context
```

Three optional layers feed this pipeline: **Precision Code Intelligence**,
**Dependency Intelligence**, and **Structural Search / Structural Rewrite**.
All three are optional. A clean CodeCortex installation with no network access,
no precision index, and no structural engine works exactly as it did before —
the layers add stronger evidence above the existing behavior, they do not
replace it.

## The evidence record

Every layer emits the same typed record, so nothing has to invent its own
metadata shape:

| Field | Meaning |
| --- | --- |
| `kind` | definition, reference, implementation, call, import, type relation, documentation, structural match, Git history, memory, validation |
| `provider` | which layer produced it |
| `provenance` | how it was produced, e.g. `precision-index`, `structural-match` |
| `trust` | categorical strength — see the table below |
| `path`, `start_line`, `start_column`, `end_line`, `end_column` | one-based location |
| `symbol`, `target_symbol` | resolved identity, not just a name |
| `confidence` | numeric, bounded to `[0, 1]` |
| `exact` | true only for fresh compiler/indexer-resolved evidence |
| `stale` | true when the evidence came from an index that no longer matches the source |

`exact` and `stale` are mutually exclusive by construction: a record cannot
claim the exact tier unless it is fresh, and the model rejects any attempt to
do so.

## Trust tiers

The tier is what agents should read. The numeric score exists only to order
results and fill a token budget; it is a ranking device, not a calibrated
probability.

| Trust tier | Produced by |
| --- | --- |
| `exact` | a fresh compiler/indexer-resolved occurrence |
| `near_exact` | a live language-server resolution |
| `structural` | a parsed-syntax match, or version-matched documentation |
| `inferred_high` | a strong graph relationship, or exact evidence now marked stale |
| `inferred` | a heuristic cross-file relationship |
| `weak` | a lexical coincidence |

Four properties are enforced in code rather than documented-and-hoped-for, and
each is checked exhaustively across the tier and confidence space:

- **Stale exact evidence never outranks fresh structural evidence.** The stale
  multiplier is derived from that bound rather than chosen: stale scores are
  scaled by a factor strictly below the weakest score any fresh structural
  record can reach, so the property holds at every confidence pairing instead
  of at most of them. Scaling rather than clamping keeps stale records ordered
  among themselves, so a stale exact result still beats a stale guess.
- **Exact and stale cannot both be set.** Exactness is a claim about the
  present. A record that is out of date cannot also be exact, and the model
  rejects any attempt to declare both.
- **A provider cannot elevate its own trust tier.** A tier describes *how* a
  result was obtained, so the ceiling belongs to the method: only an index
  produced by a compiler or language analyser may claim `exact`; an AST match
  is `structural` however confident the engine is; retrieved documentation is
  evidence about a dependency's API rather than an exact resolution of a
  repository symbol.
- **Weaker evidence is superseded, never erased.** When two providers point at
  the same location, the stronger record is kept and the weaker one is recorded
  under `metadata.superseded`, so conflicts stay visible for debugging.

## What the layers add

### Precision Code Intelligence

Reads a compiler- or indexer-produced index of the repository and answers
position-based questions exactly: *what is defined here*, *what references
this*, *what implements this*. Because it resolves by symbol identity rather
than by name, it distinguishes two packages that export the same class name — a
case where name matching is a coin flip.

Exact edges are also fused into the project graph, where impact analysis weighs
them more heavily than inferred ones and reports the mix.

**Fallback:** no index, an unreadable index, an unsupported schema version, or
a document path that violates the protocol all produce an `unavailable`
provider report naming the reason, and CodeCortex continues with structural and
heuristic resolution. A **stale** index is not discarded: its results are
returned marked `stale`, ranked below fresh evidence, with reindex guidance.

**Positions.** Occurrence columns are not character offsets. An index stores
them in whatever code unit the indexer declared — bytes, UTF-16 code units, or
code points — and the same position is a different number in each. CodeCortex
converts at the boundary and reports code points throughout. Every real indexer
tested omits the declaration and emits UTF-16, so an undeclared encoding is
resolved from a table of *measured* tool behaviour; an unrecognised tool falls
back to code points and its positions are reported as an assumption rather than
as exact. Ranges are half-open, matching the protocol: a caret at a range's end
column belongs to the next token.

**Staleness** is deterministic. Every indexed document is checked, not a
sample, because a sampled scheme reports `exact` for exactly the files it did
not look at. The check calls `stat` only — nothing is hashed — and costs about
4 ms across 600 documents.

**Local symbols** are scoped to the document that declares them, as the
protocol requires. Real indexers restart these identifiers per file, so a
globally-keyed lookup would return one file's local variable as another's.

### Dependency Intelligence

Reads dependency manifests and lockfiles across Python, Node, Rust, Go, JVM,
and .NET, and keeps the **declared constraint** and the **resolved version**
separate. `^15.0.0` is not an answer to "which API does this repository run";
`15.4.3` is.

Given a resolved version, an optional documentation provider can return
version-aware documentation for it.

**Version matching** distinguishes an exact answer from a fallback. A
lockfile's `15.1.8` and a provider label of `v15.1.8` are the same release and
are matched; `2.0.0-rc.1` and `2.0.0` are not, and are never folded together.
Only a version the provider actually publishes is pinned in the request, and
whether the result is version-exact is recorded on the resolution — and kept in
the cache, so a cached fallback answer is not mistaken later for a cached exact
one.

**Fallback:** the documentation provider is disabled by default. When it is
disabled, uncredentialed, offline, rate-limited, or returns something
unexpected, CodeCortex returns the local manifest facts plus an explicit
docs-unavailable state. It never fabricates documentation. A library the
provider has accepted but not finished preparing is reported as pending rather
than as missing, and its explanatory response body is never returned as that
library's documentation. Cached documentation may be served while offline,
always marked `stale`.

### Structural Search and Structural Rewrite

Finds code by syntax rather than by text — `old_api($X)` matches the calls and
not the comment that mentions them — and turns that into guarded migrations.

The engine is pinned to an exact version rather than a range, because
CodeCortex parses its structured output and that output shape is part of the
integration contract. `cortex doctor` reports an installed build that is not
the verified one instead of showing it as plainly available.

A pattern the engine cannot parse exits successfully with a warning and no
matches. CodeCortex surfaces that warning as an error, so an invalid pattern is
distinguishable from a pattern that legitimately found nothing — and so a
malformed pattern can never silently drive a rewrite.

**Fallback:** when the engine is not installed, structural capabilities report
`unavailable` and CodeCortex falls back to lexical and symbol search. It does
not claim equivalent precision for the fallback.

## The rewrite lifecycle

A structural rewrite is never one opaque destructive call:

1. parse the request and validate the pattern and replacement;
2. structural search produces the match set;
3. limits are enforced (files, matches, changed bytes);
4. impact analysis computes affected symbols, tests, and a risk score;
5. a **preview** is persisted with the SHA-256 of every file it was computed
   from, plus an expiry;
6. apply requires that preview's id, mutation authorization, and configuration
   that permits application;
7. every file's current hash is re-verified against the preview — a file that
   changed in the meantime aborts the transaction;
8. files are replaced atomically, and any write failure restores the originals;
9. changed files are reindexed;
10. validation runs;
11. post-change impact analysis reports residual risk;
12. the result reports files changed, matches applied, validation, and rollback
    state — including partial failure, which is never hidden.

## Routing

The router classifies which optional layers a request should consult and
records the reason on the route plan. Local layers are proposed freely; the
remote documentation layer is proposed only when the question is actually about
a third-party dependency.

| Request | Layers |
| --- | --- |
| "Where is AuthService defined?" | precision |
| "Who calls refresh_token?" | precision |
| "What changed in this file?" | none — Git intelligence answers it |
| "Is this method deprecated in our installed version?" | dependency documentation |
| "Find all usages of this old API shape." | structural |
| "Migrate all old API calls to the new shape." | precision + dependency + structural, then impact, preview, and validation |

Mutation is never routed automatically: it always requires explicit
authorization.

## Configuration

All three layers are configured in `.codecortex/config.json` and all are safe
to omit.

```json
{
  "precision_index": {
    "enabled": true,
    "path": ".codecortex/precision/index.cortexidx",
    "auto_generate": false,
    "generator_command": []
  },
  "dependency_docs": {
    "enabled": false,
    "api_key_env": "CODECORTEX_DEPENDENCY_DOCS_API_KEY",
    "cache_ttl_seconds": 86400,
    "serve_stale_when_offline": true
  },
  "structural": {
    "enabled": true,
    "command": null,
    "max_rewrite_files": 50,
    "max_rewrite_matches": 500,
    "max_rewrite_bytes": 1048576,
    "preview_ttl_seconds": 1800,
    "allow_apply": true
  }
}
```

A precision index is discovered automatically at
`.codecortex/precision/index.cortexidx`, `index.cortexidx`, `.codecortex/index.cortexidx`, or
`build/index.cortexidx` when no path is configured. A malformed section falls back
to defaults rather than breaking local operation.

## Diagnostics

`cortex doctor` reports each layer's state without touching repository code:

```
precision intelligence   available | stale | unavailable | disabled
dependency docs          available | credentials missing | disabled
structural engine        available | unavailable
```

`cortex precision-status` gives the detail: index path, document, symbol, and
occurrence counts, the indexer that produced it, and the staleness reason.

## Security

- **Subprocess.** Every external process is invoked with an explicit argument
  vector and a resolved absolute executable — never `shell=True`, never a shell
  string. Runtime is bounded by a timeout and captured output by a byte cap.
  CodeCortex never downloads an executable on your behalf.
- **Paths.** Every path is resolved and required to stay inside the project
  root. Parent traversal, absolute escapes, and symlink escapes are rejected,
  and a match reported outside the root is dropped rather than acted on.
- **Network.** The only outbound capability is the documentation provider, and
  it is disabled by default. It sends the library name, the resolved version,
  and your question — never source, paths, secrets, Git history, or memory.
  Responses are size-capped, schema-validated, and time-bounded, with a small
  bounded retry budget.
- **Credentials.** The API key is read only from a configured environment
  variable. It is never written to project state or task traces, and anything
  resembling a credential is redacted from diagnostics.
- **Rewrites.** Preview required, content-hash verified, limits enforced,
  atomic writes, rollback on failure, audit event on apply.
- **MCP.** Every tool declares a strict schema with `additionalProperties:
  false`. `cortex_rewrite_apply` is on the mutating surface only, so remote
  deployments gate it through the existing mutation-principal policy.
