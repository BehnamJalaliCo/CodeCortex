"""Stable application gateway for every external interface."""

from __future__ import annotations

from codecortex.core.contracts import MemoryStore
from codecortex.core.models import AgentRequest, ExecutionResult, RoutePlan
from codecortex.engines import EngineRegistry
from codecortex.orchestrator import Orchestrator
from codecortex.router import AdaptiveRouter


class CodeCortexGateway:
    def __init__(
        self,
        router: AdaptiveRouter,
        orchestrator: Orchestrator,
        registry: EngineRegistry,
        memory: MemoryStore,
    ) -> None:
        self.router = router
        self.orchestrator = orchestrator
        self.registry = registry
        self.memory = memory

    def route(self, query: str, project_root: str = ".") -> RoutePlan:
        return self.router.route(AgentRequest(query=query, project_root=project_root))

    async def query(self, query: str, project_root: str = ".") -> ExecutionResult:
        return await self.orchestrator.execute(
            AgentRequest(query=query, project_root=project_root)
        )

    async def remember(self, key: str, value: str, namespace: str = "project") -> None:
        await self.memory.put(namespace, key, value)

    async def health(self) -> dict[str, bool]:
        health = await self.registry.health()
        return {capability.value: status for capability, status in health.items()}
