# CodeCortex

CodeCortex is an open-source context intelligence layer for AI coding agents. It gives agents a structured view of a codebase, routes each request to the right internal capability, keeps context focused, tracks project knowledge, and provides a clean control layer for analysis and code changes.

The goal is simple: help coding agents understand large repositories with less noise and make safer, more precise changes.

## What CodeCortex provides

- Repository intelligence and relationship mapping
- Symbol-aware code navigation
- Adaptive context routing
- Context budget management
- Persistent project memory
- Agent orchestration
- MCP-ready integration layer
- CLI diagnostics and project setup
- Telemetry for context use and routing decisions
- Benchmarking tools for quality, cost, and efficiency

## Architecture

```text
Coding Agent
    |
    v
CodeCortex Gateway
    |
    v
Adaptive Router
    |
    +--> Repository Intelligence
    +--> Symbol Intelligence
    +--> Context Engine
    +--> Memory Engine
    |
    v
Orchestrator
    |
    +--> Tools / MCP
    +--> Validation
    +--> Telemetry
    |
    v
Response / Code Change
```

## Status

CodeCortex is under active development. The first milestone focuses on the core architecture, routing contracts, local project memory, context controls, CLI, and testable engine interfaces.

## License

License information will be added before the first public release.
