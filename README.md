# CodeCortex

**The context intelligence layer for AI coding agents.**

CodeCortex gives coding agents a persistent, queryable model of a software project: symbols, dependency relationships, architecture, history, project memory, change impact and compact task-specific context.

Instead of repeatedly reading large parts of a repository, an agent can ask CodeCortex for the smallest useful slice of project intelligence and keep the result inside a controlled context budget.

## Highlights

- Incremental repository and knowledge-graph indexing
- Multi-language symbol and type intelligence
- Confidence-scored cross-file call and dependency resolution
- Hybrid semantic, lexical and structural retrieval
- Change-impact analysis and affected-test discovery
- Git history, symbol blame and ownership intelligence
- Architecture inference and architecture-drift detection
- Pull-request risk intelligence
- Local project memory and revisioned shared team memory
- Federated multi-repository workspaces
- Query-aware context ranking, deduplication and token budgeting
- Agent task traces with local observability and sensitive-field redaction
- Native MCP stdio server with structured tools
- Reproducible benchmarks, benchmark history and regression gates
- Agent-neutral external evaluation suites

## Quick start

```bash
git clone https://github.com/BehnamJalaliCo/CodeCortex.git
cd CodeCortex
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Initialize any project:

```bash
cortex init /path/to/project
cortex doctor -p /path/to/project
```

Ask for project intelligence:

```bash
cortex run "Find the authentication refresh path" -p /path/to/project
cortex impact AuthService -p /path/to/project
cortex semantic "where is session rotation handled?" -p /path/to/project
```

Run the MCP server:

```bash
cortex mcp -p /path/to/project
```

## Architecture

```text
Coding Agent / MCP Host / CLI
             |
             v
+---------------------------+
|     CodeCortex Gateway    |
+-------------+-------------+
              |
              v
+---------------------------+
|      Adaptive Router      |
+-------------+-------------+
              |
      +-------+--------+------------------+
      |                |                  |
      v                v                  v
 Repository         Symbols          Project Memory
 Intelligence     & Types           & Team Memory
      |                |                  |
      +-------+--------+------------------+
              |
              v
+---------------------------+
|  Knowledge + Change Graph |
| calls / imports / impact  |
+-------------+-------------+
              |
      +-------+---------+----------------+
      |                 |                |
      v                 v                v
 Semantic          Architecture      Git / PR
 Retrieval         Intelligence      Intelligence
      |                 |                |
      +-------+---------+----------------+
              |
              v
+---------------------------+
|      Context Pipeline     |
| rank -> dedup -> fit      |
+-------------+-------------+
              |
              v
+---------------------------+
| Orchestrator + Task Trace |
+---------------------------+
```

More detail is available in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/ADVANCED_INTELLIGENCE.md`](docs/ADVANCED_INTELLIGENCE.md).

## CLI

```text
cortex init
cortex index
cortex doctor
cortex route
cortex run
cortex semantic
cortex impact
cortex history
cortex symbol-history
cortex architecture
cortex architecture-baseline
cortex architecture-drift
cortex pr
cortex remember
cortex team-remember
cortex team-search
cortex workspace-add
cortex workspace-search
cortex trace-summary
cortex stats
cortex dashboard
cortex benchmark
cortex benchmark-gate
cortex evaluate
cortex mcp
```

## Semantic retrieval

The default semantic provider is local and deterministic. No external service is required. For the optional neural provider:

```bash
pip install -e ".[semantic]"
```

## Project state

Runtime state is project-local:

```text
.codecortex/
├── index/
│   ├── manifest.json
│   ├── graph.json
│   └── semantic.json
├── architecture/
│   └── baseline.json
├── memory/
│   └── team.sqlite3
├── benchmarks/
│   └── history.json
├── runtime/
│   ├── events.jsonl
│   └── traces.jsonl
└── workspace.json
```

The `.codecortex/` directory is ignored by Git by default.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

CI runs against Python 3.11, 3.12 and 3.13.

## Benchmarks

CodeCortex does not hard-code performance claims. Benchmark and evaluation results are generated from actual runs and can be persisted locally. Regression gates can fail when success/recall degrade or resource use exceeds configured thresholds.

## Status

The core intelligence and agent-workflow layers are implemented. Current work is focused on production hardening, scale, additional provider integrations and release quality.

See [`ROADMAP.md`](ROADMAP.md) for the current plan.
