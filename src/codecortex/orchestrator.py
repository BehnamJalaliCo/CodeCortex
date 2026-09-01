"""Core request orchestration with bounded engine execution and feedback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter

from codecortex.context import BudgetContextProcessor
from codecortex.core.contracts import ContextProcessor, Engine
from codecortex.core.models import AgentRequest, Capability, EngineResult, ExecutionResult
from codecortex.engines import EngineRegistry
from codecortex.feedback import AgentFeedbackStore
from codecortex.router import AdaptiveRouter
from codecortex.telemetry import TelemetryCollector
from codecortex.tracing import TaskTraceRecorder


@dataclass(frozen=True, slots=True)
class EngineExecutionPolicy:
    health_timeout_seconds: float = 5.0
    execution_timeout_seconds: float = 120.0
    max_retries: int = 0

    def __post_init__(self) -> None:
        if self.health_timeout_seconds <= 0 or self.execution_timeout_seconds <= 0:
            raise ValueError("engine timeouts must be positive")
        if not 0 <= self.max_retries <= 2:
            raise ValueError("max_retries must be between 0 and 2")


class Orchestrator:
    def __init__(self, registry: EngineRegistry, router: AdaptiveRouter, context: ContextProcessor | None = None, telemetry: TelemetryCollector | None = None, feedback: AgentFeedbackStore | None = None, tracer: TaskTraceRecorder | None = None, policy: EngineExecutionPolicy | None = None) -> None:
        self.registry = registry
        self.router = router
        self.context = context or BudgetContextProcessor()
        self.telemetry = telemetry or TelemetryCollector()
        self.feedback = feedback
        self.tracer = tracer
        self.policy = policy or EngineExecutionPolicy()

    async def execute(self, request: AgentRequest) -> ExecutionResult:
        trace_id = self.tracer.new_trace_id() if self.tracer else None
        plan = self.router.route(request)
        parent_span: str | None = None
        if self.tracer and trace_id:
            with self.tracer.span("orchestrator.execute", trace_id=trace_id, attributes={"kind": plan.request_kind.value}) as span:
                parent_span = span.span_id
                results = await self._execute_selected(plan.selected, request, trace_id, parent_span)
        else:
            results = await self._execute_selected(plan.selected, request, trace_id, parent_span)
        chunks = [chunk for result in results for chunk in result.chunks]
        fitted = await self.context.fit(chunks, plan.context_budget)
        return ExecutionResult(request=request, plan=plan, results=results, context_tokens=sum(chunk.tokens for chunk in fitted), metadata={"trace_id": trace_id} if trace_id else {})

    async def _execute_selected(self, selected: list[Capability], request: AgentRequest, trace_id: str | None, parent_span: str | None) -> list[EngineResult]:
        tasks = [self._run_engine(capability, request, trace_id, parent_span) for capability in selected]
        values = await asyncio.gather(*tasks)
        return [value for value in values if value is not None]

    async def _healthy(self, capability: Capability, request: AgentRequest) -> bool:
        engine = self.registry.get(capability)
        if engine is None:
            return False
        timeout = float(request.metadata.get("engine_health_timeout_seconds", self.policy.health_timeout_seconds))
        try:
            return bool(await asyncio.wait_for(engine.health(), timeout=max(0.01, timeout)))
        except asyncio.CancelledError:
            raise
        except Exception:
            return False

    def _record_feedback(self, request: AgentRequest, capability: Capability, success: bool, latency_ms: float) -> None:
        if self.feedback is not None:
            self.feedback.record(request.query, capability, success, latency_ms)

    async def _execute_engine_once(self, engine: Engine, capability: Capability, request: AgentRequest, trace_id: str | None, parent_span: str | None, attempt_number: int) -> EngineResult:
        if self.tracer and trace_id:
            attrs: dict[str, object] = {"capability": capability.value, "attempt": attempt_number}
            async with self.tracer.async_span("engine.execute", trace_id=trace_id, parent_id=parent_span, attributes=attrs):
                result = await engine.execute(request)
                attrs["chunks"] = len(result.chunks)
                attrs["context_tokens"] = sum(chunk.tokens for chunk in result.chunks)
                return result
        return await engine.execute(request)

    async def _run_engine(self, capability: Capability, request: AgentRequest, trace_id: str | None, parent_span: str | None) -> EngineResult | None:
        engine = self.registry.get(capability)
        if engine is None or not await self._healthy(capability, request):
            self.telemetry.emit("engine.skipped", capability=capability.value)
            return None
        retries = request.metadata.get("engine_retries", self.policy.max_retries)
        retries = max(0, min(2, int(retries)))
        timeout = max(0.01, float(request.metadata.get("engine_timeout_seconds", self.policy.execution_timeout_seconds)))
        started = perf_counter()
        for attempt in range(retries + 1):
            try:
                result = await asyncio.wait_for(self._execute_engine_once(engine, capability, request, trace_id, parent_span, attempt + 1), timeout=timeout)
                duration_ms = (perf_counter() - started) * 1000
                self.telemetry.emit("engine.executed", capability=capability.value, duration_ms=duration_ms, attempts=attempt + 1)
                self._record_feedback(request, capability, True, duration_ms)
                return result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt >= retries:
                    duration_ms = (perf_counter() - started) * 1000
                    self.telemetry.emit("engine.failed", capability=capability.value, duration_ms=duration_ms, error=type(exc).__name__)
                    self._record_feedback(request, capability, False, duration_ms)
                    return None
        return None
