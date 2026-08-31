"""Graph-backed local repository intelligence engine."""

from __future__ import annotations

from pathlib import Path

from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult
from codecortex.indexing import ProjectIndexer


class RepositoryEngine(Engine):
    capability = Capability.REPOSITORY

    def __init__(self, project_root: Path, max_files: int = 5_000) -> None:
        self.project_root = project_root.resolve()
        self.max_files = max_files

    async def health(self) -> bool:
        return self.project_root.exists() and self.project_root.is_dir()

    async def execute(self, request: AgentRequest) -> EngineResult:
        graph = ProjectIndexer(self.project_root, max_files=self.max_files).build()
        graph_path = self.project_root / ".codecortex" / "index" / "graph.json"
        graph.save(graph_path)

        counts = graph.counts()
        matches = graph.search(request.query)
        import_edges = sum(1 for edge in graph.edges if edge.kind == "imports")
        define_edges = sum(1 for edge in graph.edges if edge.kind == "defines")

        summary = [
            f"Project root: {self.project_root}",
            f"Graph nodes: {len(graph.nodes)}",
            f"Graph edges: {len(graph.edges)}",
            f"Files: {counts.get('file', 0)}",
            f"Symbols: {define_edges}",
            f"Import relationships: {import_edges}",
        ]
        if matches:
            summary.append(
                "Relevant graph nodes:\n"
                + "\n".join(
                    f"- {node.kind}: {node.name}"
                    + (f" ({node.path}:{node.line or 1})" if node.path else "")
                    for node in matches
                )
            )

        content = "\n".join(summary)
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source="repository-graph",
                    content=content,
                    tokens=max(1, len(content) // 4),
                    relevance=0.85,
                    metadata={
                        "nodes": len(graph.nodes),
                        "edges": len(graph.edges),
                        "matches": len(matches),
                    },
                )
            ],
            metadata={
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "node_counts": counts,
                "graph_path": str(graph_path),
            },
        )
