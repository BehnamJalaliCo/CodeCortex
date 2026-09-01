"""Capability-based engine registry."""

from __future__ import annotations

import asyncio

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

    async def health(self, timeout_seconds: float = 5.0) -> dict[Capability, bool]:
        async def probe(engine: Engine) -> bool:
            try:
                return bool(await asyncio.wait_for(engine.health(), timeout=timeout_seconds))
            except asyncio.CancelledError:
                raise
            except Exception:
                return False

        pairs = list(self._engines.items())
        values = await asyncio.gather(*(probe(engine) for _, engine in pairs))
        return {capability: status for (capability, _), status in zip(pairs, values, strict=True)}
