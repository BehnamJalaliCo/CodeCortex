# Project identity

## Canonical identity

**Product:** CodeCortex Context Engine  
**Short name:** CodeCortex  
**Primary CLI:** `cortex`  
**Python import:** `codecortex`  
**Python distribution:** `codecortex-context-engine`  
**Repository:** `BehnamJalaliCo/CodeCortex`

## Positioning

CodeCortex is **context intelligence infrastructure for AI coding agents**. The project should be described by its concrete capabilities — repository intelligence, semantic symbols, dependency/impact analysis, context optimization, memory, Git/PR intelligence, guarded edits, and MCP integration — rather than broad claims such as “the ultimate coding agent.”

## Name collision policy

Several unrelated software projects use CodeCortex-like names. Renaming a mature public repository prematurely would break continuity, so this project keeps the short brand while making every machine-facing and search-facing identifier explicit:

- Use **CodeCortex Context Engine** in titles and release descriptions.
- Use `codecortex-context-engine` for Python packaging.
- Use `cortex` as the recommended CLI invocation.
- Use the full GitHub repository path when linking source.
- Do not imply affiliation with unrelated projects that share a similar name.

If a future trademark, package-registry, or user-confusion issue makes the short brand materially harmful, a rename should be handled as a dedicated migration with aliases and redirects rather than an unannounced package change.

## Messaging rules

1. Never publish unmeasured performance numbers.
2. Distinguish CodeCortex-owned orchestration from optional third-party engines.
3. Describe alpha/beta status accurately.
4. Prefer reproducible commands and artifacts over marketing adjectives.
5. Keep security and local-data behavior explicit.
