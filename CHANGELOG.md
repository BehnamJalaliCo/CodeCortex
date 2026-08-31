# Changelog

All notable changes to CodeCortex are documented here. The project follows semantic versioning while in alpha; breaking changes may occur before 1.0 and will be called out explicitly.

## Unreleased

### Added

- Revision-pinned isolated graph, semantic-symbol/LSP, and context-optimization backends behind stable CodeCortex contracts.
- Guarded language-server rename, replace-body, insert-before, and insert-after operations in CLI and MCP.
- Warm backend MCP session pooling, health caching, failure recovery, and concurrent orchestration.
- Native Tree-sitter parser provider with conservative fallback.
- Expanded reproducible real-repository benchmark corpus and live coding-agent E2E harness.
- Docker Core/Full integration CI.
- CodeQL, dependency review, Bandit, dependency audit, SBOM generation, and security-boundary tests.
- Production observability dashboard with traces, graph hotspots, architecture drift, benchmark history, latency, token savings, and PR-risk API.
- Signed release pipeline with checksums, Sigstore bundles, GitHub provenance attestations, PyPI Trusted Publishing, and GHCR publishing.

### Changed

- Python distribution identity is now `codecortex-context-engine`; the public brand remains CodeCortex Context Engine and the recommended CLI remains `cortex`.
- Optional backend processes remain isolated from the Core Python dependency environment and are pinned to exact compatible revisions.
- Documentation now treats benchmark output as evidence only after reproducible execution; missing metrics are never synthesized.

### Security

- Semantic edit paths are constrained to the repository root and reject path traversal, absolute escape, and symlink escape.
- Security reporting now uses GitHub's private vulnerability-reporting flow.
