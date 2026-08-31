# CodeCortex

**Context intelligence for AI coding agents.**

I built CodeCortex around a simple problem: coding agents become much less useful when a repository is large enough that they have to choose between reading too much code or missing the part that matters.

CodeCortex sits between an agent and the codebase. It maps the repository, finds symbols, routes each request to the right capability, keeps context inside a defined budget, remembers useful project decisions, and exposes the result through one stable gateway.

## What it does

- Maps repository structure and relevant paths
- Finds code at symbol level
- Routes requests based on intent
- Keeps context inside an explicit token budget
- Stores project-scoped memory locally
- Runs validation as part of change-oriented routes
- Exposes a stable tool bridge for coding-agent integrations
- Tracks routing and context activity locally
- Includes a lightweight local dashboard
- Includes a benchmark harness for reproducible measurements

## Quick start

```bash
git clone https://github.com/BehnamJalaliCo/CodeCortex.git
cd CodeCortex
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Initialize it inside a repository:

```bash
cortex init /path/to/project
cortex doctor -p /path/to/project
```

Ask CodeCortex how it would handle a task:

```bash
cortex route "Why does changing UserSession break checkout?" -p /path/to/project
```

Run the intelligence pipeline:

```bash
cortex run "Find the authentication refresh path" -p /path/to/project
```

Store a project decision:

```bash
cortex remember database "PostgreSQL is the primary database" -p /path/to/project
```

Open the local dashboard:

```bash
cortex dashboard -p /path/to/project
```

The dashboard is available at `http://127.0.0.1:7331` by default.

## Architecture

```text
Coding Agent / Tool Host
          |
          v
+-----------------------+
|   CodeCortex Gateway  |
+-----------+-----------+
            |
            v
+-----------------------+
|    Adaptive Router    |
+-----------+-----------+
            |
   +--------+---------+-----------+-----------+
   |                  |           |           |
   v                  v           v           v
Repository          Symbols     Memory     Validation
Intelligence      Intelligence   Engine      Engine
   |                  |           |           |
   +--------+---------+-----------+-----------+
            |
            v
+-----------------------+
|   Context Pipeline    |
| rank -> fit -> budget |
+-----------+-----------+
            |
            v
+-----------------------+
|     Orchestrator      |
+-----------+-----------+
            |
      +-----+-----+
      |           |
      v           v
  Telemetry   Tool Bridge
```

The core is intentionally small. Engines sit behind typed contracts, so a capability can be replaced without changing the router, gateway, or host integration.

More detail is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Commands

```text
cortex init
cortex doctor
cortex route
cortex run
cortex remember
cortex stats
cortex dashboard
cortex mcp-spec
```

## Project state

CodeCortex keeps local runtime data under:

```text
.codecortex/
├── config.json
├── memory/
└── runtime/
    └── events.jsonl
```

This directory is ignored by Git by default.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

CI runs the test suite on Python 3.11, 3.12, and 3.13.

## Status

CodeCortex is in active development. The current codebase is the architectural foundation for the first public release. The next work is focused on incremental indexing, multi-language symbol intelligence, dependency graphs, stronger context ranking, and a native transport layer.

See [`ROADMAP.md`](ROADMAP.md) for the current plan.

## License

License information will be added before the first public release.
