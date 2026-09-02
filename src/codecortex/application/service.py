"""Transport-neutral product service used by CLI, MCP and HTTP adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from codecortex.git_intelligence import GitIntelligence
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.memory.knowledge import ProjectKnowledgeExtractor

if TYPE_CHECKING:
    from codecortex.runtime import CortexRuntime


class ProjectOverview(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_root: str
    health: dict[str, bool]
    active_backends: tuple[str, ...]


class CortexApplicationService:
    """One product-level entry point for CodeCortex capabilities."""

    def __init__(self, runtime: "CortexRuntime") -> None:
        self.runtime = runtime

    @property
    def project_root(self) -> str:
        return str(self.runtime.config.project_root)

    async def overview(self) -> ProjectOverview:
        return ProjectOverview(
            project_root=self.project_root,
            health=await self.runtime.gateway.health(),
            active_backends=self.runtime.active_backends,
        )

    async def repository_dashboard(self) -> dict[str, Any]:
        root = self.runtime.config.project_root
        graph, graph_stats = IncrementalGraphIndex(root).refresh()
        git = GitIntelligence(root).analyze(300)
        knowledge = ProjectKnowledgeExtractor(root).extract()
        counts = graph.counts()
        symbol_count = sum(
            value for kind, value in counts.items() if kind not in {"file", "module", "reference"}
        )
        return {
            "repository": {"root": str(root), "languages": list(knowledge.languages)},
            "index": {
                "tracked": graph_stats.index.tracked,
                "added": len(graph_stats.index.added),
                "changed": len(graph_stats.index.changed),
                "removed": len(graph_stats.index.removed),
                "files_reparsed": graph_stats.files_reparsed,
                "full_rebuild": graph_stats.full_rebuild,
                "duration_ms": graph_stats.index.duration_ms,
            },
            "graph": {
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "symbols": symbol_count,
                "counts": counts,
            },
            "git": {
                "commits": git.commits,
                "hot_files": [item.path for item in git.hot_files[:8]],
            },
            "runtime": {
                "health": await self.runtime.gateway.health(),
                "active_backends": list(self.runtime.active_backends),
            },
        }

    def route(self, query: str) -> dict[str, Any]:
        plan = self.runtime.gateway.route(query, self.project_root)
        return plan.model_dump(mode="json")

    async def query(self, query: str) -> dict[str, Any]:
        result = await self.runtime.gateway.query(query, self.project_root)
        return result.model_dump(mode="json")

    async def health(self) -> dict[str, bool]:
        return await self.runtime.gateway.health()

    async def remember(self, key: str, value: str, namespace: str = "project") -> None:
        await self.runtime.gateway.remember(key, value, namespace)
