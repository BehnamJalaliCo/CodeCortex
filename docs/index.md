# CodeCortex Context Engine

**Context intelligence infrastructure for AI coding agents.**

CodeCortex builds task-specific codebase context from repository structure, semantic symbols, dependencies, Git history, impact analysis, memory, and context compression, then exposes that intelligence through one MCP surface.

## What it provides

- Repository and dependency intelligence
- Semantic symbol navigation and guarded refactoring
- Hybrid retrieval and context compression
- Project and team memory
- Git, PR, impact, and architecture intelligence
- MCP integration for coding agents
- Local observability, benchmarking, and security controls

## Start locally

```bash
git clone https://github.com/BehnamJalaliCo/CodeCortex.git
cd CodeCortex
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cortex init .
cortex doctor
```

Continue with the architecture, quality, testing, packaging, and release documentation from the navigation.
