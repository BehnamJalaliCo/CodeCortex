# Integrations

CodeCortex exposes one agent-facing MCP surface and includes merge-safe project configuration for supported coding agents.

## Supported coding-agent targets

The current implementation supports these project-local targets:

| Agent | CodeCortex-managed configuration |
|---|---|
| Claude Code | `.mcp.json` |
| Codex | `.codex/config.toml` |
| Cursor | `.cursor/mcp.json` |
| Gemini CLI | `.gemini/settings.json` |
| OpenCode | `opencode.json` |

These targets come directly from `codecortex.integrations.agents.AgentTarget`.

## Detect local agents

```bash
cortex agents detect
```

Detection checks supported executables and existing project-local configuration directories/files.

## Preview configuration

Before changing any project configuration:

```bash
cortex agents configure --dry-run
```

To preview all supported targets:

```bash
cortex agents configure --all --dry-run
```

## Configure detected agents

```bash
cortex agents configure
```

Or configure every supported target:

```bash
cortex agents configure --all
```

The configurator merges the CodeCortex MCP entry into existing JSON/TOML configuration instead of replacing the whole file. Existing files are backed up before a real modification where applicable.

## MCP command

All supported project-local integrations ultimately point to the same CodeCortex command:

```bash
cortex mcp --path /absolute/path/to/repository
```

The stdio MCP server exposes repository intelligence through a stable surface while internal engines remain behind the CodeCortex gateway.

## Why the integration boundary matters

A coding-agent host should not need to know how repository indexing, symbol resolution, retrieval, Git intelligence, memory, architecture inference, or impact analysis is implemented.

CodeCortex keeps that orchestration behind a single gateway so:

- the agent configuration stays small;
- evidence providers can evolve without rewriting host integrations;
- local-first behavior remains explicit;
- unavailable optional providers can degrade cleanly instead of pretending to succeed;
- guarded editing and validation remain inside the same trust boundary.

## Remote operation

For shared or hosted deployments, see [Distributed operation](DISTRIBUTED.md) and the [Platform overview](platform/README.md). Remote deployments should use the repository's authentication, TLS, policy, quota, and audit guidance instead of exposing internal worker services directly.
