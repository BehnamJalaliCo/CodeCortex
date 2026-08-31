# CodeCortex Context Engine 🧠

[![CI](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/ci.yml/badge.svg)](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/ci.yml)
[![CodeQL](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/codeql.yml/badge.svg)](https://github.com/BehnamJalaliCo/CodeCortex/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/BehnamJalaliCo/CodeCortex/badge)](https://securityscorecards.dev/viewer/?uri=github.com/BehnamJalaliCo/CodeCortex)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)

### Context intelligence infrastructure for AI coding agents.

CodeCortex builds a task-specific view of a codebase from repository structure, semantic symbols, dependencies, Git history, impact, memory, and compressed context — then exposes it through one MCP surface.

**Map. Understand. Edit. Compress. Remember.**

> **Alpha.** The architecture and local workflows are usable today. Performance claims are published only from reproducible benchmark artifacts produced by repository workflows.

## Why CodeCortex

Large repositories force coding agents to repeatedly rediscover architecture, read irrelevant files, and spend context on information that should already be structured. CodeCortex sits between an agent and its codebase and routes each request to the smallest useful intelligence surface.

```text
Coding Agent
    │
    ▼
CodeCortex MCP / Gateway
    │
    ├── Adaptive Router
    ├── Repository + Dependency Intelligence
    ├── Semantic Symbol + Refactor Intelligence
    ├── Hybrid Retrieval + Context Compression
    ├── Project + Team Memory
    ├── Git + PR + Impact Intelligence
    ├── Architecture Drift
    └── Validation + Task Tracing
```

The orchestration, routing, repository intelligence, symbol intelligence, context processing, memory, multi-repository workspace, change intelligence, observability, evaluation, and product integration layers live in this repository. Optional external adapters are configuration-driven and disabled by default.

## Install

Python 3.11–3.13 is supported.

```bash
git clone https://github.com/BehnamJalaliCo/CodeCortex.git
cd CodeCortex
pip install -e ".[dev]"
cortex init .
```

The release pipeline is prepared to publish the Python distribution as `codecortex-context-engine`.

## One MCP surface

```bash
cortex mcp --path /path/to/repository
```

The MCP surface includes repository mapping, semantic search, symbols, references, dependency analysis, impact analysis, architecture inference, context construction, project/team memory, PR intelligence, traces, validation, and guarded semantic editing.

### Semantic edits

```bash
cortex edit rename src/auth.py AuthService SessionService
cortex edit replace src/auth.py AuthService/refresh --body-file ./replacement.txt
cortex edit insert-before src/auth.py AuthService --body-file ./imports.txt
cortex edit insert-after src/auth.py AuthService --body-file ./helper.txt
```

Paths are constrained to the project root and symbol-body mutations perform a semantic preflight read.

## Native language intelligence

Python uses the standard AST. The optional native parser extra provides Tree-sitter grammars across TypeScript, JavaScript, Go, Rust, Java, C, C++, C#, PHP, and Ruby.

```bash
pip install "codecortex-context-engine[parsers]"
```

## Core commands

```bash
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

## Quality and security

CodeCortex uses layered validation: CI across Python 3.11–3.13, CodeQL, dependency auditing, Bandit, security-boundary tests, OpenSSF Scorecard, CycloneDX SBOMs, checksums, Sigstore signing, and GitHub build-provenance attestations.

Repository-wide branch coverage has a measured baseline and a 90% long-term target. See `docs/QUALITY.md` for the current evidence and policy.

## Reproducible performance evidence

```bash
python scripts/run_production_benchmark.py
```

Missing token, file-read, or cost metrics remain `null`; CodeCortex does not fabricate them. Public performance claims should be backed by reproducible benchmark artifacts.

## Observatory

```bash
cortex dashboard -p /path/to/repository
```

The local read-only dashboard shows backend health, routing distribution, context tokens saved, engine latency, graph hotspots, recent task traces, architecture drift, benchmark history, and a PR-risk API. It binds to `127.0.0.1` by default.

## Docker

```bash
docker build --target core -t codecortex:core .
docker build --target full -t codecortex:full .
docker compose up dashboard
```

## Project standards

- `CONTRIBUTING.md` — contribution workflow.
- `CODE_OF_CONDUCT.md` — community expectations.
- `GOVERNANCE.md` — decision-making and maintainership.
- `SUPPORT.md` — support channels.
- `SECURITY.md` — private vulnerability reporting and security defaults.
- `CITATION.cff` — citation metadata.
- `COMMERCIAL.md` — commercial support and licensing model.
- `docs/QUALITY.md` — measurable quality targets.
- `docs/OPENSSF.md` — OpenSSF badge readiness and external enrollment.
- `ROADMAP.md` — shipped and future work.

## Licensing

CodeCortex is licensed under **Apache-2.0**. Separate paid support, managed offerings, enterprise terms, and commercial agreements for material the licensor has the right to license may be offered independently; see `COMMERCIAL.md`.
