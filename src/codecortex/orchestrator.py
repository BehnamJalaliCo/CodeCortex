"""Core request orchestration."""

from __future__ import annotations

from codecortex.context import BudgetContextProcessor
from codecortex.core.models import AgentRequest, Capability, EngineResult, ExecutionResult
from codecortex.engines import EngineRegistry
from codecortex.router import AdaptiveRouter
from codecortex.telemetry import TelemetryCollector
from codecortex.tracing import TaskTraceRecorder


class Orchestrator:
    """Route a request, execute available engines, and fit returned context."""

    def __init__(
        self,
        registry: EngineRegistry,
        router: AdaptiveRouter,
        context_processor: BudgetContextProcessor | None = None,
        telemetry: TelemetryCollector | None = None,
        tracer: TaskTraceRecorder | None = None,
    ) -> None:
        self.registry = registry
        self.router = router
        self.context_processor = context_processor or BudgetContextProcessor()
        self.telemetry = telemetry or TelemetryCollector()
        self.tracer = tracer

    async def execute(self, request: AgentRequest) -> ExecutionResult:
        if self.tracer is None:
            return await self._execute(request, None, None)
        trace_id = str(request.metadata.get("trace_id") or self.tracer.new_trace_id())
        attributes: dict[str, object] = {"query_chars": len(request.query)}
        async with self.tracer.async_span(
            "request.execute",
            trace_id=trace_id,
            attributes=attributes,
        ) as root_span:
            result = await self._execute(request, trace_id, root_span)
            attributes["context_tokens"] = result.context_tokens
            attributes["capabilities"] = [item.value for item in result.plan.selected]
            return result.model_copy(
                update={"metadata": {**result.metadata, "trace_id": trace_id}}
            )

    async def _execute(
        self,
        request: AgentRequest,
        trace_id: str | None,
        parent_span: str | None,
    ) -> ExecutionResult:
        plan = self.router.route(request)
        self.telemetry.emit(
            "route.created",
            kind=plan.request_kind.value,
            capabilities=[capability.value for capability in plan.selected],
        )
        if self.tracer and trace_id:
            self.tracer.record(
                "route.created",
                trace_id=trace_id,
                parent_id=parent_span,
                attributes={
                    "kind": plan.request_kind.value,
                    "capabilities": [item.value for item in plan.selected],
                },
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
            if self.tracer and trace_id:
                attrs: dict[str, object] = {"capability": capability.value}
                async with self.tracer.async_span(
                    "engine.execute",
                    trace_id=trace_id,
                    parent_id=parent_span,
                    attributes=attrs,
                ):
                    result = await engine.execute(request)
                    attrs["chunks"] = len(result.chunks)
                    attrs["context_tokens"] = sum(chunk.tokens for chunk in result.chunks)
            else:
                result = await engine.execute(request)
            results.append(result)
            all_chunks.extend(result.chunks)
            self.telemetry.emit("engine.executed", capability=capability.value)

        original_tokens = sum(chunk.tokens for chunk in all_chunks)
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
            original=original_tokens,
            used=context_tokens,
            saved=max(0, original_tokens - context_tokens),
            chunks=len(fitted),
        )
        return ExecutionResult(
            request=request,
            plan=plan,
            results=normalized_results,
            context_tokens=context_tokens,
            metadata={
                "original_context_tokens": original_tokens,
                "context_tokens_saved": max(0, original_tokens - context_tokens),
            },
        )
