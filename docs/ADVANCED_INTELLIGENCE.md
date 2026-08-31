# Advanced Intelligence

CodeCortex now maintains several complementary representations of a software project instead of treating a repository as a bag of files.

## Language intelligence

The language layer extracts symbols, signatures, annotations, return types, inheritance and local type relationships. Python uses the standard syntax tree for precise extraction; other supported languages use conservative structural providers behind one stable registry so deeper native parsers can be added without changing callers.

## Resolution-aware graph

Repository relationships carry resolution metadata. Cross-file calls and type relationships expose confidence, ambiguity, candidate count and ranked alternatives rather than silently choosing a target when evidence is weak.

## Incremental graph

The repository manifest identifies added, changed and removed files by content state. The persisted graph then reparses dirty files, prunes stale fragments and merges new nodes and edges. Unchanged files are not reparsed.

## Hybrid retrieval

Semantic retrieval is provider-based. The default local provider is deterministic and requires no network service. An optional local neural provider can be enabled through the semantic extra. Hybrid ranking combines vector similarity, lexical overlap and structural priors.

## Git and change intelligence

History can be queried at file or symbol level. Symbol history includes commits, blame lines and ownership. Pull-request intelligence maps diff hunks back to symbols, walks impact relationships, identifies affected tests and calculates a risk score from impact, breadth and churn.

## Architecture intelligence

Architecture inference evaluates independent evidence groups and returns confidence, supporting evidence and missing signals. A saved architecture fingerprint can later be compared with the current graph to detect pattern changes, new dependency directions, coupling growth and declining resolution quality.

## Multi-repository workspaces

A workspace can register multiple repository roots. Search is federated across repository graphs, node IDs are namespaced, and matching symbols across repositories can be represented as cross-repository relationships.

## Shared team memory

Team memory uses SQLite with WAL mode, revision history, optimistic concurrency, actor/source metadata and tags. Conflicting stale writes are rejected instead of silently overwriting newer knowledge.

## Task traces

Agent requests can emit durable spans for routing and engine execution. Trace attributes are bounded and sensitive-looking keys are redacted before persistence. Trace summaries expose errors, duration, tool calls and context-token counts.

## Evaluation and regression control

Benchmark snapshots can be persisted and compared against explicit regression policies. External evaluation suites use a versioned JSON format and an agent-neutral subprocess protocol with no shell execution, deterministic checks, timeouts and resource-use limits.

## Main CLI surfaces

```text
cortex index
cortex semantic
cortex architecture
cortex architecture-baseline
cortex architecture-drift
cortex symbol-history
cortex pr
cortex team-remember
cortex team-search
cortex workspace-add
cortex workspace-search
cortex trace-summary
cortex benchmark
cortex benchmark-gate
cortex evaluate
cortex mcp
```

All state remains project-local under `.codecortex/` unless a future remote provider is explicitly configured.
