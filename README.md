# CodeCortex 🧠

### The context intelligence layer for AI coding agents.

CodeCortex gives coding agents a unified view of repository architecture, symbols, dependencies, history, impact, memory, and compact task-specific context through one MCP surface.

**Map. Understand. Edit. Compress. Remember.**

> Alpha software. The architecture is usable today, but public performance claims are only published after reproducible benchmark runs.

## Why CodeCortex

Large codebases make agents spend too much context rediscovering structure, reading irrelevant files, and rebuilding knowledge between tasks. CodeCortex sits between the agent and the repository and routes each request to the right intelligence capability.

```text
Coding Agent
    │
    ▼
CodeCortex MCP / Gateway
    │
    ├── Adaptive Router
    ├── Repository Intelligence
    ├── Symbol Intelligence
    ├── Context Intelligence
    ├── Unified Memory
    ├── Git + PR Intelligence
    └── Validation + Tracing
```

The orchestration, routing, stable backend contracts, unified memory, multi-repository workspace, change intelligence, traces, evaluation, and product integration are CodeCortex-owned layers. Optional mature engines are revision-pinned, isolated from the Core dependency graph, and documented in `THIRD_PARTY_NOTICES.md`.

## Install

Python 3.11–3.13 is supported.

```bash
uv tool install git+https://github.com/BehnamJalaliCo/CodeCortex.git
```

Initialize the current repository:

```bash
cortex init .
```

For the complete intelligence stack and detected agent configuration:

```bash
cortex bootstrap
```

Or manage pieces explicitly:

```bash
cortex backend list
cortex backend install all
cortex backend doctor
cortex agents detect
cortex agents configure
```

Backend environments are isolated and pinned to exact revisions, so their dependency trees do not contaminate the CodeCortex Core environment.

## Agent integration

CodeCortex exposes a single MCP server:

```bash
cortex mcp --path /path/to/repository
```

`cortex agents configure` performs merge-safe project configuration for supported coding agents. Existing JSON/TOML settings are preserved; modified files receive backups, invalid configs are refused rather than overwritten, and an existing unmanaged Codex server entry is never silently replaced.

The agent sees CodeCortex tools such as repository mapping, symbol discovery, dependency analysis, semantic search, impact analysis, context construction, architecture inference, project/team memory, PR intelligence, trace summaries, validation, and runtime stats.

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

## Real repository benchmarks

The production benchmark uses immutable revisions of real repositories and compares five scenarios:

```text
vanilla
repository intelligence only
symbol intelligence only
vanilla + context optimization
full CodeCortex stack
```

Run it with:

```bash
python scripts/run_production_benchmark.py --provision
```

For a real coding agent with provider-reported usage and cost:

```bash
python scripts/run_agent_matrix.py --command "./my-instrumented-agent"
```

The benchmark never invents missing token, file-read, or cost values. Generated result artifacts are not treated as published evidence until they come from a reproducible run. See `benchmarks/production/README.md`.

## Docker

Core image:

```bash
docker build --target core -t codecortex:core .
```

Full backend image:

```bash
docker build --target full -t codecortex:full .
```

Dashboard:

```bash
docker compose up dashboard
```

## Reliability

CodeCortex uses three test rings:

- Core CI across supported Python versions.
- Adapter conformance against exact backend revisions.
- Scheduled upstream regression suites.

Release smoke tests run on Linux, macOS, and Windows. The repository also includes a scheduled dependency security audit and automated dependency update configuration.

## Development

```bash
git clone https://github.com/BehnamJalaliCo/CodeCortex.git
cd CodeCortex
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest -q
```

Run the deterministic demo:

```bash
python scripts/demo.py
```

## Project docs

- `docs/ARCHITECTURE.md` — core architecture.
- `docs/ADVANCED_INTELLIGENCE.md` — deeper intelligence layers.
- `docs/TESTING.md` — test rings and compatibility policy.
- `docs/RELEASE.md` — release process.
- `ROADMAP.md` — future work.
- `SECURITY.md` — security reporting.
- `THIRD_PARTY_NOTICES.md` — optional backend licensing and attribution.

## License

CodeCortex is licensed under Apache-2.0. Optional backend software remains under its respective upstream license; see `THIRD_PARTY_NOTICES.md`.
