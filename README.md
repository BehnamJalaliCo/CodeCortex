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

The orchestration, routing, repository intelligence, symbol intelligence, context processing, memory, multi-repository workspace, change intelligence, observability, evaluation, and product integration layers live in this repository. Optional external adapters are configuration-driven and disabled by default; CodeCortex ships without embedded upstream source identities or source URLs.

## Install

Python 3.11–3.13 is supported.

### From source today

```bash
git clone https://github.com/BehnamJalaliCo/CodeCortex.git
cd CodeCortex
pip install -e ".[dev]"
```

The release pipeline publishes the Python distribution as `codecortex-context-engine`. After the first successful public package release:

```bash
uv tool install codecortex-context-engine
```

Initialize a repository:

```bash
cortex init .
```

Configure detected agents:

```bash
cortex agents detect
cortex agents configure
```

Optional external adapters can be supplied explicitly through environment configuration. Built-in intelligence remains the default runtime.

## One MCP surface

```bash
cortex mcp --path /path/to/repository
```

Agent configuration is merge-safe: existing JSON/TOML settings are preserved, modified files receive backups, malformed configs are refused rather than overwritten, and unmanaged server entries are not silently replaced.

The MCP surface includes repository mapping, semantic search, symbols, references, dependency analysis, impact analysis, architecture inference, context construction, project/team memory, PR intelligence, traces, validation, and guarded semantic editing.

### Semantic edits

CodeCortex exposes guarded semantic edit operations when the configured symbol intelligence surface supports them:

```bash
cortex edit rename src/auth.py AuthService SessionService
cortex edit replace src/auth.py AuthService/refresh --body-file ./replacement.txt
cortex edit insert-before src/auth.py AuthService --body-file ./imports.txt
cortex edit insert-after src/auth.py AuthService --body-file ./helper.txt
```

Paths are resolved inside the project root and symbol-body mutations perform a semantic preflight read.

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

The production benchmark measures CodeCortex scenarios without inventing unavailable metrics. Run it with:

```bash
python scripts/run_production_benchmark.py
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
- Backend boundary and integration tests.
- Native-parser provider tests.
- Docker Core/Full integration tests.
- Dependency audit, Bandit, CodeQL, dependency review, and security-boundary tests.
- CycloneDX SBOM generation.
- Tagged release checksums, Sigstore bundles, and GitHub build-provenance attestations.

Live model-backed agent E2E workflows are credential-gated and verify actual MCP tool use through CodeCortex telemetry rather than assuming configuration means success.

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

## Documentation

- `docs/ARCHITECTURE.md` — system architecture.
- `docs/ADVANCED_INTELLIGENCE.md` — deeper intelligence layers.
- `docs/TESTING.md` — test rings and compatibility policy.
- `docs/RELEASE.md` — release process.
- `docs/PACKAGING.md` — distribution identity.
- `docs/BRAND.md` — canonical project identity and naming policy.
- `ROADMAP.md` — shipped and future work.
- `SECURITY.md` — private vulnerability reporting and security defaults.

## License

CodeCortex is licensed under Apache-2.0.
