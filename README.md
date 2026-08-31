# CodeCortex Context Engine 🧠

### Context intelligence infrastructure for AI coding agents.

CodeCortex builds a task-specific view of a codebase from repository structure, semantic symbols, dependencies, Git history, impact, memory, and compressed context — then exposes it through one MCP surface.

**Map. Understand. Edit. Compress. Remember.**

> **Alpha.** The architecture and local workflows are usable today. Performance claims are published only from reproducible benchmark artifacts produced by the repository workflows.

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

The orchestration, routing, stable backend contracts, memory, multi-repository workspace, change intelligence, observability, evaluation, and product integration are CodeCortex-owned layers. Mature engine sources are pinned to exact revisions and carried under `vendor/`; licensing details live in `THIRD_PARTY_NOTICES.md`.

## Install

Python 3.11–3.13 is supported.

### From source today

```bash
git clone --recurse-submodules https://github.com/BehnamJalaliCo/CodeCortex.git
cd CodeCortex
pip install -e ".[dev]"
```

If the repository was cloned without recursive source checkout:

```bash
git submodule update --init --recursive
```

The release pipeline publishes the Python distribution as `codecortex-context-engine`. After the first successful public package release:

```bash
uv tool install codecortex-context-engine
```

Initialize a repository:

```bash
cortex init .
```

Install the complete intelligence stack and configure detected agents:

```bash
cortex bootstrap
```

Or manage components explicitly:

```bash
cortex backend list
cortex backend install all
cortex backend doctor
cortex agents detect
cortex agents configure
```

Backend environments are isolated. A source checkout installs its pinned local engine sources first; packaged installs retain a revision-pinned remote fallback.

## One MCP surface

```bash
cortex mcp --path /path/to/repository
```

Agent configuration is merge-safe: existing JSON/TOML settings are preserved, modified files receive backups, malformed configs are refused rather than overwritten, and unmanaged server entries are not silently replaced.

The MCP surface includes repository mapping, semantic search, symbols, references, dependency analysis, impact analysis, architecture inference, context construction, project/team memory, PR intelligence, traces, validation, and guarded semantic editing.

### Semantic edits

With the semantic backend installed, CodeCortex exposes language-server-backed refactors:

```bash
cortex edit rename src/auth.py AuthService SessionService
cortex edit replace src/auth.py AuthService/refresh --body-file ./replacement.txt
cortex edit insert-before src/auth.py AuthService --body-file ./imports.txt
cortex edit insert-after src/auth.py AuthService --body-file ./helper.txt
```

Equivalent guarded edit operations are available through MCP. Paths are resolved inside the project root and every symbol-body mutation performs a semantic preflight read.

## Native language intelligence

Python uses the standard AST. Install the native parser extra for Tree-sitter grammars across TypeScript, JavaScript, Go, Rust, Java, C, C++, C#, PHP, and Ruby:

```bash
pip install "codecortex-context-engine[parsers]"
```

When native grammars are unavailable, CodeCortex falls back to conservative structural parsing instead of pretending the deeper parser ran.

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

## Reproducible performance evidence

The production benchmark checks immutable revisions of real repositories under five scenarios:

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

For an instrumented coding agent with provider-reported usage and cost:

```bash
python scripts/run_agent_matrix.py --command "./my-instrumented-agent"
```

Missing token, file-read, or cost metrics remain `null`; CodeCortex does not fabricate them. CI stores raw benchmark artifacts and publishes a run summary. A public performance number belongs in this README only after a reproducible run has produced the evidence.

## Observatory

```bash
cortex dashboard -p /path/to/repository
```

The local read-only dashboard shows backend health, routing distribution, context tokens saved, engine latency, graph hotspots, recent task traces, architecture drift, benchmark history, and a PR-risk API. It binds to `127.0.0.1` by default and sends defensive browser security headers.

## Docker

```bash
docker build --target core -t codecortex:core .
docker build --target full -t codecortex:full .
docker compose up dashboard
```

Docker CI smoke-tests Core and Full images, including MCP discovery. Tagged releases publish attested images to GHCR.

## Reliability and supply chain

CodeCortex uses layered validation:

- Core CI across Python 3.11, 3.12, and 3.13.
- Live adapter conformance against exact pinned source revisions.
- Scheduled source regression suites.
- Native-parser provider tests.
- Docker Core/Full integration tests.
- Dependency audit, Bandit, CodeQL, dependency review, and security-boundary tests.
- CycloneDX SBOM generation.
- Tagged release checksums, Sigstore bundles, and GitHub build-provenance attestations.

Live model-backed agent E2E workflows are credential-gated and verify actual MCP tool use through CodeCortex telemetry rather than assuming configuration means success.

## Development

```bash
git clone --recurse-submodules https://github.com/BehnamJalaliCo/CodeCortex.git
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

## Documentation

- `docs/ARCHITECTURE.md` — system architecture.
- `docs/ADVANCED_INTELLIGENCE.md` — deeper intelligence layers.
- `docs/TESTING.md` — test rings and compatibility policy.
- `docs/RELEASE.md` — release process.
- `docs/PACKAGING.md` — distribution identity.
- `docs/BRAND.md` — canonical project identity and naming policy.
- `ROADMAP.md` — shipped and future work.
- `SECURITY.md` — private vulnerability reporting and security defaults.
- `THIRD_PARTY_NOTICES.md` — required third-party licensing and attribution.

## License

CodeCortex-owned code is licensed under Apache-2.0. Vendored engine software remains under its applicable license; see `THIRD_PARTY_NOTICES.md`.
