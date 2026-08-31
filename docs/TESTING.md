# Testing Strategy

CodeCortex has three test rings.

1. **Core CI** runs on every push across supported Python versions and covers CodeCortex-owned logic.
2. **Adapter conformance** provisions each pinned backend in isolation and verifies the stable CodeCortex contract, including MCP tool discovery where applicable.
3. **Upstream regression** checks the pinned source revisions with their native test suites on a scheduled/manual workflow. It is informational rather than a merge blocker because upstream suites may require platform services, external language servers, large model downloads or other environment-specific dependencies.

A backend update is accepted only after its adapter contract is green. Version pins are intentionally explicit so a new upstream release cannot silently change production behavior.
