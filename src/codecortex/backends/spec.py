"""Pinned backend specifications used by the CodeCortex engine layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackendSpec:
    key: str
    package: str
    source_url: str
    revision: str
    command: str
    license_id: str
    capabilities: tuple[str, ...]
    extras: tuple[str, ...] = ()
    python: str = "3.13"
    vendor_path: str | None = None

    @property
    def source_requirement(self) -> str:
        """Remote fallback requirement used when the vendored checkout is absent."""
        if not self.extras:
            return f"git+{self.source_url}@{self.revision}"
        extras = ",".join(self.extras)
        return f"{self.package}[{extras}] @ git+{self.source_url}@{self.revision}"


BACKENDS: dict[str, BackendSpec] = {
    "graph": BackendSpec(
        key="graph",
        package="graphifyy",
        source_url="https://github.com/Graphify-Labs/graphify.git",
        revision="33362d969292b57eda82f3fbd9eb5f3f5bc9bbc2",
        command="graphify",
        license_id="Apache-2.0",
        capabilities=("ast", "graph", "query", "path", "explain", "incremental"),
        vendor_path="vendor/graph-engine",
    ),
    "symbols": BackendSpec(
        key="symbols",
        package="serena-agent",
        source_url="https://github.com/oraios/serena.git",
        revision="43ae0211d7f3bba4101cd0552707fa21d37f4c84",
        command="serena",
        license_id="MIT",
        capabilities=("lsp", "symbols", "references", "diagnostics", "editing", "refactor"),
        vendor_path="vendor/symbol-engine",
    ),
    "context": BackendSpec(
        key="context",
        package="headroom-ai",
        source_url="https://github.com/headroomlabs-ai/headroom.git",
        revision="65477f933a775bd519d4b037d31d93b3e255e297",
        command="headroom",
        license_id="Apache-2.0",
        capabilities=("compression", "routing", "reversible", "memory", "proxy", "mcp"),
        extras=("mcp", "code", "memory", "relevance"),
        vendor_path="vendor/context-engine",
    ),
}
