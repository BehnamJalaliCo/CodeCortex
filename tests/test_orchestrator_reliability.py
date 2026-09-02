import asyncio

from codecortex.context import BudgetContextProcessor
from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult
from codecortex.engines import EngineRegistry
from codecortex.orchestrator import EngineExecutionPolicy, Orchestrator
from codecortex.router import AdaptiveRouter


class FailingHealth(Engine):
    capability = Capability.REPOSITORY

    async def health(self) -> bool:
        raise RuntimeError("health boom")

    async def execute(self, request: AgentRequest) -> EngineResult:
        raise AssertionError("must not execute")


class SlowEngine(Engine):
    capability = Capability.REPOSITORY

    async def health(self) -> bool:
        return True

    async def execute(self, request: AgentRequest) -> EngineResult:
        await asyncio.sleep(0.05)
        return EngineResult(capability=self.capability)


class DuplicateChunkEngine(Engine):
    capability = Capability.REPOSITORY

    async def health(self) -> bool:
        return True

    async def execute(self, request: AgentRequest) -> EngineResult:
        return EngineResult(
            capability=self.capability,
            chunks=[
                ContextChunk(source="same", content="same", tokens=3, relevance=1.0),
                ContextChunk(source="same", content="same", tokens=3, relevance=0.5),
            ],
        )


def test_health_failure_degrades_instead_of_failing_request() -> None:
    registry = EngineRegistry()
    registry.register(FailingHealth())
    orchestrator = Orchestrator(registry, AdaptiveRouter())
    result = asyncio.run(orchestrator.execute(AgentRequest(query="explain repository")))
    assert result.results == []


def test_engine_timeout_is_bounded() -> None:
    registry = EngineRegistry()
    registry.register(SlowEngine())
    orchestrator = Orchestrator(
        registry,
        AdaptiveRouter(),
        policy=EngineExecutionPolicy(health_timeout_seconds=0.1, execution_timeout_seconds=0.01),
    )
    result = asyncio.run(orchestrator.execute(AgentRequest(query="explain repository")))
    assert result.results == []


def test_chunk_identity_prevents_duplicate_content_from_being_kept_twice() -> None:
    registry = EngineRegistry()
    registry.register(DuplicateChunkEngine())
    orchestrator = Orchestrator(
        registry, AdaptiveRouter(), context_processor=BudgetContextProcessor()
    )
    result = asyncio.run(orchestrator.execute(AgentRequest(query="explain repository")))
    assert len(result.results) == 1
    assert len(result.results[0].chunks) == 1
