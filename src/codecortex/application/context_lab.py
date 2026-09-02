"""Context-pipeline inspection service for the web console."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from codecortex.context import ContextPipeline
from codecortex.indexing.incremental_graph import IncrementalGraphIndex

if TYPE_CHECKING:
    from codecortex.runtime import CortexRuntime


class ContextLabService:
    def __init__(self, runtime: CortexRuntime) -> None:
        self.runtime = runtime
        self.root = runtime.config.project_root

    async def build(self, query: str, budget: int = 32_000) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("context query is required")
        validated = self.runtime.config.validate_budget(budget)
        execution = await self.runtime.gateway.query(query, str(self.root))
        chunks = [chunk for result in execution.results for chunk in result.chunks]
        graph, _ = IncrementalGraphIndex(self.root).refresh()
        prepared = await ContextPipeline(self.root, graph).prepare(query, chunks, validated)
        return {
            "query": query,
            "budget": validated,
            "metrics": asdict(prepared.metrics),
            "trace_id": execution.metadata.get("trace_id"),
            "chunks": [chunk.model_dump(mode="json") for chunk in prepared.chunks],
        }
