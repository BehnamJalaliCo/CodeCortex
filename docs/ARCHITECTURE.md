# Architecture

CodeCortex is organized as a small core with replaceable engines around it. The core owns routing, orchestration, context limits, project memory, validation, and observability. Engines implement capabilities and can evolve without changing the agent-facing interface.

## Layers

1. **Gateway** — receives requests from CLI, MCP, or future integrations.
2. **Router** — classifies intent and chooses capabilities.
3. **Orchestrator** — executes the route plan and combines results.
4. **Engines** — repository, symbol, context, memory, and validation capabilities.
5. **Context Pipeline** — ranks and fits context into a defined budget.
6. **Memory** — stores project-scoped knowledge and reusable decisions.
7. **Telemetry** — records routing, token use, timing, and engine health.
8. **Interfaces** — CLI, MCP, and future service APIs.

## Design rules

- The core does not depend on a specific external engine.
- Every engine is accessed through a typed contract.
- Routing decisions are observable and testable.
- Context has an explicit budget.
- Memory is project scoped by default.
- Local operation is the default path.
- Integrations are adapters, not core dependencies.
