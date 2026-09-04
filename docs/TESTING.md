# Testing Strategy

CodeCortex has three test rings.

1. **Core CI** runs on every push across supported Python versions and covers CodeCortex-owned logic.
2. **Adapter conformance** provisions each pinned backend in isolation and verifies the stable CodeCortex contract, including MCP tool discovery where applicable.
3. **Upstream regression** checks the pinned source revisions with their native test suites on a scheduled/manual workflow. It is informational rather than a merge blocker because upstream suites may require platform services, external language servers, large model downloads or other environment-specific dependencies.

## Optional evidence layers

The three evidence-fusion layers are optional, so their tests must not require
optional components to be installed:

- **Precision code intelligence** is tested against index fixtures serialized
  with the real binary encoding (`tests/fixtures/precision_index.py`), so the
  wire reader, symbol-identity grammar, staleness detection, and fallback paths
  are exercised without any external indexer.
- **Dependency documentation** is tested against a deterministic fake provider
  and a local HTTP stub. No account, credential, or network egress is required,
  and one test asserts that outgoing requests carry no repository content.
- **Structural search and rewrite** drive the real subprocess code path against
  an in-repository stub engine invoked through `sys.executable`, so the adapter,
  limits, and transaction handling are covered on every platform. Tests that
  need the real engine skip themselves when it is absent; the pinned binary is
  exercised in the `Structural Engine` workflow.

A backend update is accepted only after its adapter contract is green. Version pins are intentionally explicit so a new upstream release cannot silently change production behavior.
