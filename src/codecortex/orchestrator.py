"""Core request orchestration."""

from __future__ import annotations

from codecortex.context import BudgetContextProcessor
from codecortex.core.models import AgentRequest, Capability, EngineResult, ExecutionResult
from codecortex.engines import EngineRegistry
from codecortex.router import AdaptiveRouter
from codecortex.telemetry import TelemetryCollector


class Orchestrator:
    """Route a request, execute available engines, and fit returned context."""

    def __init__(
        self,
        registry: EngineRegistry,
        router: AdaptiveRouter,
        context_processor: BudgetContextProcessor | None = None,
        telemetry: TelemetryCollector | None = None,
    ) -> None:
        self.registry = registry
        self.router = router
        self.context_processor = context_processor or BudgetContextProcessor()
        self.telemetry = telemetry or TelemetryCollector()

    async def execute(self, request: AgentRequest) -> ExecutionResult:
        plan = self.router.route(request)
        self.telemetry.emit(
            "route.created",
            kind=plan.request_kind.value,
            capabilities=[capability.value for capability in plan.selected],
        )

        results: list[EngineResult] = []
        all_chunks = []
        for capability in plan.selected:
            if capability == Capability.CONTEXT:
                continue
            engine = self.registry.get(capability)
            if engine is None or not await engine.health():
                self.telemetry.emit("engine.skipped", capability=capability.value)
                continue
            result = await engine.execute(request)
            results.append(result)
            all_chunks.extend(result.chunks)
            self.telemetry.emit("engine.executed", capability=capability.value)

        fitted = await self.context_processor.fit(all_chunks, plan.context_budget)
        fitted_sources = {(chunk.source, chunk.content) for chunk in fitted}
        normalized_results: list[EngineResult] = []
        for result in results:
            kept = [
                chunk for chunk in result.chunks if (chunk.source, chunk.content) in fitted_sources
            ]
            normalized_results.append(result.model_copy(update={"chunks": kept}))

        context_tokens = sum(chunk.tokens for chunk in fitted)
        self.telemetry.emit(
            "context.fitted",
            budget=plan.context_budget,
            used=context_tokens,
            chunks=len(fitted),
        )
        return ExecutionResult(
            request=request,
            plan=plan,
            results=normalized_results,
            context_tokens=context_tokens,
        )
