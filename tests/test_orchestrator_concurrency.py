import asyncio
from time import perf_counter

import pytest

from codecortex.context import BudgetContextProcessor
from codecortex.core.models import AgentRequest, Capability, EngineResult, RequestKind
from codecortex.engines import EngineRegistry
from codecortex.orchestrator import Orchestrator
from codecortex.router import AdaptiveRouter


class SlowEngine:
    def __init__(self, capability):
        self.capability = capability

    async def health(self):
        return True

    async def execute(self, request):
        await asyncio.sleep(0.08)
        return EngineResult(capability=self.capability, content="ok", chunks=[])


@pytest.mark.asyncio
async def test_independent_engines_execute_concurrently():
    registry = EngineRegistry()
    registry.register(SlowEngine(Capability.REPOSITORY))
    registry.register(SlowEngine(Capability.SYMBOLS))
    registry.register(SlowEngine(Capability.VALIDATION))
    router = AdaptiveRouter()
    orchestrator = Orchestrator(registry, router, BudgetContextProcessor())
    request = AgentRequest(query="debug and fix symbol", kind=RequestKind.DEBUG)
    started = perf_counter()
    await orchestrator.execute(request)
    elapsed = perf_counter() - started
    assert elapsed < 0.20
