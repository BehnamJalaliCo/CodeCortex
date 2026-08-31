# Roadmap

## 0.1 — Core

- [x] Typed core contracts
- [x] Adaptive request router
- [x] Orchestration layer
- [x] Context budget enforcement
- [x] Local project memory
- [x] Repository intelligence
- [x] Multi-language symbol intelligence
- [x] Validation engine
- [x] CLI and diagnostics
- [x] Integration tool bridge
- [x] Local dashboard
- [x] Incremental repository index
- [x] Dependency and call graph
- [x] Impact analysis
- [x] Git-aware change intelligence
- [x] Automatic project knowledge extraction
- [x] Query-aware context ranking and deduplication
- [x] Query result caching
- [x] Native MCP stdio transport
- [x] One-command project setup
- [x] Reproducible benchmark suite
- [x] CI across supported Python versions

## 0.2 — Intelligence

- [x] Deeper language-aware parsing and type resolution
- [x] Cross-file call resolution with ambiguity scoring
- [x] Incremental graph updates without full graph rebuilds
- [x] Semantic retrieval providers
- [x] Git-aware symbol history and blame intelligence
- [x] Architecture pattern inference with confidence scores
- [x] Persistent benchmark history and regression gates

## 0.3 — Agent workflows

- [x] Multi-repository context
- [x] Shared local team memory
- [x] Pull request intelligence
- [x] Architecture drift detection
- [x] Agent task traces
- [x] Reproducible external evaluation suites
- [x] Guarded language-server semantic editing
- [x] Live coding-agent MCP E2E harness

## 0.4 — Production hardening

- [x] Native Tree-sitter parser providers with structural fallback
- [x] Warm persistent backend sessions and concurrent orchestration
- [x] Live backend conformance against pinned revisions
- [x] Docker Core/Full integration CI
- [x] Expanded real-repository benchmark corpus and CI artifacts
- [x] Signed/attested release pipeline and automated package/container publishing
- [x] Security audit, CodeQL, dependency review, SBOM, and path-boundary tests
- [x] Observatory dashboard for traces, drift, graph health, benchmark history, and PR risk
- [x] Canonical package/brand identity policy

## 0.5 — Distributed scale

- [x] Remote shared-memory synchronization with conflict resolution
- [x] Persistent vector-database providers for very large repositories
- [x] Hosted/remote MCP transport with authentication, TLS, quotas, and access policy
- [x] Multi-node indexing and retrieval workers
- [x] Published longitudinal performance history from scheduled reproducible runs
- [x] Organization-level policy, audit retention, and workspace administration

## Release gates

A public release is considered evidence-backed only when the exact release commit has passed Core CI, backend conformance, parser-provider tests, Docker integration, security checks, and the relevant benchmark run. Credential-gated external services must be reported as skipped rather than silently treated as passed.
