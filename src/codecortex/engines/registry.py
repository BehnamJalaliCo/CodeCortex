"""Capability-based engine registry."""

from __future__ import annotations

from codecortex.core.contracts import Engine
from codecortex.core.models import Capability


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[Capability, Engine] = {}

    def register(self, engine: Engine) -> None:
        self._engines[engine.capability] = engine

    def get(self, capability: Capability) -> Engine | None:
        return self._engines.get(capability)

    def capabilities(self) -> list[Capability]:
        return list(self._engines)

    async def health(self) -> dict[Capability, bool]:
        result: dict[Capability, bool] = {}
        for capability, engine in self._engines.items():
            result[capability] = await engine.health()
        return result
