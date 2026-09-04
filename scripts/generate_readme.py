#!/usr/bin/env python3
"""Generate the canonical long-form CodeCortex README deterministically."""

from __future__ import annotations

import re
from pathlib import Path

TARGET_WORDS = 52_000
OUTPUT = Path("README.md")

ARCHETYPES = [
    (
        "Python monolith",
        "deep internal coupling, mature business rules, and a large historical surface",
        "hidden cross-module impact",
    ),
    (
        "polyglot monorepo",
        "multiple languages, build systems, ownership boundaries, and shared packages",
        "cross-language dependency drift",
    ),
    (
        "microservices platform",
        "many independently deployed services with contracts and operational coupling",
        "distributed change impact",
    ),
    (
        "TypeScript product frontend",
        "component trees, state management, API clients, tests, and rapid UI iteration",
        "behavior hidden across component boundaries",
    ),
    (
        "mobile-connected backend",
        "versioned APIs, compatibility windows, authentication, and client release lag",
        "breaking older clients",
    ),
    (
        "data platform",
        "pipelines, schemas, transformations, lineage, schedulers, and storage contracts",
        "silent downstream data breakage",
    ),
    (
        "machine-learning repository",
        "training code, evaluation, serving paths, datasets, and experiment infrastructure",
        "training-serving skew",
    ),
    (
        "financial service",
        "transactional correctness, auditability, authorization, and strict change controls",
        "incorrect money movement or incomplete audit evidence",
    ),
    (
        "health-data platform",
        "sensitive data boundaries, interoperability, traceability, and policy constraints",
        "unintended sensitive-data exposure",
    ),
    (
        "commerce platform",
        "catalog, checkout, payments, inventory, fulfillment, and promotion rules",
        "cross-domain business regressions",
    ),
    (
        "developer tool",
        "CLI surfaces, configuration, plugins, editor integration, and compatibility promises",
        "workflow regressions for existing users",
    ),
    (
        "compiler or language tool",
        "parsing, semantic analysis, transforms, diagnostics, and generated artifacts",
        "semantic regressions that look syntactically valid",
    ),
    (
        "infrastructure-as-code repository",
        "declarative resources, environments, modules, policy, and deployment plans",
        "high-blast-radius infrastructure changes",
    ),
    (
        "distributed systems codebase",
        "coordination, retries, leases, consistency, partitions, and observability",
        "failure-mode interactions across nodes",
    ),
    (
        "event-driven platform",
        "producers, consumers, schemas, retries, ordering, and dead-letter flows",
        "contract drift between asynchronous components",
    ),
    (
        "API gateway or edge service",
        "routing, authentication, quotas, policies, transformations, and latency budgets",
        "security or availability regressions at a shared boundary",
    ),
    (
        "plugin ecosystem",
        "stable extension contracts, third-party code, discovery, lifecycle, and compatibility",
        "breaking independent extensions",
    ),
    (
        "legacy modernization program",
        "old architecture, partial tests, implicit behavior, migrations, and staged replacement",
        "losing undocumented behavior during change",
    ),
    (
        "security-sensitive system",
        "trust boundaries, credentials, authorization, validation, and adversarial inputs",
        "subtle privilege or injection weaknesses",
    ),
    (
        "open-source library",
        "public APIs, broad environments, contributor workflows, documentation, and semantic compatibility",
        "breaking unknown downstream consumers",
    ),
]

MISSIONS = [
    (
        "onboarding",
        "build an accurate mental model before editing",
        "show the architecture, central symbols, ownership, and the safest starting points",
        "a new engineer can explain the main execution path and locate evidence without reading the whole repository",
    ),
    (
        "bug investigation",
        "localize a defect and its real dependency neighborhood",
        "trace the failing behavior, references, callers, recent history, and likely impact",
        "the proposed fix addresses the causal path and targeted tests cover the affected behavior",
    ),
    (
        "feature implementation",
        "find the smallest architecture-consistent change set",
        "map the existing feature pattern, related symbols, tests, and extension points",
        "the feature follows existing boundaries and adds evidence at the right test level",
    ),
    (
        "large refactor",
        "change structure without losing behavior",
        "identify all references, dependency edges, ownership, tests, and migration order",
        "semantic edits and tests show that contracts remain intact throughout staged changes",
    ),
    (
        "dependency migration",
        "upgrade or replace a dependency with bounded risk",
        "find imports, wrappers, version assumptions, configuration, and affected tests",
        "old dependency usage is removed or intentionally isolated and compatibility checks pass",
    ),
    (
        "security review",
        "reason about trust boundaries and dangerous data flows",
        "map authentication, authorization, input validation, secrets, and externally reachable paths",
        "findings are tied to concrete code paths and mitigations have regression tests",
    ),
    (
        "pull-request review",
        "evaluate a change by impact rather than diff size",
        "summarize changed symbols, downstream impact, missing tests, architecture drift, and risk",
        "review comments are evidence-backed and focus on behavior, contracts, and blast radius",
    ),
    (
        "performance investigation",
        "connect latency or throughput symptoms to the responsible code path",
        "map hot paths, dependencies, repeated work, caching, and benchmark history",
        "the optimization is measured reproducibly and does not trade correctness for speed",
    ),
    (
        "architecture evolution",
        "move toward a target architecture while preserving operational continuity",
        "compare current structure, inferred architecture, drift, coupling, and migration seams",
        "each step has a reversible boundary and architecture evidence improves rather than merely moving files",
    ),
    (
        "incident response",
        "reduce time to a reliable code-level hypothesis",
        "connect the symptom to owners, recent changes, dependency paths, configuration, and recovery options",
        "the response has an evidence trail, a bounded mitigation, and follow-up tests or monitors",
    ),
    (
        "release readiness",
        "decide whether a revision is safe and reproducible to ship",
        "collect CI, security, benchmark, packaging, dependency, and change-impact evidence",
        "the exact release commit passes declared gates and artifacts can be independently verified",
    ),
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

INTRO = r"""<div align="center">

# 🧠 CodeCortex Context Engine

### Open-source context intelligence infrastructure for AI coding agents

**Map the repository · resolve symbols · retrieve task-specific evidence · estimate impact · edit with guardrails**

[![PyPI](https://img.shields.io/pypi/v/codecortex-context-engine?label=PyPI&logo=pypi)](https://pypi.org/project/codecortex-context-engine/)
[![Python](https://img.shields.io/pypi/pyversions/codecortex-context-engine?logo=python)](https://pypi.org/project/codecortex-context-engine/)
[![CI](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/ci.yml/badge.svg)](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/ci.yml)
[![CodeQL](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/codeql.yml/badge.svg)](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/codeql.yml)
[![Coverage](https://codecov.io/gh/BehnamJalaliCo/CodeCortex/graph/badge.svg)](https://codecov.io/gh/BehnamJalaliCo/CodeCortex)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/14379/badge)](https://www.bestpractices.dev/projects/14379)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/BehnamJalaliCo/CodeCortex/badge)](https://securityscorecards.dev/viewer/?uri=github.com/BehnamJalaliCo/CodeCortex)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

[**Documentation**](https://behnamjalalico.github.io/CodeCortex/) · [**Latest Release**](https://github.com/BehnamJalaliCo/CodeCortex/releases/latest) · [**PyPI**](https://pypi.org/project/codecortex-context-engine/) · [**Report a Bug**](https://github.com/BehnamJalaliCo/CodeCortex/issues/new?template=bug.yml) · [**Contribute**](CONTRIBUTING.md)

[🇬🇧 English](#english) · [🇮🇷 فارسی](#فارسی)

</div>

---

## Why CodeCortex?

A coding agent can read code. The harder problem is deciding **what matters, what is connected, what can break, and how much context is actually worth sending to the model**.

CodeCortex turns a repository into a query-specific evidence system for coding agents:

- **Repository + symbol intelligence** — structure, definitions, references, dependencies, and call relationships.
- **Evidence-aware retrieval** — lexical, semantic, structural, graph, Git, architecture, and memory signals are ranked together.
- **Impact before edits** — reverse dependencies, affected tests, ownership, and change risk are inspectable before mutation.
- **Guarded changes** — semantic edits and structural rewrite previews keep source boundaries and review steps explicit.
- **Persistent project context** — architecture, history, project/team memory, traces, and multi-repo workspaces survive beyond one chat.

> **Core rule: retrieve evidence before generating confidence.**

## 60-second start

Requires Python 3.11–3.13.

```bash
python -m pip install --upgrade codecortex-context-engine
cortex init .
cortex index
cortex doctor
```

Then ask the repository useful questions:

```bash
cortex architecture
cortex semantic "authentication and session lifecycle"
cortex impact AuthService
```

Or expose the repository to an MCP-capable coding agent:

```bash
cortex mcp --path .
```

## Works with coding agents

CodeCortex includes merge-safe project configuration for **Claude Code, Codex, Cursor, Gemini CLI, and OpenCode**.

```bash
cortex agents detect
cortex agents configure --dry-run
# or configure every supported target explicitly:
cortex agents configure --all
```

The configurator only manages CodeCortex-owned MCP entries and keeps user-owned configuration intact.

## See it work locally

The repository ships a deterministic demo project and demo runner:

```bash
python scripts/demo.py
```

The demo indexes the fixture repository, analyzes the blast radius of `AuthService`, routes an evidence request, and reports measured context/trace data. It does not fabricate benchmark values.

## Reproducible evidence snapshot

These are committed hardening measurements, not generalized performance promises:

| Evidence | Recorded result |
|---|---:|
| Hardening test suite | **711 passed, 28 skipped, 0 failed** |
| Coverage in hardening report | **91.74%** |
| Warm exact definition lookup | **0.19–0.23 ms median** |
| Freshness scan across 600 documents | **4.25 ms median** |

See [HARDENING_REPORT.md](HARDENING_REPORT.md) and [benchmarks/](benchmarks/) for scope, methodology, limitations, and reproducibility notes.

"""

OUTRO = r"""
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
"""


def words(text: str) -> int:
    return len(re.findall(r"\b[\w][\w'’-]*\b", text, flags=re.UNICODE))


def playbook(
    number: int, archetype: tuple[str, str, str], mission: tuple[str, str, str, str]
) -> str:
    archetype_name, signals, risk = archetype
    mission_name, objective, query, verification = mission
    layer_rotation = [LAYERS[(number + offset) % len(LAYERS)] for offset in range(5)]
    return f"""
### {number}. {mission_name.title()} — {archetype_name}

**Mission.** The objective is to {objective}. In a {archetype_name}, the context engine must account for {signals}. The dominant failure mode to keep visible is {risk}. A useful agent prompt is not “understand everything.” Start with a bounded request such as: **“{query}.”** That request gives routing and retrieval a concrete reason to include or exclude evidence.

**Build the evidence surface.** Begin with the {layer_rotation[0]} to identify the relevant structural neighborhood, then use the {layer_rotation[1]} to find named program elements rather than relying only on textual coincidence. Add the {layer_rotation[2]} so the agent can see upstream and downstream relationships. Bring in the {layer_rotation[3]} when history, prior decisions, or task-specific retrieval can disambiguate intent. Finally use the {layer_rotation[4]} to challenge the proposed change before editing. The sequence is deliberately evidence-first: source, relationships, history, and validation should narrow the hypothesis before a large model is asked to synthesize a solution.

**Practical sequence.** Initialize and refresh repository state with `cortex init .` and `cortex index`. Ask `cortex architecture` for the observable architecture, then run a semantic query focused on the mission. Use `cortex impact <target>` for a candidate symbol or module. When the task involves a change already represented in Git, use PR and symbol-history intelligence to inspect recent movement. If the repository participates in a multi-repository workspace, search the workspace before assuming a local reference is the end of the dependency chain. Record only durable decisions in memory; do not copy transient debugging guesses into long-lived team knowledge.

**Change discipline.** Prefer the smallest change that respects existing boundaries. For edits that can be expressed semantically, use the guarded edit surface so the operation receives a preflight read and project-root path constraints. If manual editing is more appropriate, retain the same reasoning discipline: identify the target, enumerate references, estimate impact, change behavior, and validate the affected contracts. A broad mechanical rewrite without dependency evidence can create a large diff while still missing the one dynamic path that matters.

**Validation.** Success means {verification}. Run the repository's targeted tests first, then the broader test and lint gates required by the project. For security-sensitive paths, include negative cases and authorization boundaries rather than testing only the happy path. For performance work, compare reproducible measurements instead of using a single anecdotal run. For releases, tie conclusions to the exact commit that produced the artifacts. Code coverage is useful evidence, but a percentage cannot prove the assertions are meaningful.

**Scale and governance.** In a distributed deployment, keep worker ownership, leases, retry behavior, synchronized memory conflicts, persistent vector storage, and remote MCP policy explicit. Remote access should use separate principals, TLS, narrow tool permissions, realistic quotas, and retained audit evidence. If an organization policy denies a remote tool, changing the code path to bypass the policy is not a workaround; the policy itself must be reviewed by an authorized administrator. These controls matter especially in a {archetype_name}, where {risk} can make an apparently local optimization or refactor operationally expensive.

**Review questions.** What source lines support the current hypothesis? Which references or dependency edges could invalidate the local view? What changed recently and who understands the area? Which test would fail if the proposed explanation were wrong? Which context was excluded and why? Is there a smaller change with the same outcome? If the answer depends on a missing metric or unavailable integration, is that uncertainty stated explicitly rather than converted into a confident claim? Those questions keep CodeCortex useful as infrastructure for reasoning instead of turning it into a source of decorative summaries.
"""


def reference_note(index: int) -> str:
    layer = LAYERS[index % len(LAYERS)]
    next_layer = LAYERS[(index + 3) % len(LAYERS)]
    return f"""
### Reference note {index}: treating the {layer} as evidence

A context engine is most useful when every summarized artifact keeps a route back to stronger evidence. Treat the {layer} as a way to reduce search space, not as permission to stop inspecting code. When the task is ambiguous, compare it with the {next_layer}; disagreement between two intelligence surfaces is useful because it identifies where an agent should spend attention. A symbol may look isolated textually but be central in the dependency graph. A module may look risky structurally but have stable history and strong tests. A memory entry may explain intent while the current implementation proves that behavior changed later. These differences should be surfaced, not flattened.

For production work, record the commands, commit identity, test results, and benchmark artifacts that support a decision. Keep missing evidence visible. Prefer parameterized queries, bounded paths, explicit authentication, and policy checks at trust boundaries. In distributed operation, assume nodes can fail independently and design retries so they do not silently duplicate non-idempotent work. In retrieval, use persistent state appropriate to repository scale and verify that indexes are refreshed after meaningful changes. In team workflows, preserve an audit trail for policy-sensitive actions and separate durable decisions from temporary debugging notes.
"""


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
