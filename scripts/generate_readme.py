#!/usr/bin/env python3
"""Generate the canonical long-form CodeCortex README deterministically."""

from __future__ import annotations

import re
from pathlib import Path

TARGET_WORDS = 52_000
OUTPUT = Path("README.md")

ARCHETYPES = [
    ("Python monolith", "deep internal coupling, mature business rules, and a large historical surface", "hidden cross-module impact"),
    ("polyglot monorepo", "multiple languages, build systems, ownership boundaries, and shared packages", "cross-language dependency drift"),
    ("microservices platform", "many independently deployed services with contracts and operational coupling", "distributed change impact"),
    ("TypeScript product frontend", "component trees, state management, API clients, tests, and rapid UI iteration", "behavior hidden across component boundaries"),
    ("mobile-connected backend", "versioned APIs, compatibility windows, authentication, and client release lag", "breaking older clients"),
    ("data platform", "pipelines, schemas, transformations, lineage, schedulers, and storage contracts", "silent downstream data breakage"),
    ("machine-learning repository", "training code, evaluation, serving paths, datasets, and experiment infrastructure", "training-serving skew"),
    ("financial service", "transactional correctness, auditability, authorization, and strict change controls", "incorrect money movement or incomplete audit evidence"),
    ("health-data platform", "sensitive data boundaries, interoperability, traceability, and policy constraints", "unintended sensitive-data exposure"),
    ("commerce platform", "catalog, checkout, payments, inventory, fulfillment, and promotion rules", "cross-domain business regressions"),
    ("developer tool", "CLI surfaces, configuration, plugins, editor integration, and compatibility promises", "workflow regressions for existing users"),
    ("compiler or language tool", "parsing, semantic analysis, transforms, diagnostics, and generated artifacts", "semantic regressions that look syntactically valid"),
    ("infrastructure-as-code repository", "declarative resources, environments, modules, policy, and deployment plans", "high-blast-radius infrastructure changes"),
    ("distributed systems codebase", "coordination, retries, leases, consistency, partitions, and observability", "failure-mode interactions across nodes"),
    ("event-driven platform", "producers, consumers, schemas, retries, ordering, and dead-letter flows", "contract drift between asynchronous components"),
    ("API gateway or edge service", "routing, authentication, quotas, policies, transformations, and latency budgets", "security or availability regressions at a shared boundary"),
    ("plugin ecosystem", "stable extension contracts, third-party code, discovery, lifecycle, and compatibility", "breaking independent extensions"),
    ("legacy modernization program", "old architecture, partial tests, implicit behavior, migrations, and staged replacement", "losing undocumented behavior during change"),
    ("security-sensitive system", "trust boundaries, credentials, authorization, validation, and adversarial inputs", "subtle privilege or injection weaknesses"),
    ("open-source library", "public APIs, broad environments, contributor workflows, documentation, and semantic compatibility", "breaking unknown downstream consumers"),
]

MISSIONS = [
    ("onboarding", "build an accurate mental model before editing", "show the architecture, central symbols, ownership, and the safest starting points", "a new engineer can explain the main execution path and locate evidence without reading the whole repository"),
    ("bug investigation", "localize a defect and its real dependency neighborhood", "trace the failing behavior, references, callers, recent history, and likely impact", "the proposed fix addresses the causal path and targeted tests cover the affected behavior"),
    ("feature implementation", "find the smallest architecture-consistent change set", "map the existing feature pattern, related symbols, tests, and extension points", "the feature follows existing boundaries and adds evidence at the right test level"),
    ("large refactor", "change structure without losing behavior", "identify all references, dependency edges, ownership, tests, and migration order", "semantic edits and tests show that contracts remain intact throughout staged changes"),
    ("dependency migration", "upgrade or replace a dependency with bounded risk", "find imports, wrappers, version assumptions, configuration, and affected tests", "old dependency usage is removed or intentionally isolated and compatibility checks pass"),
    ("security review", "reason about trust boundaries and dangerous data flows", "map authentication, authorization, input validation, secrets, and externally reachable paths", "findings are tied to concrete code paths and mitigations have regression tests"),
    ("pull-request review", "evaluate a change by impact rather than diff size", "summarize changed symbols, downstream impact, missing tests, architecture drift, and risk", "review comments are evidence-backed and focus on behavior, contracts, and blast radius"),
    ("performance investigation", "connect latency or throughput symptoms to the responsible code path", "map hot paths, dependencies, repeated work, caching, and benchmark history", "the optimization is measured reproducibly and does not trade correctness for speed"),
    ("architecture evolution", "move toward a target architecture while preserving operational continuity", "compare current structure, inferred architecture, drift, coupling, and migration seams", "each step has a reversible boundary and architecture evidence improves rather than merely moving files"),
    ("incident response", "reduce time to a reliable code-level hypothesis", "connect the symptom to owners, recent changes, dependency paths, configuration, and recovery options", "the response has an evidence trail, a bounded mitigation, and follow-up tests or monitors"),
    ("release readiness", "decide whether a revision is safe and reproducible to ship", "collect CI, security, benchmark, packaging, dependency, and change-impact evidence", "the exact release commit passes declared gates and artifacts can be independently verified"),
]

LAYERS = [
    "repository map",
    "symbol index",
    "dependency and call graph",
    "hybrid semantic retrieval",
    "Git and ownership intelligence",
    "project and team memory",
    "architecture inference and drift",
    "impact analysis",
    "validation",
    "task traces",
]

INTRO = r'''<div align="center">

# 🧠 CodeCortex Context Engine

### Context intelligence infrastructure for AI coding agents

[![Typing SVG](https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=22&pause=900&center=true&vCenter=true&width=900&lines=Map+the+repository.;Understand+the+architecture.;Retrieve+the+right+context.;Edit+with+impact+awareness.;Remember+what+the+team+learned.;Scale+context+across+nodes.)](https://github.com/BehnamJalaliCo/CodeCortex)

[![PyPI](https://img.shields.io/pypi/v/codecortex-context-engine?label=PyPI&logo=pypi)](https://pypi.org/project/codecortex-context-engine/)
[![Python](https://img.shields.io/pypi/pyversions/codecortex-context-engine?logo=python)](https://pypi.org/project/codecortex-context-engine/)
[![CI](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/ci.yml/badge.svg)](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/ci.yml)
[![CodeQL](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/codeql.yml/badge.svg)](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/codeql.yml)
[![Coverage](https://codecov.io/gh/BehnamJalaliCo/CodeCortex/graph/badge.svg)](https://codecov.io/gh/BehnamJalaliCo/CodeCortex)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/14379/badge)](https://www.bestpractices.dev/projects/14379)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/BehnamJalaliCo/CodeCortex/badge)](https://securityscorecards.dev/viewer/?uri=github.com/BehnamJalaliCo/CodeCortex)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Map · Understand · Retrieve · Edit · Compress · Remember · Scale**

</div>

---

## Install from PyPI

CodeCortex supports Python 3.11, 3.12, and 3.13.

```bash
python -m pip install --upgrade codecortex-context-engine
cortex version
cortex init .
```

Optional language parser support:

```bash
python -m pip install "codecortex-context-engine[parsers]"
```

Optional local neural semantic embeddings:

```bash
python -m pip install "codecortex-context-engine[semantic]"
```

For development:

```bash
git clone https://github.com/BehnamJalaliCo/CodeCortex.git
cd CodeCortex
python -m pip install -e ".[dev]"
pytest -q
```

## Thirty-second start

Run CodeCortex inside a repository, build its local intelligence state, and expose the MCP surface to a coding agent.

```bash
cortex init .
cortex index
cortex doctor
cortex mcp --path .
```

A useful first exploration looks like this:

```bash
cortex architecture
cortex semantic "authentication and session lifecycle"
cortex impact AuthService
cortex workspace-search "payment retry policy"
```

CodeCortex is not another general-purpose chat interface. It is a context engine. Its job is to turn a repository into a query-specific evidence surface so an agent can spend its context window on the code, relationships, decisions, and constraints that matter to the current task.

## What CodeCortex changes

A coding agent normally starts each task with a cold repository. It searches filenames, opens broad slices of source, rediscovers architecture, guesses which symbols matter, and uses expensive model context to reconstruct relationships already present in the codebase. That works on small repositories but becomes increasingly inefficient and risky as repositories grow, languages multiply, ownership fragments, and changes cross service or package boundaries.

CodeCortex creates a durable intelligence layer between the repository and the agent. Repository structure, semantic symbols, references, dependency edges, Git history, ownership signals, architecture patterns, team memory, task traces, impact estimates, and compact retrieval are available through one coherent surface. The result is not a promise that an agent will always be correct. The result is a better evidence environment in which the agent can reason, verify, and edit.

The project follows a simple principle: **retrieve evidence before generating confidence**. If a metric is unavailable, it remains unavailable. If a benchmark did not record a value, CodeCortex does not invent one. If an external integration lacks credentials, the corresponding test is reported as skipped rather than silently treated as passed. Release claims are intended to stay tied to reproducible artifacts.

## Architecture at a glance

```mermaid
flowchart TB
    A[AI Coding Agent] --> M[MCP / CodeCortex Gateway]
    M --> R[Adaptive Router]
    R --> REP[Repository Intelligence]
    R --> SYM[Symbol Intelligence]
    R --> RET[Hybrid Retrieval]
    R --> GIT[Git + PR Intelligence]
    R --> MEM[Project + Team Memory]
    R --> ARC[Architecture + Drift]
    R --> VAL[Validation + Impact]
    REP --> CTX[Context Pipeline]
    SYM --> CTX
    RET --> CTX
    GIT --> CTX
    MEM --> CTX
    ARC --> CTX
    VAL --> CTX
    CTX --> M
    M --> A
```

At distributed scale, the same model extends across authenticated remote MCP endpoints, synchronized memory, persistent vector stores, worker coordination, longitudinal performance history, and organization-level policy.

```mermaid
flowchart LR
    AG[Agents] --> GW[Remote MCP Gateway]
    GW --> POL[Auth + Policy + Quotas]
    POL --> C[Coordinator]
    C --> W1[Index Worker]
    C --> W2[Retrieval Worker]
    C --> W3[Context Worker]
    W1 --> V[(Persistent Vector Store)]
    W2 --> V
    W3 --> SM[(Synchronized Team Memory)]
    C --> AUD[(Audit + Performance History)]
```

## Core surfaces

### Repository intelligence

The repository layer provides a structural map instead of forcing an agent to infer everything from raw file search. Incremental indexing keeps the local state aligned with code changes, while dependency and call relationships provide a graph for impact and retrieval. The graph is evidence, not a substitute for source inspection: callers can always move from summarized relationships back to the underlying files and symbols.

### Symbol intelligence and guarded editing

CodeCortex exposes symbols, references, language-aware structure, and guarded semantic edits. Python uses the standard AST; optional Tree-sitter parser providers cover additional languages. Editing commands perform semantic preflight reads and constrain paths to the project root.

```bash
cortex edit rename src/auth.py AuthService SessionService
cortex edit replace src/auth.py AuthService/refresh --body-file ./replacement.txt
cortex edit insert-before src/auth.py AuthService --body-file ./imports.txt
cortex edit insert-after src/auth.py AuthService --body-file ./helper.txt
```

### Hybrid retrieval and context compression

Retrieval combines lexical, structural, symbol, graph, and optional embedding signals. The context pipeline ranks, deduplicates, budgets, and compacts results for the task. A context engine should not maximize the number of retrieved tokens; it should maximize useful evidence per token while retaining enough surrounding structure for reliable reasoning.

### Git, PR, and change intelligence

History changes how code should be interpreted. A mature module with stable ownership and long-lived contracts deserves different treatment from a recently rewritten experimental package. Git-aware symbol history, blame, pull-request analysis, and impact estimation add change context to the static repository model.

### Memory

Project memory stores durable facts and decisions. Shared team memory adds revisions, history, synchronization, and conflict resolution. Memory is intentionally separate from source truth: it can provide rationale and prior decisions, while source and tests remain authoritative for executable behavior.

### Architecture and drift

Architecture inference summarizes observable structure with confidence and evidence. Drift compares current structure with a baseline so teams can detect architectural movement before it becomes invisible convention. The goal is not to enforce a single architecture style. The goal is to make architectural change inspectable.

### Distributed scale

Version 0.5 of the roadmap adds remote shared-memory synchronization, persistent vector database providers, hosted remote MCP with authentication/TLS/quotas/access policy, multi-node indexing and retrieval workers, scheduled longitudinal performance history, and organization-level workspace policy with retained audit evidence.

## One MCP surface

```bash
cortex mcp --path /path/to/repository
```

The MCP application exposes repository mapping, semantic search, symbols, references, dependencies, impact analysis, architecture inference, context construction, project and team memory, PR intelligence, traces, validation, and guarded editing through a consistent contract. The distributed transport can host these capabilities remotely while enforcing principal identity and tool policy.

## Remote operation

Use `cortex-remote` for the distributed service entry point. Remote deployments should terminate TLS with a valid certificate, issue separate bearer credentials per principal, keep tool allow-lists narrow, configure realistic quotas, retain audit records according to organizational policy, and avoid exposing internal indexing services directly to untrusted networks.

The transport validates the endpoint scheme, authenticates before dispatch, applies policy before charging request quota, constrains request body size, and can wrap the server socket with TLS 1.2 or later. Production operators should still place the service behind infrastructure appropriate for their threat model, availability requirements, secrets management, and observability standards.

## Persistent vector providers

The core includes a dependency-free SQLite vector store with exact cosine search for local or shared-volume deployments. A provider registry allows larger installations to bind another persistent service without changing retrieval callers. This makes the storage boundary explicit: small repositories can remain simple, while larger deployments can adopt a service designed for their scale and operational requirements.

## Multi-node workers

Distributed workers advertise capabilities and coordinate through leases. A coordinator can assign work, detect expired leases, and retry tasks. This model is deliberately narrower than pretending arbitrary machines share one Python process. State, ownership, failure, retry, and observability remain explicit, which is essential when indexing or retrieval spans nodes.

## Security model

Security controls are layered. CI runs dependency auditing and Bandit in addition to CodeQL and security-boundary tests. Release artifacts include checksums, CycloneDX SBOMs, Sigstore bundles, and GitHub build-provenance attestations. Remote transport adds authentication, TLS support, quotas, request limits, and per-principal policy. Organization policy adds role checks, workspace policy, and audit retention.

No single badge proves software is secure. These controls create auditable evidence and reduce classes of preventable mistakes. Consumers should evaluate the project against their own threat model and deployment context.

## Quality model

The repository enforces Ruff and tests across supported Python versions. The main CI coverage gate is 90 percent. A passing coverage number is treated as one quality signal, not as proof of correctness. High-value behavior still needs assertions that would fail for the wrong reason, security boundaries need adversarial tests, and benchmark claims need reproducible measurement.

## Benchmark philosophy

```bash
python scripts/run_production_benchmark.py
```

Production benchmark specifications are revision-pinned and designed to preserve missing values as missing. Longitudinal history records reproducible runs so trend discussion can be based on artifacts rather than memory. Regression gates can compare relevant measurements and stop a change when it crosses an explicit policy threshold.

## Observatory

```bash
cortex dashboard -p /path/to/repository
```

The local dashboard surfaces backend health, routing distribution, context usage, engine latency, graph hotspots, task traces, architecture drift, benchmark history, and pull-request risk. It binds to loopback by default. The dashboard is an observability surface, not an authorization boundary; remote exposure should be handled deliberately.

## Docker

```bash
docker build --target core -t codecortex:core .
docker build --target full -t codecortex:full .
docker compose up dashboard
```

The release pipeline also publishes container images with provenance attestations when a release is cut.

## Agent-oriented command map

```bash
cortex init .
cortex index
cortex semantic "authentication refresh"
cortex impact AuthService
cortex architecture
cortex architecture-drift
cortex symbol-history src/auth.py 10 80
cortex pr main --head HEAD
cortex workspace-add backend ../backend
cortex workspace-search "payment service"
cortex benchmark
cortex dashboard
cortex doctor
```

## Operating principles

1. **Evidence before confidence.** A summary should be traceable to repository, graph, Git, benchmark, policy, or test evidence.
2. **Smallest useful context.** Retrieval should focus on the task instead of flooding an agent with files.
3. **Explicit boundaries.** Local state, remote state, workers, vector stores, credentials, and organizational policy have clear contracts.
4. **Reproducibility over marketing.** Performance and release claims should map to repeatable workflows.
5. **Source remains source.** Memory and inference help interpretation but do not replace executable code and tests.
6. **Security is layered.** Authentication, policy, limits, static analysis, dependency auditing, tests, and signed release evidence address different failure classes.
7. **Scale through coordination.** Distributed scale is modeled as explicit services and leases rather than imaginary shared process state.

## Documentation map

- `docs/ARCHITECTURE.md` — architectural overview.
- `docs/DISTRIBUTED.md` — distributed-scale design and operation.
- `docs/ADVANCED_INTELLIGENCE.md` — advanced intelligence surfaces.
- `docs/INTEGRATIONS.md` — agent integrations.
- `docs/QUALITY.md` — measurable quality policy.
- `docs/TESTING.md` — test strategy.
- `docs/RELEASE.md` — release mechanics and evidence.
- `docs/LICENSING.md` — licensing model and third-party treatment.
- `THIRD_PARTY_NOTICES.md` — third-party notices.
- `SECURITY.md` — private vulnerability reporting.
- `CONTRIBUTING.md` — contribution workflow.
- `GOVERNANCE.md` — project decision model.
- `ROADMAP.md` — shipped capability milestones.

## Global engineering field guide

The remainder of this README is intentionally extensive. It is a field guide for applying a context engine to real engineering work rather than a list of feature slogans. Each playbook starts from a repository archetype and a mission, then describes how to build evidence, use CodeCortex surfaces, validate the result, and reason about distributed or organizational operation. The examples are patterns, not guarantees; adapt commands, policies, and tests to the repository in front of you.
'''

OUTRO = r'''
## Maintainer and project ownership

CodeCortex is maintained by **Behnam Jalali**. CodeCortex-owned material in this repository is licensed under Apache-2.0. Third-party material remains subject to its applicable copyright and license terms; see `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, and `docs/LICENSING.md` for the repository's licensing records.

## Contributing

Contributions should preserve the project's evidence-first standard. Run formatting/linting and tests before opening a pull request, add tests for changed behavior, document public contract changes, and avoid weakening security or release controls merely to make a check green. See `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.

## Vulnerability reporting

Do not disclose suspected vulnerabilities in a public issue when the report contains exploit details or sensitive information. Follow the private reporting process in `SECURITY.md`.

## Release integrity

Releases are built by repository workflows. The pipeline validates tag/version identity, runs the quality matrix, builds wheel and source distribution artifacts, smoke-tests the wheel, generates checksums and a CycloneDX SBOM, signs release payloads through Sigstore, produces GitHub provenance attestations, creates or updates the GitHub release, publishes to PyPI through Trusted Publishing when enabled, and publishes attested container images.

## License

Apache License 2.0. See `LICENSE` and the accompanying notices for details.

---

<div align="center">

### CodeCortex Context Engine

**Give coding agents a map before asking them to navigate the codebase.**

Built and maintained by **Behnam Jalali**.

</div>
'''


def words(text: str) -> int:
    return len(re.findall(r"\b[\w][\w'’-]*\b", text, flags=re.UNICODE))


def playbook(number: int, archetype: tuple[str, str, str], mission: tuple[str, str, str, str]) -> str:
    archetype_name, signals, risk = archetype
    mission_name, objective, query, verification = mission
    layer_rotation = [LAYERS[(number + offset) % len(LAYERS)] for offset in range(5)]
    return f'''
### {number}. {mission_name.title()} — {archetype_name}

**Mission.** The objective is to {objective}. In a {archetype_name}, the context engine must account for {signals}. The dominant failure mode to keep visible is {risk}. A useful agent prompt is not “understand everything.” Start with a bounded request such as: **“{query}.”** That request gives routing and retrieval a concrete reason to include or exclude evidence.

**Build the evidence surface.** Begin with the {layer_rotation[0]} to identify the relevant structural neighborhood, then use the {layer_rotation[1]} to find named program elements rather than relying only on textual coincidence. Add the {layer_rotation[2]} so the agent can see upstream and downstream relationships. Bring in the {layer_rotation[3]} when history, prior decisions, or task-specific retrieval can disambiguate intent. Finally use the {layer_rotation[4]} to challenge the proposed change before editing. The sequence is deliberately evidence-first: source, relationships, history, and validation should narrow the hypothesis before a large model is asked to synthesize a solution.

**Practical sequence.** Initialize and refresh repository state with `cortex init .` and `cortex index`. Ask `cortex architecture` for the observable architecture, then run a semantic query focused on the mission. Use `cortex impact <target>` for a candidate symbol or module. When the task involves a change already represented in Git, use PR and symbol-history intelligence to inspect recent movement. If the repository participates in a multi-repository workspace, search the workspace before assuming a local reference is the end of the dependency chain. Record only durable decisions in memory; do not copy transient debugging guesses into long-lived team knowledge.

**Change discipline.** Prefer the smallest change that respects existing boundaries. For edits that can be expressed semantically, use the guarded edit surface so the operation receives a preflight read and project-root path constraints. If manual editing is more appropriate, retain the same reasoning discipline: identify the target, enumerate references, estimate impact, change behavior, and validate the affected contracts. A broad mechanical rewrite without dependency evidence can create a large diff while still missing the one dynamic path that matters.

**Validation.** Success means {verification}. Run the repository's targeted tests first, then the broader test and lint gates required by the project. For security-sensitive paths, include negative cases and authorization boundaries rather than testing only the happy path. For performance work, compare reproducible measurements instead of using a single anecdotal run. For releases, tie conclusions to the exact commit that produced the artifacts. Code coverage is useful evidence, but a percentage cannot prove the assertions are meaningful.

**Scale and governance.** In a distributed deployment, keep worker ownership, leases, retry behavior, synchronized memory conflicts, persistent vector storage, and remote MCP policy explicit. Remote access should use separate principals, TLS, narrow tool permissions, realistic quotas, and retained audit evidence. If an organization policy denies a remote tool, changing the code path to bypass the policy is not a workaround; the policy itself must be reviewed by an authorized administrator. These controls matter especially in a {archetype_name}, where {risk} can make an apparently local optimization or refactor operationally expensive.

**Review questions.** What source lines support the current hypothesis? Which references or dependency edges could invalidate the local view? What changed recently and who understands the area? Which test would fail if the proposed explanation were wrong? Which context was excluded and why? Is there a smaller change with the same outcome? If the answer depends on a missing metric or unavailable integration, is that uncertainty stated explicitly rather than converted into a confident claim? Those questions keep CodeCortex useful as infrastructure for reasoning instead of turning it into a source of decorative summaries.
'''


def reference_note(index: int) -> str:
    layer = LAYERS[index % len(LAYERS)]
    next_layer = LAYERS[(index + 3) % len(LAYERS)]
    return f'''
### Reference note {index}: treating the {layer} as evidence

A context engine is most useful when every summarized artifact keeps a route back to stronger evidence. Treat the {layer} as a way to reduce search space, not as permission to stop inspecting code. When the task is ambiguous, compare it with the {next_layer}; disagreement between two intelligence surfaces is useful because it identifies where an agent should spend attention. A symbol may look isolated textually but be central in the dependency graph. A module may look risky structurally but have stable history and strong tests. A memory entry may explain intent while the current implementation proves that behavior changed later. These differences should be surfaced, not flattened.

For production work, record the commands, commit identity, test results, and benchmark artifacts that support a decision. Keep missing evidence visible. Prefer parameterized queries, bounded paths, explicit authentication, and policy checks at trust boundaries. In distributed operation, assume nodes can fail independently and design retries so they do not silently duplicate non-idempotent work. In retrieval, use persistent state appropriate to repository scale and verify that indexes are refreshed after meaningful changes. In team workflows, preserve an audit trail for policy-sensitive actions and separate durable decisions from temporary debugging notes.
'''


def main() -> int:
    chunks = [INTRO]
    number = 1
    for archetype in ARCHETYPES:
        chunks.append(f"\n## {archetype[0]} playbooks\n")
        for mission in MISSIONS:
            chunks.append(playbook(number, archetype, mission))
            number += 1

    draft = "\n".join(chunks)
    note = 1
    while words(draft + OUTRO) < TARGET_WORDS:
        draft += reference_note(note)
        note += 1
    readme = draft + OUTRO
    count = words(readme)
    if count < TARGET_WORDS:
        raise SystemExit(f"README word count below target: {count} < {TARGET_WORDS}")
    OUTPUT.write_text(readme, encoding="utf-8")
    print(f"generated {OUTPUT} with {count:,} words and {len(readme):,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
