# CodeCortex Production Execution Ledger

This file is the persistent execution contract for the production roadmap. A task is `DONE` only when its required implementation, integration, testing, and hardening evidence is recorded here.

Baseline branch: `main`
Baseline commit: `e4317686e4190b30f72880bd2422aafac669213e`
Execution branch: `codex/production-roadmap`
Baseline date: 2026-09-01

# Execution Board

| ID | Milestone | Status | Priority | Depends On | Tests |
|---|---|---|---|---|---|
| CC-0510 | Baseline & Correctness | IN_PROGRESS | P0 | — | PARTIAL |
| CC-0520 | Runtime Reliability | TODO | P0 | CC-0510 | NOT RUN |
| CC-0530 | State & Concurrency | TODO | P0 | CC-0510 | NOT RUN |
| CC-0540 | Security Boundaries | TODO | P0 | CC-0510 | PARTIAL |
| CC-0610 | Application Service Layer | TODO | P0 | CC-0510 | NOT RUN |
| CC-0620 | HTTP API | TODO | P0 | CC-0610 | NOT RUN |
| CC-0630 | Project Registry | TODO | P0 | CC-0610 | NOT RUN |
| CC-0640 | Frontend Foundation | TODO | P0 | CC-0620 | NOT RUN |
| CC-0650 | Context Lab | TODO | P0 | CC-0620, CC-0640 | NOT RUN |
| CC-0660 | Graph Explorer | TODO | P0 | CC-0620, CC-0640 | NOT RUN |
| CC-0670 | Traces / Overview / Projects | TODO | P1 | CC-0630, CC-0640 | NOT RUN |
| CC-0700 | Retrieval V3 | TODO | P0 | CC-0610 | NOT RUN |
| CC-0800 | Adaptive Router V2 | TODO | P0 | CC-0610, CC-0700 | NOT RUN |
| CC-0900 | Agent Gateway | TODO | P0 | CC-0620, CC-0540 | NOT RUN |
| CC-1000 | PR Intelligence V2 | TODO | P1 | CC-0610, CC-0700 | NOT RUN |
| CC-1100 | Team / Organization | TODO | P0 | CC-0540, CC-0620 | NOT RUN |
| CC-1200 | Distributed Control | TODO | P1 | CC-0540, CC-0620 | NOT RUN |
| CC-1300 | Memory Control | TODO | P1 | CC-0620, CC-1100 | NOT RUN |
| CC-1400 | Architecture Control | TODO | P1 | CC-0620 | NOT RUN |
| CC-1500 | Benchmark & Quality Control | TODO | P1 | CC-0620, CC-0700 | NOT RUN |
| CC-1600 | Settings | TODO | P1 | CC-0620 | NOT RUN |
| CC-1700 | Live Events | TODO | P1 | CC-0620 | NOT RUN |
| CC-1800 | 1.0 Validation & Release Readiness | TODO | P0 | CC-0500..CC-1700 required scope | NOT RUN |

## Completion dimensions

For each capability the ledger tracks four dimensions:

| Dimension | Meaning |
|---|---|
| Implemented | The behavior exists behind typed contracts. |
| Integrated | Real entry points use the shared implementation. |
| Tested | Required focused/integration/invariant checks pass. |
| Hardened | Security, concurrency, bounds, errors, and observability required for the task are verified. |

# Verified Baseline

## Repository audit summary

The default branch already contains a substantial alpha implementation. The current implementation includes CLI entry points, gateway/router/orchestrator layers, capability engines, repository and incremental indexing, symbol/language intelligence, relationship graphs, Retrieval V2, context budgeting/slicing/tokenization, cache/state, memory/team memory, Git and PR intelligence, architecture inference/drift, tracing/telemetry, evaluation/benchmarks, agent feedback/integrations, workspace federation, semantic editing, a read-oriented Observatory/dashboard, remote MCP, distributed workers/coordination/memory/vector abstractions, organization policy, Docker, CI, security workflows, and broad tests.

The audit also confirms important production gaps:

- There is no shared `services/` application layer or production `control_plane/` HTTP API yet.
- There is no packaged React/TypeScript Control Plane frontend yet.
- The existing Observatory is not the required product Control Plane and must not become a monolith.
- Retrieval V2 exists, but the requested persistent lexical/BM25 + explainable multi-signal Retrieval V3 pipeline is not complete.
- Existing incremental graph tests cover dirty/dependent reparsing and duplicate method IDs, but not the full required mutation/resolution equivalence matrix.
- Current roadmap reporting is checkbox-only and does not distinguish implemented/integrated/tested/hardened evidence.
- The main CI run reports success even though its Python 3.13 coverage log reports `89.76%` and `FAIL Required test coverage of 90% not reached`. This is a false-green quality-gate condition to fix without reducing the threshold.
- `mypy src/codecortex` is configured with strict typing but is not currently executed in the main CI workflow.
- The baseline pytest log reports repeated `ResourceWarning` messages for unclosed SQLite connections; database lifecycle ownership needs hardening.

## Baseline commands and observed evidence

Direct checkout in the execution container is unavailable because outbound GitHub DNS/network access is not available there. Therefore no local command is reported as passed. Baseline execution evidence is taken from GitHub Actions for exact `main@e4317686e4190b30f72880bd2422aafac669213e` and is explicitly distinguished from commands that were not run.

| Validation | Exact command / workflow action | Baseline result |
|---|---|---|
| Ruff | `ruff check .` | PASS in CI |
| Pytest, Python 3.13 | `pytest -q --cov=codecortex --cov-report=xml --cov-report=term-missing --cov-fail-under=90` | 181 passed, 1 skipped; coverage gate text reports FAIL |
| Coverage | same command | 89.76%, below required 90%; MUST FIX |
| Python 3.11 / 3.12 tests | `pytest -q` | PASS in CI |
| Invariant suite | configured focused pytest file set in `.github/workflows/ci.yml` | PASS in CI |
| Mypy | `mypy src/codecortex` | NOT RUN by current CI |
| Build | `python -m build` | PASS in package job |
| Twine | `python -m twine check dist/*` | PASS in package job |
| Wheel smoke | install wheel + `cortex --help`, `cortex version`, `cortex-remote --help` | PASS |
| Docker | `.github/workflows/docker.yml` | PASS at baseline commit |
| Security | `.github/workflows/security.yml` | PASS at workflow level |
| CodeQL | `.github/workflows/codeql.yml` | PASS at workflow level |
| Backend conformance | dedicated workflow | PASS at workflow level |
| Native parser providers | dedicated workflow | PASS at workflow level |

Baseline rule: the green aggregate CI status is **not** accepted as evidence that the coverage requirement passed. CC-0515 owns correction of this inconsistency.

# Dependency Order

Critical path:

```text
CC-0510 Baseline & correctness
  -> CC-0520 Runtime reliability
  -> CC-0530 State/concurrency
  -> CC-0540 Security boundaries
  -> CC-0610 Shared services
  -> CC-0620 API + CC-0630 Registry
  -> CC-0640 Frontend
  -> CC-0650 Context Lab + CC-0660 Graph Explorer + CC-0670 observability pages
  -> CC-0700 Retrieval V3
  -> CC-0800 Router V2
  -> CC-0900 Agent Gateway
  -> CC-1000 PR Intelligence V2
  -> CC-1100 Team/Organization
  -> CC-1200 Distributed Control
  -> CC-1300/1400/1500/1600/1700 control surfaces
  -> CC-1800 repository-wide 1.0 validation
```

Independent tasks within a milestone can run once their explicit dependencies are done. Optional live-provider verification can remain `BLOCKED` while interface, mocked tests, and independent work continue.

# EPIC CC-0500 — Foundation & Stabilization

## MILESTONE CC-0510 — Baseline & Correctness

### CC-0511 — Audit repository and establish verified baseline

Status: DONE

Priority: P0

Milestone: CC-0510

Depends on:
- —

Goal:
Establish an evidence-backed baseline and a persistent execution ledger before feature work.

Implementation:
- inspect repository tree, README, ROADMAP, package metadata, CLI/runtime, intelligence subsystems, tests, Docker, and workflows
- record exact baseline commit and workflow evidence
- create `docs/IMPLEMENTATION_PLAN.md` as the first repository artifact
- record discrepancies instead of converting them to success

Acceptance criteria:
- [x] baseline commit is fixed and recorded
- [x] existing architecture and major subsystem inventory is recorded
- [x] exact validation evidence and known non-runs are distinguished
- [x] task hierarchy, dependencies, acceptance criteria, and board exist

Validation:
- unit tests: not applicable to documentation-only baseline task
- integration tests: GitHub Actions baseline inspected
- security tests: security workflow status inspected
- type checks: current CI absence recorded
- benchmark/performance checks: no new claims; existing workflow presence audited

Result:
Baseline established at `main@e4317686e4190b30f72880bd2422aafac669213e`. False-green coverage and SQLite resource warnings were discovered and assigned follow-up tasks.

Commit:
Filled after this ledger commit is created.

### CC-0512 — Complete incremental graph equivalence mutation matrix

Status: IN_PROGRESS

Priority: P0

Milestone: CC-0510

Depends on:
- CC-0511

Goal:
Prove that incremental graph updates are semantically equivalent to full rebuilds across required definition, caller, ambiguity, and cross-file mutations.

Implementation:
- extend `tests/test_incremental_graph.py` and/or `tests/test_invariant_suite.py`
- use canonical node/edge comparison helpers, not incidental object ordering
- cover added/removed/renamed definitions, changed callers, unchanged callers toward changed targets, unresolved references becoming resolvable, ambiguous symbols, duplicate methods, and cross-file dependency changes
- if a scenario fails, fix owning indexing/resolution layer before marking DONE

Subtasks:
- CC-0512.1 add reusable full-vs-incremental assertion harness
- CC-0512.2 test added, removed, and renamed definitions
- CC-0512.3 test changed and unchanged callers
- CC-0512.4 test unresolved-to-resolved and ambiguous references
- CC-0512.5 test duplicate methods and cross-file dependency changes

Acceptance criteria:
- [ ] every required mutation class has a regression/invariant test
- [ ] `FullGraph(after) == IncrementalGraph(before + same mutations)` for all cases
- [ ] failures are fixed in the owning layer, not masked in tests

Validation:
- unit tests: focused incremental graph tests
- integration tests: invariant suite
- security tests: n/a
- type checks: `mypy src/codecortex` after changes if available in CI
- benchmark/performance checks: ensure no test-driven production change introduces a full-rebuild-per-mutation path

Result:
Pending.

Commit:
Pending.

### CC-0513 — Harden relationship re-resolution and ambiguous symbol resolution

Status: TODO

Priority: P0

Milestone: CC-0510

Depends on:
- CC-0512

Goal:
Make relationship resolution deterministic when targets are added, removed, renamed, duplicated, or become ambiguous.

Implementation:
- inspect indexing relationship extraction/resolution and symbol identity rules
- invalidate/re-resolve dependent references when the candidate target set changes
- preserve qualified identities for duplicate method names
- add deterministic ambiguity handling and provenance where supported

Acceptance criteria:
- [ ] stale edges are removed after target deletion/rename
- [ ] previously unresolved references resolve after a target is added
- [ ] ambiguous references do not silently bind to an arbitrary target
- [ ] qualified duplicate methods remain distinct

Validation:
- unit tests: resolver unit cases
- integration tests: CC-0512 invariant matrix
- security tests: malicious/invalid symbol text does not escape path/project boundaries
- type checks: strict mypy
- benchmark/performance checks: re-resolution bounded to affected/dependent files

Result:
Pending.

Commit:
Pending.

### CC-0514 — Verify config precedence and hard context limits

Status: TODO

Priority: P0

Milestone: CC-0510

Depends on:
- CC-0511

Goal:
Make configuration precedence explicit and guarantee `context_tokens <= hard_context_limit` on every path.

Implementation:
- audit config sources and actual precedence
- centralize validation for context budget/hard limit/tokenizer settings
- add boundary/property tests for CLI/MCP/service callers
- document only implemented precedence

Acceptance criteria:
- [ ] precedence is deterministic and tested
- [ ] invalid negative/oversized limits are rejected safely
- [ ] hard limit cannot be exceeded after dedupe/slicing/serialization
- [ ] compatibility aliases retain documented behavior

Validation:
- unit tests: config + budget tests
- integration tests: context pipeline entry points
- security tests: malformed config and oversized values
- type checks: strict mypy
- benchmark/performance checks: no unbounded tokenization loop

Result:
Pending.

Commit:
Pending.

### CC-0515 — Restore trustworthy CI quality gates

Status: TODO

Priority: P0

Milestone: CC-0510

Depends on:
- CC-0512

Goal:
Make CI fail when required coverage/type quality fails, without lowering the 90% coverage threshold.

Implementation:
- make coverage threshold failure propagate reliably
- add `mypy src/codecortex` to main CI
- close meaningful coverage debt with behavioral tests, not exclusions or threshold reduction
- keep package, Windows, invariant, and Codecov behavior intact

Subtasks:
- CC-0515.1 reproduce/guard false-green coverage behavior in workflow
- CC-0515.2 add strict mypy CI step
- CC-0515.3 raise measured behavioral coverage to at least 90%
- CC-0515.4 record exact post-fix CI evidence

Acceptance criteria:
- [ ] coverage below 90 causes a failing quality gate
- [ ] measured coverage is >= 90%
- [ ] strict mypy is green in CI
- [ ] no broad typing suppressions or coverage exclusions are introduced

Validation:
- unit tests: full pytest suite
- integration tests: invariant CI job
- security tests: existing security workflows remain green
- type checks: `mypy src/codecortex`
- benchmark/performance checks: n/a

Result:
Pending.

Commit:
Pending.

## MILESTONE CC-0520 — Runtime Reliability

### CC-0521 — Isolate engine health and execution failures

Status: TODO
Priority: P0
Milestone: CC-0520
Depends on:
- CC-0510
Goal:
Prevent one unhealthy engine/backend from poisoning unrelated capabilities or the whole request.
Implementation:
- audit orchestrator, engine health, backend manager/session pool
- define typed failure categories and per-engine health state
- isolate failures and preserve partial safe results where contracts allow
Acceptance criteria:
- [ ] unhealthy engine does not mark unrelated engine unhealthy
- [ ] safe structured failure category is returned
- [ ] health recovery is deterministic and tested
Validation:
- unit tests: engine health/failure tests
- integration tests: gateway -> router -> orchestrator with one failing engine
- security tests: raw exceptions/secrets are not returned
- type checks: strict mypy
- benchmark/performance checks: failure path bounded
Result:
Pending.
Commit:
Pending.

### CC-0522 — Enforce timeouts, retries, and cancellation propagation

Status: TODO
Priority: P0
Milestone: CC-0520
Depends on:
- CC-0521
Goal:
Bound execution and propagate cancellation through orchestrator, backends, MCP, and distributed work.
Implementation:
- introduce/verify explicit timeout budget contracts
- retry only classified transient/idempotent work with bounded attempts
- propagate cancellation to sessions/workers where supported
Acceptance criteria:
- [ ] hung engine cannot block indefinitely
- [ ] retries are bounded and observable
- [ ] cancellation stops downstream work and does not commit stale completion
Validation:
- unit tests: timeout/retry state machine
- integration tests: cancelled request path
- security tests: attacker cannot force unbounded retry
- type checks: strict mypy
- benchmark/performance checks: timeout overhead measured where material
Result:
Pending.
Commit:
Pending.

### CC-0523 — Stabilize chunk identity and cache integrity

Status: TODO
Priority: P0
Milestone: CC-0520
Depends on:
- CC-0513
Goal:
Guarantee stable chunk IDs and prevent stale/cross-project cache reuse.
Implementation:
- audit chunk identity inputs and cache keys
- include project/revision/config dimensions required for correctness
- make writes atomic and entries bounded
Acceptance criteria:
- [ ] unchanged chunk identity is stable across incremental updates
- [ ] changed content/config invalidates affected cache entries
- [ ] project A cache cannot satisfy project B request
Validation:
- unit tests: identity/cache-key tests
- integration tests: index -> retrieve -> mutate -> retrieve
- security tests: cross-project cache isolation
- type checks: strict mypy
- benchmark/performance checks: cache hit/miss counters and bounded size
Result:
Pending.
Commit:
Pending.

## MILESTONE CC-0530 — State & Concurrency

### CC-0531 — Make mutable state transactional, atomic, and recoverable

Status: TODO
Priority: P0
Milestone: CC-0530
Depends on:
- CC-0510
Goal:
Make persistent mutable state safe under concurrent writers and malformed/interrupted writes.
Implementation:
- audit SQLite/JSON/file state stores
- use transactions/WAL/atomic replace/locks as appropriate
- version state and add recovery/migration paths
Acceptance criteria:
- [ ] concurrent writers do not corrupt state
- [ ] malformed state recovers or fails safely with typed error
- [ ] interrupted writes preserve last valid state
Validation:
- unit tests: state/recovery tests
- integration tests: concurrent writer tests
- security tests: corrupt/adversarial state
- type checks: strict mypy
- benchmark/performance checks: no global full-store rewrite on hot paths where avoidable
Result:
Pending.
Commit:
Pending.

### CC-0532 — Harden memory concurrency and synchronization

Status: TODO
Priority: P0
Milestone: CC-0530
Depends on:
- CC-0531
Goal:
Prevent lost updates and cross-workspace leakage in project/team/distributed memory.
Implementation:
- audit revision/conflict semantics
- add atomic revision updates and deterministic merge/conflict handling
- preserve actor/provenance metadata
Acceptance criteria:
- [ ] concurrent writes do not silently lose data
- [ ] revisions are monotonic/validated
- [ ] workspace isolation holds during search/sync
Validation:
- unit tests: revision/conflict tests
- integration tests: multi-writer and sync tests
- security tests: cross-workspace access
- type checks: strict mypy
- benchmark/performance checks: bounded sync batches
Result:
Pending.
Commit:
Pending.

### CC-0533 — Close SQLite resource lifecycle leaks

Status: TODO
Priority: P1
Milestone: CC-0530
Depends on:
- CC-0531
Goal:
Eliminate unclosed SQLite connection warnings and define connection ownership/lifecycle.
Implementation:
- identify baseline `ResourceWarning` sources
- add context-managed/explicit close semantics and test teardown
- preserve pooling/concurrency behavior
Acceptance criteria:
- [ ] focused tests run without unclosed-SQLite `ResourceWarning`
- [ ] connection lifecycle is explicit
- [ ] no use-after-close regression
Validation:
- unit tests: affected stores
- integration tests: repeated create/use/close cycles
- security tests: n/a
- type checks: strict mypy
- benchmark/performance checks: no connection churn regression
Result:
Pending.
Commit:
Pending.

## MILESTONE CC-0540 — Security Boundaries

### CC-0541 — Enforce organization role invariants

Status: TODO
Priority: P0
Milestone: CC-0540
Depends on:
- CC-0531
Goal:
Prevent organization takeover, owner escalation, and workspace-policy bypass.
Implementation:
- audit OrganizationPolicyStore and role mutation paths
- enforce owner/admin/member/viewer authority transitions transactionally
- unify workspace/tool authorization checks
Acceptance criteria:
- [ ] duplicate org creation cannot cause takeover
- [ ] admin cannot self-escalate or grant owner without owner authority
- [ ] non-owner cannot modify owner and last owner cannot be removed
- [ ] unauthorized tool/workspace access is denied
Validation:
- unit tests: role transition table
- integration tests: org/workspace policy flows
- security tests: takeover/escalation/isolation matrix
- type checks: strict mypy
- benchmark/performance checks: authorization lookup bounded/indexed
Result:
Pending.
Commit:
Pending.

### CC-0542 — Enforce authenticated worker identity and fencing

Status: TODO
Priority: P0
Milestone: CC-0540
Depends on:
- CC-0531
Goal:
Reject worker spoofing, stale leases, stale completion, and duplicate claims.
Implementation:
- bind worker principal to authenticated identity rather than caller-supplied `node_id`
- use lease/fencing token state transitions atomically
- recover safely after crash/restart/reassignment
Acceptance criteria:
- [ ] competing claims produce one valid owner
- [ ] duplicate node IDs cannot impersonate principal
- [ ] old fencing token cannot heartbeat/complete after reassignment
- [ ] lease expiry/retry/crash recovery is tested
Validation:
- unit tests: fencing state machine
- integration tests: coordinator/workers
- security tests: spoof/stale-token matrix
- type checks: strict mypy
- benchmark/performance checks: queue claim path bounded
Result:
Pending.
Commit:
Pending.

### CC-0543 — Harden remote MCP authentication and tool authorization

Status: TODO
Priority: P0
Milestone: CC-0540
Depends on:
- CC-0541
Goal:
Require safe authentication for remote/non-loopback MCP and enforce per-principal tool policy.
Implementation:
- preserve documented trusted-local mode only on loopback
- require auth for remote binds unless explicit dangerous-dev flag
- use random credentials stored as digests; plaintext shown once when needed
- validate arguments, body limits, paths, and tool permissions
Acceptance criteria:
- [ ] remote unauthenticated access is denied by default
- [ ] malformed/oversized MCP requests fail safely
- [ ] unauthorized principal never receives or invokes unauthorized tool
- [ ] credentials are not logged or stored in plaintext
Validation:
- unit tests: auth/authz and schema validation
- integration tests: remote MCP client/server
- security tests: malformed MCP, token misuse, unauthorized mutation
- type checks: strict mypy
- benchmark/performance checks: auth overhead bounded
Result:
Pending.
Commit:
Pending.

### CC-0544 — Implement recursive telemetry/tracing secret redaction

Status: TODO
Priority: P0
Milestone: CC-0540
Depends on:
- CC-0510
Goal:
Prevent nested credentials/source secrets from leaking through traces, telemetry, errors, or audit records.
Implementation:
- central recursive redactor for mappings/sequences/models
- cover authorization headers, token/key/password-like fields and configured patterns
- apply before persistence/export/logging
Acceptance criteria:
- [ ] nested secrets are redacted at arbitrary supported depth
- [ ] safe non-secret diagnostics remain useful
- [ ] raw internal exceptions are not exposed externally
Validation:
- unit tests: nested/redaction cases
- integration tests: trace + telemetry + HTTP/MCP error path
- security tests: nested secret regression suite
- type checks: strict mypy
- benchmark/performance checks: redaction handles bounded payloads without pathological recursion
Result:
Pending.
Commit:
Pending.

# EPIC CC-0600 — CodeCortex Control Plane

## MILESTONE CC-0610 — Application Service Layer

### CC-0611 — Define shared application service contracts and dependencies

Status: TODO
Priority: P0
Milestone: CC-0610
Depends on:
- CC-0510
Goal:
Create the single application-service boundary used by CLI, MCP, HTTP, and Web UI without rewriting stable intelligence.
Implementation:
- add `src/codecortex/services/` package and typed service context/errors
- define project/workspace/principal/trace/cancellation request context
- inject existing gateway/router/orchestrator/intelligence dependencies
Acceptance criteria:
- [ ] service contracts are typed and transport-neutral
- [ ] no service imports frontend/HTTP concerns
- [ ] existing CLI/MCP behavior remains compatible
Validation:
- unit tests: service dependency construction
- integration tests: one CLI/MCP path uses or is proven compatible with service contract
- security tests: principal/project scope required for privileged calls
- type checks: strict mypy
- benchmark/performance checks: no duplicated repository scan
Result:
Pending.
Commit:
Pending.

### CC-0612 — Implement ProjectService and project-scoped intelligence facade

Status: TODO
Priority: P0
Milestone: CC-0610
Depends on:
- CC-0611
Goal:
Provide safe project registration/lookup/index/health operations for all transports.
Implementation:
- add `project_service.py`
- delegate indexing/language/git/graph/semantic stats to existing components
- validate path/symlink boundaries and non-destructive unregister semantics
Acceptance criteria:
- [ ] project add/list/get/rename/remove/health are service operations
- [ ] unregister never deletes source code
- [ ] project IDs are stable and project scope enforced
Validation:
- unit tests: project service
- integration tests: register -> index -> health
- security tests: traversal/absolute/symlink escape
- type checks: strict mypy
- benchmark/performance checks: list/health avoid full re-index
Result:
Pending.
Commit:
Pending.

### CC-0613 — Implement GraphService, RetrievalService, and ContextService

Status: TODO
Priority: P0
Milestone: CC-0610
Depends on:
- CC-0611, CC-0514
Goal:
Expose bounded graph, retrieval, and exact context-construction behavior through shared services.
Implementation:
- add typed service modules wrapping existing graph/retrieval/context pipeline
- preserve provenance and hard context limits
- expose explanation data rather than transport-specific blobs
Acceptance criteria:
- [ ] services call existing intelligence instead of duplicating it
- [ ] graph/retrieval outputs are bounded
- [ ] exact selected context chunks and provenance are available
Validation:
- unit tests: service adapters
- integration tests: index -> retrieval/context/graph
- security tests: project isolation and response bounds
- type checks: strict mypy
- benchmark/performance checks: no full graph dump/query scan
Result:
Pending.
Commit:
Pending.

### CC-0614 — Implement trace/agent/PR/memory/architecture/benchmark/worker/organization service adapters

Status: TODO
Priority: P1
Milestone: CC-0610
Depends on:
- CC-0611
Goal:
Provide shared transport-neutral facades for remaining intelligence/administration domains.
Implementation:
- create cohesive service modules by domain
- delegate to existing implementations and preserve authorization/policy boundaries
- avoid a god service or duplicate state stores
Acceptance criteria:
- [ ] each domain has a cohesive typed facade where needed by UI/API
- [ ] mutation operations require principal/scope
- [ ] no duplicate business logic is introduced
Validation:
- unit tests: each adapter
- integration tests: representative service -> core paths
- security tests: unauthorized mutations
- type checks: strict mypy
- benchmark/performance checks: bounded collection calls
Result:
Pending.
Commit:
Pending.

## MILESTONE CC-0620 — HTTP API

### CC-0621 — Create versioned FastAPI application boundary

Status: TODO
Priority: P0
Milestone: CC-0620
Depends on:
- CC-0611, CC-0544
Goal:
Add a production API shell under `/api/v1/` with safe errors, correlation IDs, lifecycle, and optional web dependencies.
Implementation:
- add optional `web` dependency group for FastAPI/Pydantic/Uvicorn as justified
- add `control_plane/app.py`, dependencies, errors, security, schemas
- no raw exception/stack trace exposure
Acceptance criteria:
- [ ] app starts with `web` extra and base package remains usable without it
- [ ] `/api/v1/` routes use typed schemas
- [ ] safe structured errors include correlation ID
- [ ] body/request limits are enforced
Validation:
- unit tests: schema/error handling
- integration tests: TestClient API lifecycle
- security tests: malformed/oversized body, exception leakage
- type checks: strict mypy
- benchmark/performance checks: representative API latency recorded later
Result:
Pending.
Commit:
Pending.

### CC-0622 — Add stable IDs, pagination, and bounded collection schema contracts

Status: TODO
Priority: P0
Milestone: CC-0620
Depends on:
- CC-0621
Goal:
Prevent unbounded HTTP results and establish forward-compatible versioned response contracts.
Implementation:
- shared page/cursor/error/ID schemas
- explicit max page/graph/search sizes
- validate enum/filter fields
Acceptance criteria:
- [ ] all large collections paginate or have explicit hard maxima
- [ ] invalid cursors/limits produce typed 4xx errors
- [ ] stable IDs do not expose unsafe filesystem internals
Validation:
- unit tests: schema bounds
- integration tests: pagination and missing resource
- security tests: extreme limits and cross-project IDs
- type checks: strict mypy
- benchmark/performance checks: page calls bounded
Result:
Pending.
Commit:
Pending.

### CC-0623 — Unify Control Plane auth/authz with organization and remote-access policy

Status: TODO
Priority: P0
Milestone: CC-0620
Depends on:
- CC-0621, CC-0541, CC-0543
Goal:
Apply one authorization policy across Control Plane, MCP, and organization/workspace boundaries.
Implementation:
- request principal dependency
- trusted-local loopback mode; remote auth required by default
- policy checks at service/authorization boundary, not frontend
Acceptance criteria:
- [ ] remote requests require configured authentication by default
- [ ] project/workspace/tool mutations enforce roles/policy
- [ ] frontend cannot bypass authorization by direct state access
Validation:
- unit tests: authorization matrix
- integration tests: HTTP -> service -> policy
- security tests: cross-workspace and privilege escalation
- type checks: strict mypy
- benchmark/performance checks: authz lookup bounded
Result:
Pending.
Commit:
Pending.

## MILESTONE CC-0630 — Project Registry

### CC-0631 — Add versioned persistent project registry and migrations

Status: TODO
Priority: P0
Milestone: CC-0630
Depends on:
- CC-0612, CC-0531
Goal:
Persist registered repositories with explicit schema/version migration and no destructive source ownership.
Implementation:
- local SQLite default using existing state conventions where possible
- project ID, display name, canonical root, timestamps, index metadata
- transactional migrations/backups where required
Acceptance criteria:
- [ ] existing `.codecortex` state remains readable or has tested migration
- [ ] duplicate/canonical path registration is deterministic
- [ ] source deletion is never part of unregister
Validation:
- unit tests: migration/registry CRUD
- integration tests: old state -> migrate -> list
- security tests: path/symlink/cross-project access
- type checks: strict mypy
- benchmark/performance checks: indexed lookup/list
Result:
Pending.
Commit:
Pending.

### CC-0632 — Expose project operations and health/status intelligence

Status: TODO
Priority: P0
Milestone: CC-0630
Depends on:
- CC-0631, CC-0622
Goal:
Expose add/remove registration/rename/list/health/index status/languages/revision/graph/semantic/Git stats.
Implementation:
- API routes backed only by ProjectService
- typed health/stat models with unknown/missing distinct from zero
Acceptance criteria:
- [ ] all requested project fields are available when supported
- [ ] missing metrics remain null/unknown, not fabricated zero
- [ ] endpoints are paginated/bounded and authorized
Validation:
- unit tests: response mapping
- integration tests: API -> service -> index/core
- security tests: unsafe paths/cross-project ID
- type checks: strict mypy
- benchmark/performance checks: project overview does not trigger re-index
Result:
Pending.
Commit:
Pending.

## MILESTONE CC-0640 — Frontend Foundation

### CC-0641 — Add React/TypeScript/Vite build and Python package asset pipeline

Status: TODO
Priority: P0
Milestone: CC-0640
Depends on:
- CC-0621
Goal:
Ship a production-built local-first web frontend so end users do not need Node.js at runtime.
Implementation:
- add frontend workspace with React + TypeScript + Vite
- package compiled assets in Python wheel/container
- keep Node toolchain build-time only
Acceptance criteria:
- [ ] production frontend build is reproducible
- [ ] wheel/container serves compiled assets
- [ ] base Python install behavior is preserved
Validation:
- unit tests: frontend component test foundation
- integration tests: Python app serves built index/assets
- security tests: no baked credentials; safe asset routing
- type checks: `npm run typecheck` plus mypy
- benchmark/performance checks: build asset sizes recorded; no unbounded bundle regression gate yet
Result:
Pending.
Commit:
Pending.

### CC-0642 — Implement Control Plane shell, API client, error/loading states, and test harness

Status: TODO
Priority: P0
Milestone: CC-0640
Depends on:
- CC-0641, CC-0622
Goal:
Create a professional application shell without duplicating backend business rules.
Implementation:
- navigation/layout/API client/query state/error boundaries
- typed generated/manual API contracts aligned with backend schemas
- frontend lint/typecheck/component test scripts
Acceptance criteria:
- [ ] UI has no direct filesystem/SQLite/index access
- [ ] API failures and empty/loading states are usable
- [ ] critical shell tests pass
Validation:
- unit tests: components/API client
- integration tests: mocked API shell
- security tests: no credential persistence beyond intended mechanism
- type checks: npm typecheck + mypy
- benchmark/performance checks: production build
Result:
Pending.
Commit:
Pending.

## MILESTONE CC-0650 — Context Lab

### CC-0651 — Define typed Context Lab explanation models

Status: TODO
Priority: P0
Milestone: CC-0650
Depends on:
- CC-0613, CC-0800 explanation contracts when available
Goal:
Represent query classification, route score breakdown, engine execution, candidates, context processing, final chunks, and trace linkage as typed evidence.
Implementation:
- `ContextLabRequest`, `ContextLabResult`, route/candidate/context/engine explanation models
- missing scores remain optional, never fabricated
Acceptance criteria:
- [ ] every requested explanation field has explicit type/semantics
- [ ] exact final selected chunks preserve provenance
- [ ] sensitive full prompts/source are not persisted by default merely for UI
Validation:
- unit tests: serialization/schema
- integration tests: context service mapping
- security tests: redaction and bounded snippets
- type checks: strict mypy
- benchmark/performance checks: explanation generation bounded
Result:
Pending.
Commit:
Pending.

### CC-0652 — Implement Context Lab execution service and API

Status: TODO
Priority: P0
Milestone: CC-0650
Depends on:
- CC-0651, CC-0623
Goal:
Run a real context-construction request and return evidence for every stage plus a trace ID.
Implementation:
- service orchestration around existing classifier/router/engines/retrieval/context/tracing
- expose base/adjustment/final route scores when implemented
- candidate include/exclude reasons and cache/token reduction metrics
Acceptance criteria:
- [ ] request produces real selected context, not simulated placeholders
- [ ] every execution creates/links a trace
- [ ] hard context limit is enforced
Validation:
- unit tests: stage mapping
- integration tests: API -> service -> core end-to-end
- security tests: unauthorized project access, large query, secret redaction
- type checks: strict mypy
- benchmark/performance checks: latency/token metrics captured
Result:
Pending.
Commit:
Pending.

### CC-0653 — Build Context Lab UI

Status: TODO
Priority: P0
Milestone: CC-0650
Depends on:
- CC-0652, CC-0642
Goal:
Make the complete evidence path inspectable: Query -> Classification -> Route -> Engines -> Candidates -> Context Processing -> Exact Final Context -> Trace.
Implementation:
- typed UI sections/tables with expandable bounded snippets
- route and candidate score components
- trace link
Acceptance criteria:
- [ ] exact query and final selected chunks are visible for the run
- [ ] score/provenance/include-exclude evidence is understandable
- [ ] missing evidence is shown as unavailable, not zero
Validation:
- unit tests: components
- integration tests: API fixture rendering
- security tests: escaped source/snippets; no HTML injection
- type checks: frontend typecheck
- benchmark/performance checks: large bounded candidate set remains responsive
Result:
Pending.
Commit:
Pending.

### CC-0654 — Add Context Lab critical workflow E2E

Status: TODO
Priority: P0
Milestone: CC-0650
Depends on:
- CC-0653, CC-0663, CC-0671
Goal:
Protect the highest-value production workflow end-to-end.
Implementation:
- fixture repo -> register -> index -> Context Lab -> inspect retrieval/final context -> graph -> trace
Acceptance criteria:
- [ ] required E2E path passes without editing source/state manually
- [ ] failures preserve actionable correlation/trace IDs
Validation:
- unit tests: n/a
- integration tests: full workflow
- security tests: run under scoped principal
- type checks: all stacks
- benchmark/performance checks: record actual fixture latency only
Result:
Pending.
Commit:
Pending.

## MILESTONE CC-0660 — Graph Explorer

### CC-0661 — Implement bounded graph neighborhood service

Status: TODO
Priority: P0
Milestone: CC-0660
Depends on:
- CC-0613, CC-0513
Goal:
Return bounded interactive neighborhoods without whole-graph dumps.
Implementation:
- node/depth/edge-kind/node-kind/max-node/max-edge filters
- adjacency/lazy expansion over existing graph representation
- include source position/metadata/impact references where available
Acceptance criteria:
- [ ] max nodes/edges are hard-enforced
- [ ] file/class/function/method/module and supported relationship kinds are filterable
- [ ] cross-repo edges are scoped/authorized
Validation:
- unit tests: neighborhood/bounds
- integration tests: indexed fixture graph
- security tests: cross-project/workspace IDs
- type checks: strict mypy
- benchmark/performance checks: representative neighborhood latency
Result:
Pending.
Commit:
Pending.

### CC-0662 — Expose graph neighborhood API

Status: TODO
Priority: P0
Milestone: CC-0660
Depends on:
- CC-0661, CC-0622
Goal:
Expose `/api/v1/projects/{project_id}/graph/neighborhood` with typed bounded parameters/results.
Implementation:
- request validation, stable node IDs, safe metadata mapping
Acceptance criteria:
- [ ] invalid depth/limits/filter values are rejected
- [ ] missing node/project returns safe typed error
- [ ] no raw filesystem internals leak beyond intended source position
Validation:
- unit tests: API schema
- integration tests: API -> GraphService
- security tests: cross-project node attempt
- type checks: strict mypy
- benchmark/performance checks: API overhead recorded later
Result:
Pending.
Commit:
Pending.

### CC-0663 — Build interactive Graph Explorer UI

Status: TODO
Priority: P0
Milestone: CC-0660
Depends on:
- CC-0662, CC-0642
Goal:
Search, expand, filter, inspect metadata/source/impact using bounded graph fetches.
Implementation:
- choose maintained graph UI library only if it reduces meaningful complexity
- lazy neighborhood expansion, filter controls, node detail panel
Acceptance criteria:
- [ ] no full huge graph request exists
- [ ] user can search a node and expand neighbors
- [ ] impact/source links use backend IDs/contracts
Validation:
- unit tests: controls/state
- integration tests: API fixtures
- security tests: escaped metadata/source text
- type checks: frontend typecheck
- benchmark/performance checks: bounded graph rendering fixture
Result:
Pending.
Commit:
Pending.

## MILESTONE CC-0670 — Traces, Overview, Projects

### CC-0671 — Implement trace list/detail API and UI

Status: TODO
Priority: P0
Milestone: CC-0670
Depends on:
- CC-0622, CC-0544, CC-0642
Goal:
Inspect bounded, redacted major-operation traces including IDs, project, capability, operation, duration, status, failure category, and context metrics.
Implementation:
- TraceService pagination/retention mapping
- trace list/detail API and UI
Acceptance criteria:
- [ ] trace data is redacted before persistence/display
- [ ] retention/list sizes are bounded
- [ ] Context Lab trace IDs resolve to detail
Validation:
- unit tests: trace mapping/redaction
- integration tests: operation -> trace -> API/UI
- security tests: nested secrets
- type checks: both stacks
- benchmark/performance checks: trace list indexed/bounded
Result:
Pending.
Commit:
Pending.

### CC-0672 — Implement Overview and Projects pages

Status: TODO
Priority: P1
Milestone: CC-0670
Depends on:
- CC-0632, CC-0642
Goal:
Show project health/index/language/revision/graph/semantic/Git facts without bypassing services.
Implementation:
- overview aggregates bounded service metrics
- projects add/remove/rename/list and health flows
Acceptance criteria:
- [ ] project management works from UI
- [ ] unregister is clearly non-destructive
- [ ] unknown values are not shown as zero
Validation:
- unit tests: components
- integration tests: project workflow
- security tests: unauthorized mutation
- type checks: both stacks
- benchmark/performance checks: overview avoids hidden re-index
Result:
Pending.
Commit:
Pending.

# EPIC CC-0700 — Retrieval V3

### CC-0710 — Add persistent lexical/BM25 retrieval
Status: TODO
Priority: P0
Milestone: CC-0700
Depends on:
- CC-0613, CC-0523
Goal:
Provide incremental persistent lexical/BM25 candidate generation without repository scans per query.
Implementation:
- versioned lexical index keyed by project/revision/chunk identity
- incremental add/update/delete and bounded top-K query
Acceptance criteria:
- [ ] lexical index persists and updates incrementally
- [ ] deleted/changed chunks do not remain searchable stale
- [ ] query work is bounded by index/top-K rather than full source scan
Validation:
- unit tests: scoring/index updates
- integration tests: index -> mutate -> search
- security tests: project isolation/corrupt index recovery
- type checks: strict mypy
- benchmark/performance checks: lexical latency/candidates examined
Result: Pending.
Commit: Pending.

### CC-0720 — Harden vector retrieval/provider path
Status: TODO
Priority: P0
Milestone: CC-0700
Depends on:
- CC-0613
Goal:
Improve vector provider contracts, health/stats, incremental updates, and explicit scalability boundaries.
Implementation:
- preserve local provider; define optional external provider contract where useful
- version embeddings/provider metadata and health
Acceptance criteria:
- [ ] provider failures are typed/isolated
- [ ] stale embeddings are invalidated by chunk/model identity
- [ ] no claim that local exact O(N) scan scales indefinitely
Validation:
- unit tests: provider conformance
- integration tests: semantic index refresh/query
- security tests: provider config/secret redaction
- type checks: strict mypy
- benchmark/performance checks: actual local vector latency/candidates
Result: Pending.
Commit: Pending.

### CC-0730 — Add symbol-aware candidate ranking
Status: TODO
Priority: P0
Milestone: CC-0700
Depends on:
- CC-0513
Goal:
Rank exact/qualified/near symbol evidence deterministically and explain it.
Implementation:
- symbol match features using existing symbol intelligence
- ambiguity-aware scoring and provenance
Acceptance criteria:
- [ ] exact qualified matches outrank weaker ambiguous matches under defined rules
- [ ] duplicate names preserve distinct identities
- [ ] explanation includes symbol contribution
Validation:
- unit tests: ranking matrix
- integration tests: retrieval fixtures
- security tests: malformed symbol query
- type checks: strict mypy
- benchmark/performance checks: symbol lookup bounded
Result: Pending.
Commit: Pending.

### CC-0740 — Add graph-aware candidate ranking
Status: TODO
Priority: P0
Milestone: CC-0700
Depends on:
- CC-0661
Goal:
Use bounded graph proximity/relationship features in retrieval ranking.
Implementation:
- graph seed/proximity/edge-kind features with bounded expansion
Acceptance criteria:
- [ ] graph contribution is explainable
- [ ] expansion obeys hard node/edge/depth limits
- [ ] no query-wide O(NxE) traversal
Validation:
- unit tests: graph rank features
- integration tests: retrieval + graph fixture
- security tests: project scope
- type checks: strict mypy
- benchmark/performance checks: graph-ranking latency
Result: Pending.
Commit: Pending.

### CC-0750 — Add Git-aware candidate ranking
Status: TODO
Priority: P1
Milestone: CC-0700
Depends on:
- CC-0613
Goal:
Use bounded recency/churn/change-coherence evidence from existing Git intelligence.
Implementation:
- normalized Git feature model with provenance and missing-data semantics
Acceptance criteria:
- [ ] Git signal is optional and cannot erase non-Git evidence by missing-as-zero mistakes
- [ ] malicious refs are validated
- [ ] contribution is explainable
Validation:
- unit tests: feature/scoring cases
- integration tests: Git fixture
- security tests: malicious refs/path arguments
- type checks: strict mypy
- benchmark/performance checks: no full git-history scan per query
Result: Pending.
Commit: Pending.

### CC-0760 — Add memory-aware candidate ranking
Status: TODO
Priority: P1
Milestone: CC-0700
Depends on:
- CC-0532
Goal:
Use authorized project/team memory as evidence with provenance and revision.
Implementation:
- scoped memory candidate generator/ranking feature
Acceptance criteria:
- [ ] only authorized workspace/project memory participates
- [ ] provenance/revision are preserved
- [ ] stale/deleted memory is not retrieved
Validation:
- unit tests: memory scoring
- integration tests: retrieval + memory
- security tests: workspace leakage
- type checks: strict mypy
- benchmark/performance checks: bounded memory candidates
Result: Pending.
Commit: Pending.

### CC-0770 — Implement explainable candidate fusion, reranking, diversity, and deduplication
Status: TODO
Priority: P0
Milestone: CC-0700
Depends on:
- CC-0710, CC-0720, CC-0730, CC-0740, CC-0750, CC-0760
Goal:
Fuse lexical/vector/symbol/graph/Git/memory evidence deterministically and expose score/reason breakdowns.
Implementation:
- typed per-signal score model
- normalization/fusion/rerank/dedupe/diversity pipeline
- preserve include/exclude reasons and provenance
Acceptance criteria:
- [ ] final ranking is deterministic for fixed inputs/config
- [ ] each candidate exposes available signal scores/fused rank/reason
- [ ] missing signals remain missing, not fabricated
- [ ] final context selection obeys hard token limit
Validation:
- unit tests: fusion/ranking/dedupe
- integration tests: multi-signal retrieval -> context
- security tests: untrusted candidate metadata escaped/redacted
- type checks: strict mypy
- benchmark/performance checks: candidates examined and stage latency recorded
Result: Pending.
Commit: Pending.

### CC-0780 — Build Retrieval V3 evaluation and regression gates
Status: TODO
Priority: P0
Milestone: CC-0700
Depends on:
- CC-0770
Goal:
Measure real retrieval quality and latency using repository datasets without inventing results.
Implementation:
- dataset/result schema for Recall@K, Precision@K, MRR, nDCG, latency, candidates, context tokens
- historical artifacts and comparison/regression logic
Acceptance criteria:
- [ ] metrics are computed only when labels permit them
- [ ] missing measurements stay missing
- [ ] baseline and candidate snapshot can be compared reproducibly
Validation:
- unit tests: metric formulas
- integration tests: evaluation runner fixture
- security tests: dataset paths scoped
- type checks: strict mypy
- benchmark/performance checks: actual artifacts persisted
Result: Pending.
Commit: Pending.

# EPIC CC-0800 — Adaptive Router V2

### CC-0810 — Define typed contextual routing feature model
Status: TODO
Priority: P0
Milestone: CC-0800
Depends on:
- CC-0611
Goal:
Represent offline-capable routing signals for intent, repository, symbols, agent, latency, history, config, and policy.
Implementation:
- typed feature/explanation models with explicit missing values
Acceptance criteria:
- [ ] no external LLM is required
- [ ] feature extraction is deterministic and project-scoped
- [ ] missing historical data does not masquerade as zero-confidence evidence
Validation:
- unit tests: feature extraction
- integration tests: real project/query fixture
- security tests: untrusted agent metadata
- type checks: strict mypy
- benchmark/performance checks: feature extraction latency
Result: Pending.
Commit: Pending.

### CC-0820 — Implement explainable multi-adjustment route scoring
Status: TODO
Priority: P0
Milestone: CC-0800
Depends on:
- CC-0810
Goal:
Expose base, intent, repository, agent, feedback, latency, policy, and final scores with selection explanation.
Implementation:
- bounded normalized adjustment model layered over existing router
Acceptance criteria:
- [ ] every selected/non-selected capability has score breakdown/reason
- [ ] policy cannot be overridden by positive score adjustments
- [ ] fixed input produces deterministic route
Validation:
- unit tests: scoring/policy cases
- integration tests: router -> orchestrator selection
- security tests: forbidden capability cannot be score-selected
- type checks: strict mypy
- benchmark/performance checks: route latency
Result: Pending.
Commit: Pending.

### CC-0830 — Replace global feedback average with contextual bounded feedback
Status: TODO
Priority: P0
Milestone: CC-0800
Depends on:
- CC-0820
Goal:
Learn bounded adjustments by capability/request kind/project/agent type with minimum sample thresholds.
Implementation:
- versioned aggregate keys and capped adjustments
- minimum samples/decay or equivalent robust rule
Acceptance criteria:
- [ ] one project/agent cannot globally dominate all routing feedback
- [ ] sparse feedback has no unsafe large effect
- [ ] adjustments are explainable and bounded
Validation:
- unit tests: aggregation/threshold/bounds
- integration tests: feedback -> subsequent route
- security tests: project/workspace isolation
- type checks: strict mypy
- benchmark/performance checks: aggregation lookup bounded
Result: Pending.
Commit: Pending.

### CC-0840 — Add route simulation without engine execution
Status: TODO
Priority: P1
Milestone: CC-0800
Depends on:
- CC-0820
Goal:
Allow safe inspection of a proposed route without executing capability engines.
Implementation:
- simulation request/result contract and service/API exposure
Acceptance criteria:
- [ ] simulation performs no engine/tool mutation
- [ ] output matches real route-decision stage for same inputs
- [ ] policy denials remain enforced
Validation:
- unit tests: no execution spy
- integration tests: simulate vs real decision
- security tests: simulation cannot bypass hidden tool policy
- type checks: strict mypy
- benchmark/performance checks: route-only latency
Result: Pending.
Commit: Pending.

# EPIC CC-0900 — Agent Gateway

### CC-0910 — Implement persistent agent registry
Status: TODO
Priority: P0
Milestone: CC-0900
Depends on:
- CC-0614, CC-1100 auth primitives as available
Goal:
Track agent ID/type/display/version/project-workspace/connection/last-seen/capabilities/metadata.
Implementation:
- versioned local persistence and typed service/API models
- validate untrusted metadata and scope
Acceptance criteria:
- [ ] stable agent IDs and scoped registry CRUD/list
- [ ] sensitive prompt content is not required/stored by default
- [ ] connection metadata is bounded
Validation:
- unit tests: registry
- integration tests: connect/register/list
- security tests: cross-workspace agent access
- type checks: strict mypy
- benchmark/performance checks: indexed list/lookup
Result: Pending.
Commit: Pending.

### CC-0920 — Implement agent session telemetry
Status: TODO
Priority: P0
Milestone: CC-0900
Depends on:
- CC-0910, CC-0671
Goal:
Track session start/activity/tool calls/context tokens/tokens saved/latency/errors without storing sensitive complete prompts by default.
Implementation:
- bounded session/event persistence and redacted summaries
Acceptance criteria:
- [ ] session metrics are linked to agent/project/workspace
- [ ] retention is bounded/configurable
- [ ] credentials/prompts are not silently persisted
Validation:
- unit tests: session state
- integration tests: MCP session flow
- security tests: redaction/retention/isolation
- type checks: strict mypy
- benchmark/performance checks: event write overhead
Result: Pending.
Commit: Pending.

### CC-0930 — Build managed MCP status/policy API and page
Status: TODO
Priority: P1
Milestone: CC-0900
Depends on:
- CC-0920, CC-0543, CC-0642
Goal:
Show endpoint health, clients, tools, calls/minute, errors, latency, policies, and recent calls.
Implementation:
- reuse existing MCP server/telemetry/policy; no frontend configuration duplication
Acceptance criteria:
- [ ] page reflects real MCP state
- [ ] unauthorized tools/calls are not exposed across scopes
- [ ] recent calls are bounded/redacted
Validation:
- unit tests: aggregation
- integration tests: MCP -> telemetry -> API/UI
- security tests: policy/tool visibility
- type checks: both stacks
- benchmark/performance checks: bounded aggregation
Result: Pending.
Commit: Pending.

### CC-0940 — Reuse AgentConfigurator for connection workflows
Status: TODO
Priority: P1
Milestone: CC-0900
Depends on:
- CC-0910, CC-0642
Goal:
Expose supported Codex/Claude/OpenCode/compatible connection guidance/configuration from existing AgentConfigurator logic.
Implementation:
- service adapter around AgentConfigurator
- UI/API returns generated configuration data without duplicating rules
Acceptance criteria:
- [ ] connection workflow uses one source of truth
- [ ] existing CLI configurator behavior remains compatible
- [ ] secrets are shown/stored only according to credential contract
Validation:
- unit tests: adapter parity
- integration tests: configurator -> API
- security tests: secret redaction
- type checks: both stacks
- benchmark/performance checks: n/a
Result: Pending.
Commit: Pending.

# EPIC CC-1000 — PR Intelligence V2

### CC-1010 — Define evidence-backed PR comparison model
Status: TODO
Priority: P1
Milestone: CC-1000
Depends on:
- CC-0614
Goal:
Represent changed files/symbols/additions/deletions/impact/tests/owners/risk/architecture/memory/recommended context.
Implementation:
- typed comparison/evidence models; missing data optional
Acceptance criteria:
- [ ] every displayed fact has source/provenance where applicable
- [ ] no test command is synthesized without repository evidence
- [ ] Git ref/path inputs are validated
Validation:
- unit tests: model/mapping
- integration tests: local Git comparison
- security tests: malicious refs
- type checks: strict mypy
- benchmark/performance checks: bounded comparison size
Result: Pending.
Commit: Pending.

### CC-1020 — Implement explainable PR risk components
Status: TODO
Priority: P1
Milestone: CC-1000
Depends on:
- CC-1010, CC-0740
Goal:
Compute deterministic impact/breadth/churn/test/architecture/critical-path risk components and explanation.
Implementation:
- normalized evidence-based component model plus aggregate where justified
Acceptance criteria:
- [ ] component values/explanations are exposed
- [ ] missing evidence is not treated as factual zero without semantics
- [ ] output deterministic for fixed comparison state
Validation:
- unit tests: risk formulas
- integration tests: PR fixtures
- security tests: untrusted Git metadata
- type checks: strict mypy
- benchmark/performance checks: risk latency
Result: Pending.
Commit: Pending.

### CC-1030 — Generate deterministic discovered-test recommendations
Status: TODO
Priority: P1
Milestone: CC-1000
Depends on:
- CC-1010
Goal:
Recommend actual tests/commands derived from discovered test files, package metadata, CI config, graph impact, and project knowledge.
Implementation:
- evidence resolver; no free-form command hallucination
Acceptance criteria:
- [ ] every recommendation cites discovered evidence
- [ ] unsupported command remains absent rather than guessed
- [ ] changed/affected tests are ranked deterministically
Validation:
- unit tests: discovery/ranking
- integration tests: fixture package/CI
- security tests: command injection strings remain data, never executed
- type checks: strict mypy
- benchmark/performance checks: repository metadata cached/indexed
Result: Pending.
Commit: Pending.

### CC-1040 — Add hosted-Git provider boundary with GitHub adapter contract
Status: TODO
Priority: P1
Milestone: CC-1000
Depends on:
- CC-1010
Goal:
Separate provider-hosted PR metadata from local Git intelligence.
Implementation:
- provider protocol + GitHub adapter configuration; mocked tests without credentials
Acceptance criteria:
- [ ] core PR analysis works with local comparison independent of hosted provider
- [ ] GitHub adapter is optional and credentials are not base dependencies
- [ ] missing live credentials blocks only live verification
Validation:
- unit tests: mocked provider contract
- integration tests: adapter fixture
- security tests: credential redaction/least privilege
- type checks: strict mypy
- benchmark/performance checks: provider call counts bounded
Result: Pending.
Commit: Pending.

### CC-1050 — Build PR Intelligence API and page
Status: TODO
Priority: P1
Milestone: CC-1000
Depends on:
- CC-1020, CC-1030, CC-0642
Goal:
Inspect comparison evidence, impact graph, risk components, tests, architecture/memory, and recommended context.
Implementation:
- paginated/bounded service API and frontend views
Acceptance criteria:
- [ ] page displays components/evidence, not opaque score only
- [ ] context/test recommendations link to provenance
- [ ] large diffs/results are bounded
Validation:
- unit tests: UI/API mapping
- integration tests: comparison workflow
- security tests: source/diff escaping and project scope
- type checks: both stacks
- benchmark/performance checks: representative PR analysis latency
Result: Pending.
Commit: Pending.

# EPIC CC-1100 — Team / Organization

### CC-1110 — Version organization/workspace/member/credential persistence
Status: TODO
Priority: P0
Milestone: CC-1100
Depends on:
- CC-0531, CC-0541
Goal:
Provide coherent transactional local organization/workspace/member/role/credential state with migrations.
Implementation:
- SQLite local default; schema version/migrations; digest-only tokens
Acceptance criteria:
- [ ] migrations are transactional/recoverable
- [ ] plaintext credentials are not persisted
- [ ] duplicate organization/workspace creation is deterministic and safe
Validation:
- unit tests: migration/constraints
- integration tests: create/reopen/upgrade
- security tests: takeover/token storage
- type checks: strict mypy
- benchmark/performance checks: indexed membership/policy lookup
Result: Pending.
Commit: Pending.

### CC-1120 — Implement local/remote authentication primitives
Status: TODO
Priority: P0
Milestone: CC-1100
Depends on:
- CC-1110
Goal:
Support trusted-local loopback and authenticated remote access with separate principal credentials.
Implementation:
- cryptographically random tokens, digest verification, one-time plaintext return when generated
- explicit dangerous-dev bypass only
Acceptance criteria:
- [ ] non-loopback requires auth by default
- [ ] tokens are principal-specific/revocable
- [ ] auth failures are audited without secret leakage
Validation:
- unit tests: token lifecycle
- integration tests: HTTP + MCP auth
- security tests: token misuse/replay scope
- type checks: strict mypy
- benchmark/performance checks: auth verification latency
Result: Pending.
Commit: Pending.

### CC-1130 — Enforce RBAC and workspace isolation across services
Status: TODO
Priority: P0
Milestone: CC-1100
Depends on:
- CC-1120, CC-0541
Goal:
Apply owner/admin/member/viewer permissions consistently to Control Plane, MCP, memory, edits, workers, and policies.
Implementation:
- central authorization decision API used by all transports/services
Acceptance criteria:
- [ ] project/workspace A cannot read/mutate B without authority
- [ ] owner invariants from CC-0541 hold transactionally
- [ ] unauthorized tool is neither listed where inappropriate nor invoked
Validation:
- unit tests: role/capability matrix
- integration tests: service/API/MCP authorization
- security tests: escalation/cross-workspace suite
- type checks: strict mypy
- benchmark/performance checks: decision path bounded
Result: Pending.
Commit: Pending.

### CC-1140 — Implement workspace policies and context/tool/remote limits
Status: TODO
Priority: P0
Milestone: CC-1100
Depends on:
- CC-1130, CC-0514
Goal:
Configure allowed tools, context limits, remote access, and workspace policy through one policy source.
Implementation:
- unify OrganizationPolicyStore/RemoteAccessPolicy/service checks
Acceptance criteria:
- [ ] policy denial cannot be overridden by router/frontend
- [ ] context policy intersects safely with global hard limit
- [ ] policy mutations require correct role
Validation:
- unit tests: policy precedence/intersection
- integration tests: route/MCP/API enforcement
- security tests: confused-deputy/tool bypass
- type checks: strict mypy
- benchmark/performance checks: policy lookup cached safely
Result: Pending.
Commit: Pending.

### CC-1150 — Implement append-only bounded audit trail
Status: TODO
Priority: P0
Milestone: CC-1100
Depends on:
- CC-1130, CC-0544
Goal:
Audit auth, denied authz, role/workspace/policy changes, mutation tools, worker admin, memory mutation, and semantic edits.
Implementation:
- typed audit event model, retention/pagination, recursive redaction
Acceptance criteria:
- [ ] required security mutations/denials produce audit events
- [ ] audit data cannot expose credentials
- [ ] list retention is bounded and actor/scope/correlation ID preserved
Validation:
- unit tests: event generation/redaction
- integration tests: mutation -> audit API
- security tests: denied-authz logging without secret leak
- type checks: strict mypy
- benchmark/performance checks: append overhead
Result: Pending.
Commit: Pending.

### CC-1160 — Build organization/security/audit administration API and UI
Status: TODO
Priority: P1
Milestone: CC-1100
Depends on:
- CC-1140, CC-1150, CC-0642
Goal:
Manage organizations, workspaces, members, roles, credentials, policies, team memory administration, and audit without billing.
Implementation:
- authorized bounded endpoints and pages
Acceptance criteria:
- [ ] no billing/subscription functionality is added
- [ ] owner-critical operations require owner authority
- [ ] audit/security views are paginated/redacted
Validation:
- unit tests: forms/components/schemas
- integration tests: admin workflows
- security tests: UI/API escalation attempts
- type checks: both stacks
- benchmark/performance checks: bounded pages
Result: Pending.
Commit: Pending.

### CC-1170 — Add optional PostgreSQL readiness where materially useful
Status: TODO
Priority: P2
Milestone: CC-1100
Depends on:
- CC-1110
Goal:
Prepare persistence boundaries for optional PostgreSQL without replacing SQLite local default.
Implementation:
- storage protocol/SQL portability for selected multi-user stores; optional dependency/config
Acceptance criteria:
- [ ] SQLite remains default and fully supported
- [ ] no PostgreSQL dependency in base package
- [ ] contract tests run against available adapters; live DB may be externally blocked
Validation:
- unit tests: storage contract
- integration tests: SQLite; PostgreSQL when environment available
- security tests: DSN secret redaction
- type checks: strict mypy
- benchmark/performance checks: no unsupported scale claim
Result: Pending.
Commit: Pending.

# EPIC CC-1200 — Distributed Control

### CC-1210 — Bind worker registration/heartbeat to authenticated principal
Status: TODO
Priority: P0
Milestone: CC-1200
Depends on:
- CC-0542, CC-1120
Goal:
Make authenticated identity authoritative for remote workers instead of arbitrary `node_id`.
Implementation:
- principal-worker binding and capability validation
Acceptance criteria:
- [ ] spoofed/duplicate node ID cannot assume another worker identity
- [ ] heartbeats require current authorized principal
- [ ] stale worker status is deterministic
Validation:
- unit tests: binding
- integration tests: remote worker lifecycle
- security tests: spoof/token misuse
- type checks: strict mypy
- benchmark/performance checks: heartbeat path bounded
Result: Pending.
Commit: Pending.

### CC-1220 — Version typed jobs and enforce leases/fencing/retry recovery
Status: TODO
Priority: P0
Milestone: CC-1200
Depends on:
- CC-1210
Goal:
Support typed/versioned `repository.index`, `semantic.embed`, `benchmark.run`, `architecture.refresh` jobs with safe state transitions.
Implementation:
- job schema/version, queue claims, attempts, lease expiry, fencing, terminal state rules
Acceptance criteria:
- [ ] stale token cannot complete after reassignment
- [ ] competing claims yield one current lease
- [ ] retries/crash/restart preserve valid state and bounded attempts
Validation:
- unit tests: state machine/property tests
- integration tests: coordinator/worker restart
- security tests: old-token/stale-worker attacks
- type checks: strict mypy
- benchmark/performance checks: queue depth/claim latency metrics
Result: Pending.
Commit: Pending.

### CC-1230 — Build Workers/Jobs API and page
Status: TODO
Priority: P1
Milestone: CC-1200
Depends on:
- CC-1220, CC-0642
Goal:
Expose worker ID/principal/capabilities/heartbeat/activity/task/queue/attempt/failure/lease/latency safely.
Implementation:
- bounded WorkerService endpoints and UI
Acceptance criteria:
- [ ] current vs stale status is explicit
- [ ] administrative mutations are authorized/audited
- [ ] no worker credential secret is displayed
Validation:
- unit tests: mapping/components
- integration tests: worker lifecycle -> UI API
- security tests: unauthorized worker admin
- type checks: both stacks
- benchmark/performance checks: bounded polling/SSE path
Result: Pending.
Commit: Pending.

### CC-1240 — Expose vector provider health/index stats and scalable-provider boundary
Status: TODO
Priority: P1
Milestone: CC-1200
Depends on:
- CC-0720, CC-1230
Goal:
Expose actual vector provider state while retaining local default and optional scalable provider path.
Implementation:
- provider health/stat contracts; API/UI integration
Acceptance criteria:
- [ ] local exact scan limitations are documented honestly
- [ ] provider metrics are missing when unavailable, not invented
- [ ] external credentials are redacted
Validation:
- unit tests: provider stats
- integration tests: local provider
- security tests: config/secret handling
- type checks: both stacks
- benchmark/performance checks: actual provider measurements only
Result: Pending.
Commit: Pending.

# EPIC CC-1300 — Memory Control

### CC-1310 — Expose revisioned project/team memory service and API
Status: TODO
Priority: P1
Milestone: CC-1300
Depends on:
- CC-0532, CC-1130, CC-0622
Goal:
Search/add/edit/delete authorized memory with key/value/namespace/actor/revision/timestamp/history/provenance.
Implementation:
- MemoryService + typed paginated API over existing stores
Acceptance criteria:
- [ ] revision/history/provenance are preserved
- [ ] mutation authorization is enforced and audited
- [ ] deleted memory stops participating in retrieval
Validation:
- unit tests: service/version checks
- integration tests: API -> memory -> retrieval
- security tests: workspace isolation
- type checks: strict mypy
- benchmark/performance checks: bounded search/history
Result: Pending.
Commit: Pending.

### CC-1320 — Build Memory page
Status: TODO
Priority: P1
Milestone: CC-1300
Depends on:
- CC-1310, CC-0642
Goal:
Inspect and authorizedly manage project/team memory including revision history/provenance.
Implementation:
- search/list/detail/history/edit/delete UI
Acceptance criteria:
- [ ] project and team scopes are visually distinct
- [ ] revisions/actors/provenance are visible
- [ ] unauthorized controls/actions are rejected server-side
Validation:
- unit tests: components
- integration tests: memory workflow
- security tests: cross-workspace mutation
- type checks: frontend
- benchmark/performance checks: bounded list/history
Result: Pending.
Commit: Pending.

# EPIC CC-1400 — Architecture Control

### CC-1410 — Expose architecture inference/baseline/drift evidence service and API
Status: TODO
Priority: P1
Milestone: CC-1400
Depends on:
- CC-0614, CC-0622
Goal:
Expose inferred architecture, confidence, evidence, fingerprint, baseline, drift, and explanation with uncertainty preserved.
Implementation:
- ArchitectureService mapping + authorized baseline mutation
Acceptance criteria:
- [ ] inference is never presented as certainty
- [ ] evidence/confidence are preserved
- [ ] baseline updates are authorized/audited
Validation:
- unit tests: mapping/baseline
- integration tests: refresh -> baseline -> drift
- security tests: unauthorized baseline mutation
- type checks: strict mypy
- benchmark/performance checks: refresh latency recorded when run
Result: Pending.
Commit: Pending.

### CC-1420 — Build Architecture page
Status: TODO
Priority: P1
Milestone: CC-1400
Depends on:
- CC-1410, CC-0642
Goal:
Visualize inference evidence/confidence and baseline/drift without overstating certainty.
Implementation:
- summary/evidence/drift/baseline controls
Acceptance criteria:
- [ ] confidence/evidence and drift explanation are visible
- [ ] baseline mutation requires authorization
- [ ] unknown state is explicit
Validation:
- unit tests: components
- integration tests: API fixtures
- security tests: mutation auth
- type checks: frontend
- benchmark/performance checks: production build
Result: Pending.
Commit: Pending.

# EPIC CC-1500 — Benchmark & Quality Control

### CC-1510 — Version and persist benchmark/evaluation snapshots
Status: TODO
Priority: P1
Milestone: CC-1500
Depends on:
- CC-0780, CC-0614
Goal:
Persist commit/dataset/retrieval metrics/latency/context reduction/failure/skip/regression evidence with missing distinct from zero.
Implementation:
- snapshot/result schema and comparison service
Acceptance criteria:
- [ ] missing metric remains null/unavailable
- [ ] snapshots include commit/dataset/config identity
- [ ] failures/skips are recorded explicitly
Validation:
- unit tests: serialization/comparison
- integration tests: evaluation -> persisted snapshot
- security tests: path/output bounds
- type checks: strict mypy
- benchmark/performance checks: real evaluation artifacts
Result: Pending.
Commit: Pending.

### CC-1520 — Build Benchmarks page and regression comparison
Status: TODO
Priority: P1
Milestone: CC-1500
Depends on:
- CC-1510, CC-0642
Goal:
Inspect historical evidence and compare snapshots/regression gates.
Implementation:
- paginated history/detail/compare UI
Acceptance criteria:
- [ ] actual values and missing values are visually distinct
- [ ] failures/skips visible
- [ ] no fabricated scale/performance claim
Validation:
- unit tests: components
- integration tests: snapshot compare
- security tests: authorized benchmark run mutation if exposed
- type checks: frontend
- benchmark/performance checks: itself displays actual artifacts only
Result: Pending.
Commit: Pending.

# EPIC CC-1600 — Settings

### CC-1610 — Define validated settings service and actual precedence
Status: TODO
Priority: P1
Milestone: CC-1600
Depends on:
- CC-0514, CC-1130, CC-0611
Goal:
Safely expose context budget/hard limit/tokenizer/retrieval weights/embedding/cache/telemetry/trace retention/benchmark settings.
Implementation:
- typed settings schema with source/effective value and validation
- apply actual config precedence only
Acceptance criteria:
- [ ] unsafe/invalid values rejected
- [ ] workspace policy cannot be weakened by lower-authority setting
- [ ] public behavior changes are documented
Validation:
- unit tests: validation/precedence
- integration tests: setting -> effective runtime behavior
- security tests: policy override attempts/secret values
- type checks: strict mypy
- benchmark/performance checks: n/a
Result: Pending.
Commit: Pending.

### CC-1620 — Build Settings page
Status: TODO
Priority: P1
Milestone: CC-1600
Depends on:
- CC-1610, CC-0642
Goal:
Edit only safe validated settings and show effective values/sources.
Implementation:
- form controls from backend schema; no duplicated validation authority
Acceptance criteria:
- [ ] invalid changes show structured error
- [ ] secret fields are never echoed in plaintext
- [ ] effective/source values are visible where useful
Validation:
- unit tests: forms
- integration tests: save/reload/effective value
- security tests: secret handling/policy override
- type checks: frontend
- benchmark/performance checks: production build
Result: Pending.
Commit: Pending.

# EPIC CC-1700 — Live Events

### CC-1710 — Implement bounded SSE event stream
Status: TODO
Priority: P1
Milestone: CC-1700
Depends on:
- CC-0621, CC-0544
Goal:
Stream one-way observability events for index/engine/context/trace/agent/worker/task/PR lifecycle with bounded retention.
Implementation:
- typed versioned event envelope; SSE endpoint; bounded in-memory/persistent retention
- event kinds include `index.updated`, `engine.started`, `engine.finished`, `context.prepared`, `trace.created`, `agent.connected`, `agent.disconnected`, `worker.heartbeat`, `task.started`, `task.finished`, `pr.analysis.completed` as actually implemented
Acceptance criteria:
- [ ] event stream is authorized/project-workspace scoped
- [ ] retention and subscriber buffering are bounded
- [ ] credentials/source secrets are redacted
- [ ] disconnect/cancellation releases resources
Validation:
- unit tests: event buffer/envelope
- integration tests: operation -> SSE event
- security tests: cross-workspace event leakage/secret redaction
- type checks: strict mypy
- benchmark/performance checks: bounded subscriber/backpressure behavior
Result: Pending.
Commit: Pending.

### CC-1720 — Integrate live events into Control Plane views
Status: TODO
Priority: P1
Milestone: CC-1700
Depends on:
- CC-1710, CC-0642
Goal:
Use SSE to refresh observability views without aggressive polling or duplicating state.
Implementation:
- frontend event client/reconnect semantics and targeted cache invalidation
Acceptance criteria:
- [ ] disconnect/reconnect is handled safely
- [ ] events trigger bounded targeted refresh
- [ ] UI remains correct without SSE by manual/query refresh fallback
Validation:
- unit tests: event client
- integration tests: SSE fixture -> UI state
- security tests: event data escaping
- type checks: frontend
- benchmark/performance checks: no unbounded client event list
Result: Pending.
Commit: Pending.

# EPIC CC-1800 — 1.0 Validation & Release Readiness

### CC-1810 — Update evidence-oriented ROADMAP and production documentation
Status: TODO
Priority: P0
Milestone: CC-1800
Depends on:
- implemented milestones being documented
Goal:
Make README/ROADMAP/docs describe actual behavior and status, not planned or imaginary functionality.
Implementation:
- replace checkbox-only roadmap status with Implemented/Integrated/Tested/Hardened evidence
- maintain architecture/control-plane/context/retrieval/router/agent/security/distributed/deployment/API/migrations/testing/release docs as justified by implementation
Acceptance criteria:
- [ ] public docs match actual contracts/defaults
- [ ] migrations/upgrade path documented
- [ ] no unavailable feature is presented as complete
Validation:
- unit tests: docs checks where existing
- integration tests: command/examples smoke where practical
- security tests: no credentials in docs/fixtures
- type checks: n/a
- benchmark/performance checks: only actual benchmark results documented
Result: Pending.
Commit: Pending.

### CC-1820 — Production Docker Core/Full hardening
Status: TODO
Priority: P0
Milestone: CC-1800
Depends on:
- CC-0641, CC-1120
Goal:
Ship non-root practical Core and Full images with healthcheck, persistent data, safe network defaults, and no baked secrets.
Implementation:
- preserve/extend existing Docker strategy; include packaged frontend in Full where appropriate
Acceptance criteria:
- [ ] images build and smoke-test
- [ ] runtime user is non-root where practical
- [ ] persistent state volume documented
- [ ] remote auth/network defaults are safe
Validation:
- unit tests: n/a
- integration tests: Docker workflow/smoke
- security tests: image secret/non-root checks
- type checks: n/a
- benchmark/performance checks: image sizes/build evidence recorded
Result: Pending.
Commit: Pending.

### CC-1830 — Preserve and extend CLI entry points
Status: TODO
Priority: P0
Milestone: CC-1800
Depends on:
- CC-0612, CC-0621, CC-0631
Goal:
Preserve current CLI and add coherent `serve`/`ui`/project commands consistent with existing Typer structure, while retaining `cortex dashboard` compatibility.
Implementation:
- CLI delegates to services/control-plane assembly
- aliases/deprecation warnings for replaced public behavior
Acceptance criteria:
- [ ] existing documented CLI smoke tests remain green
- [ ] project add/list and Control Plane launch are usable without source edits
- [ ] compatibility changes are documented
Validation:
- unit tests: CLI runner
- integration tests: install wheel -> CLI workflow
- security tests: bind/auth defaults
- type checks: strict mypy
- benchmark/performance checks: n/a
Result: Pending.
Commit: Pending.

### CC-1840 — Repository-wide security and adversarial validation
Status: TODO
Priority: P0
Milestone: CC-1800
Depends on:
- all security-critical milestones
Goal:
Run and close practical adversarial gaps across path, Git, MCP, HTTP, org, worker, secret, state, and project boundaries.
Implementation:
- consolidate regression matrix for `../`, absolute/symlink escape, malicious refs, malformed/oversized requests, unauthorized mutation, escalation, token misuse, stale lease, nested secrets, corrupt state, cross-project access
Acceptance criteria:
- [ ] all required adversarial tests pass
- [ ] CodeQL/dependency/Bandit/security workflows remain enabled and green where runnable
- [ ] no high-severity known boundary defect remains untracked
Validation:
- unit tests: targeted
- integration tests: boundary workflows
- security tests: full adversarial suite
- type checks: strict mypy
- benchmark/performance checks: n/a
Result: Pending.
Commit: Pending.

### CC-1850 — Repository-wide performance evidence and regression review
Status: TODO
Priority: P0
Milestone: CC-1800
Depends on:
- indexing/retrieval/control-plane milestones
Goal:
Measure full/incremental indexing, semantic refresh, retrieval, context construction, graph neighborhood, and representative API latency without fabricated scale claims.
Implementation:
- reuse/extend benchmark/evaluation infrastructure; persist artifacts with commit/config/environment identity
Acceptance criteria:
- [ ] requested representative operations have actual measurements where environment supports them
- [ ] missing/external measurements are explicitly blocked/missing
- [ ] no hidden O(N^2), full-repository-per-query, unbounded event/list path remains known without task
Validation:
- unit tests: benchmark schema
- integration tests: benchmark runners
- security tests: benchmark paths/scopes safe
- type checks: strict mypy
- benchmark/performance checks: this task is the evidence run
Result: Pending.
Commit: Pending.

### CC-1860 — Final static/package/frontend/repository validation and completion report
Status: TODO
Priority: P0
Milestone: CC-1800
Depends on:
- CC-1810, CC-1820, CC-1830, CC-1840, CC-1850
Goal:
Re-audit the entire repository and prove the 1.0 quality bar before declaring readiness; do not publish a release.
Implementation:
- inspect duplicate/dead/stale Observatory paths, compatibility, metadata, migrations, Docker, docs, frontend packaging, workflows
- run exact applicable commands and record actual outputs
- produce final task/milestone counts and genuine blockers
Acceptance criteria:
- [ ] `ruff check .` passes
- [ ] `mypy src/codecortex` passes
- [ ] `pytest` and `pytest --cov` pass at required gate
- [ ] `python -m build` and package checks pass
- [ ] frontend lint/typecheck/tests/build pass
- [ ] required CI/security/Docker checks pass or genuine external blocker is recorded
- [ ] developer happy-path works without editing source/state manually
- [ ] no release/publication action is performed without owner authorization
Validation:
- unit tests: full suite
- integration tests: full/e2e suite
- security tests: CC-1840
- type checks: full strict mypy + frontend
- benchmark/performance checks: CC-1850 artifacts
Result: Pending.
Commit: Pending.

# Re-audit cadence

After each major epic, create task IDs for real findings in the owning epic and inspect:

- duplicate logic and stale compatibility paths
- dead code/TODO/FIXME
- unsafe defaults and secret leakage
- undocumented config or migration requirements
- unbounded queries/responses/event retention
- frontend/backend contract mismatch
- breaking CLI/MCP/API behavior
- state/version/migration gaps

# Commit discipline

Use small coherent commits mapped to task IDs. Commit messages should name the owning area, for example `test(indexing): complete graph equivalence invariants [CC-0512]`. Do not publish releases from this execution plan.
