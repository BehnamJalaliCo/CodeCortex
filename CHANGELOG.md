# Changelog

All notable changes to CodeCortex are documented here. The project follows semantic versioning while in alpha; breaking changes may occur before 1.0 and will be called out explicitly.

## 0.1.0a8

- Removed obsolete named upstream attribution/provenance records from the current CodeCortex tree.
- Removed vendored/vendor-specific conformance fixtures and replaced them with repository-owned invariants.
- Made optional documentation and structural integrations explicitly configurable and vendor-neutral.
- Switched precision index discovery to CodeCortex-native `.cortexidx` paths.
- Preserved the native parser sandbox/discovery hardening already merged to `main`.
- Revalidated CI, security, Windows compatibility, packaging, Docker, and MCP release paths after the cleanup.

## Unreleased (fixes)

- Native Tree-sitter parsing now runs in a supervised worker process, so a grammar
  that faults can no longer take down `cortex index` with SIGSEGV. A crashed or
  hung worker degrades that one file to the fallback parser and indexing
  continues; `CODECORTEX_NATIVE_INPROCESS=1` restores in-process parsing.
- The native provider keeps one parser per language instead of building a new
  parser (and language) for every file.
- Repository discovery honours `.gitignore` inside a Git work tree, so ignored
  build output and nested checkouts are no longer indexed as project code.
- The structural engine is now found when it was installed by the `structural`
  extra into an isolated environment (`uv tool install`, `pipx`) whose script
  directory is not on `PATH`.

## 0.1.0a7

- Fixed a Windows lock-directory race in `FileMutex` discovered by the release matrix.
- Added bounded retry behavior for transient Windows `PermissionError` lock contention.
- Added a deterministic regression test for the transient permission-error path.
- Carries forward the GitHub discovery, onboarding, and official MCP Registry publication work from the unreleased `v0.1.0a6` attempt.

## 0.1.0a6

- Reworked GitHub discovery and first-run onboarding for CodeCortex Context Engine.
- Added official MCP Registry manifest, PyPI ownership marker, manifest validation, and release publishing.
- Surfaced Claude Code, Codex, Cursor, Gemini CLI, and OpenCode integration setup.
- Expanded MkDocs navigation, Getting Started, benchmark evidence, launch materials, and discovery documentation.
- Added contributor-friendly `good first issue` entry points and product/social discovery assets.

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
- Unified evidence model with categorical trust tiers, provenance, and a central ranking, deduplication, and conflict policy.
- Precision code intelligence: exact definition, reference, implementation, and occurrence resolution from a compiler/indexer-grade index, with symbol-identity decomposition, staleness detection, incremental caching, and graph fusion.
- Dependency intelligence: manifest and lockfile discovery across Python, Node, Rust, Go, JVM, and .NET, separating declared constraints from resolved versions, behind an optional documentation-provider contract.
- Structural search and guarded structural rewrite with typed matches, captures, expiring previews, content-hash transactions, rollback, post-apply reindexing, and validation.
- New MCP tools: `cortex_precise_definition`, `cortex_precise_references`, `cortex_precise_implementations`, `cortex_symbol_occurrences`, `cortex_precision_status`, `cortex_dependency_info`, `cortex_dependency_docs`, `cortex_dependency_context`, `cortex_structural_search`, `cortex_rewrite_preview`, and `cortex_rewrite_apply` (mutating surface only).
- New CLI commands: `definition`, `references`, `implementations`, `precision-status`, `dependency`, `dependency-docs`, `structural-search`, `rewrite-preview`, `rewrite-apply`, and `evidence-benchmark`.
- Measured heuristic-versus-evidence benchmark cases for duplicate symbol names, resolved dependency versions, and mechanical migrations; unmeasurable strategies are reported as skipped.
- `docs/EVIDENCE_FUSION.md` documents the shipped evidence-fusion surfaces and fallback behavior.

### Changed

- Python distribution identity is now `codecortex-context-engine`; the public brand remains CodeCortex Context Engine and the recommended CLI remains `cortex`.
- Optional backend processes remain isolated from the Core Python dependency environment and are pinned to exact compatible revisions.
- Documentation now treats benchmark output as evidence only after reproducible execution; missing metrics are never synthesized.
- Impact analysis weighs exact relationships above inferred ones and reports the evidence mix; `cortex doctor` reports the state of each optional evidence layer.
- The context pipeline accepts ranked evidence and keeps the stronger record when two providers point at the same location.
- The package now ships a `py.typed` marker, so `mypy --strict` runs against the distribution and is green across all source files; it is enforced in CI.

### Security

- Semantic edit paths are constrained to the repository root and reject path traversal, absolute escape, and symlink escape.
- Security reporting now uses GitHub's private vulnerability-reporting flow.
- Optional external engines run with an explicit argument vector, a resolved absolute executable, bounded runtime, and bounded output; no shell is ever used and nothing is downloaded implicitly.
- Dependency documentation is disabled by default, transmits only a library name, resolved version, and question, and reads its API key solely from a configured environment variable; credentials are redacted from diagnostics and never persisted.
- Structural rewrites require an unexpired preview, re-verify every file's content hash before writing, enforce file/match/byte limits, write atomically, and roll back on partial failure.
- Structural matches and paths are constrained to the repository root, rejecting traversal, absolute escape, and symlink escape.
