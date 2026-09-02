"""Transport-neutral product service used by CLI, MCP and HTTP adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from codecortex.runtime import CortexRuntime


class ProjectOverview(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_root: str
    health: dict[str, bool]
    active_backends: tuple[str, ...]


class CortexApplicationService:
    """One product-level entry point for CodeCortex capabilities.

    Transports are deliberately thin: they validate transport concerns and delegate
    product work to this service instead of reaching into indexers or persistence.
    """

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
