# Getting Started

CodeCortex Context Engine is an open-source context intelligence layer for AI coding agents. It builds repository structure, symbol relationships, retrieval evidence, Git/PR context, impact signals, architecture information, and project memory, then exposes them through CLI, MCP, and platform surfaces.

## Requirements

- Python 3.11, 3.12, or 3.13
- A local Git repository or source tree

Core repository intelligence is local-first. Optional network-backed integrations remain explicit and credential-gated.

## Install

Linux, macOS, and Windows PowerShell can use the same PyPI-first path when
`python` resolves to Python 3.11 or newer:

```bash
python -m pip install --upgrade codecortex-context-engine
cortex version
```

On Windows systems where the Python launcher is available but `python` is not on
`PATH`, use:

```powershell
py -m pip install --upgrade codecortex-context-engine
cortex version
```

Optional language parser support:

```bash
python -m pip install "codecortex-context-engine[parsers]"
```

```powershell
py -m pip install "codecortex-context-engine[parsers]"
```

Optional local neural semantic embeddings:

```bash
python -m pip install "codecortex-context-engine[semantic]"
```

```powershell
py -m pip install "codecortex-context-engine[semantic]"
```

## First repository

Run these commands from the repository you want CodeCortex to understand:

```bash
cortex init .
cortex index
cortex doctor
```

Then inspect the repository with commands that are backed by the current codebase:

```bash
cortex architecture
cortex semantic "authentication and session lifecycle"
cortex impact AuthService
```

The exact symbol used in the `impact` example should be replaced with a symbol that exists in your repository.

## Connect a coding agent

Detect supported local coding-agent configurations:

```bash
cortex agents detect
```

Preview configuration changes without writing them:

```bash
cortex agents configure --dry-run
```

Configure detected agents:

```bash
cortex agents configure
```

Or configure every supported target explicitly:

```bash
cortex agents configure --all
```

Current configuration targets implemented by CodeCortex are:

- Claude Code
- Codex
- Cursor
- Gemini CLI
- OpenCode

The configurator writes only the CodeCortex-managed MCP entry and preserves user-owned configuration. Existing files are merged rather than blindly replaced.

## Run the MCP server directly

```bash
cortex mcp --path .
```

This exposes repository mapping, symbol/ref navigation, dependency and impact intelligence, context construction, architecture/drift, memory, validation, traces, and guarded editing through the MCP surface.

## See the deterministic demo

From a source checkout:

```bash
python -m pip install -e ".[dev]"
python scripts/demo.py
```

PowerShell equivalent when using the Windows Python launcher:

```powershell
py -m pip install -e ".[dev]"
py scripts/demo.py
```

The demo uses `examples/demo_project`, indexes it, analyzes `AuthService` impact, routes an evidence request, and prints measured context/trace output. It is designed to avoid fabricated performance claims.

## Next steps

- [Architecture](ARCHITECTURE.md)
- [Agent and ecosystem integrations](INTEGRATIONS.md)
- [Evidence Fusion](EVIDENCE_FUSION.md)
- [Distributed operation](DISTRIBUTED.md)
- [Platform and API](platform/README.md)
- [Quality and benchmarks](QUALITY.md)
- [Security policy](https://github.com/BehnamJalaliCo/CodeCortex/blob/main/SECURITY.md)
- [Licensing](LICENSING.md)
- [Release process](RELEASE.md)
