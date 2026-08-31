"""Memory search engine."""

from __future__ import annotations

from codecortex.core.contracts import Engine, MemoryStore
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult


class MemoryEngine(Engine):
    capability = Capability.MEMORY

    def __init__(self, store: MemoryStore, namespace: str = "project") -> None:
        self.store = store
        self.namespace = namespace

    async def health(self) -> bool:
        return True

    async def execute(self, request: AgentRequest) -> EngineResult:
        matches = await self.store.search(self.namespace, request.query, limit=10)
        content = "\n\n".join(matches) if matches else "No matching project memory found."
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source="project-memory",
                    content=content,
                    tokens=max(1, len(content) // 4),
                    relevance=0.75 if matches else 0.20,
                    metadata={"matches": len(matches)},
                )
            ],
            metadata={"matches": len(matches)},
        )
