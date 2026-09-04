"""Core request orchestration with bounded engine execution and feedback."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter

from codecortex.context import BudgetContextProcessor
from codecortex.core.contracts import ContextProcessor
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
    def __init__(
        self,
        registry: EngineRegistry,
        router: AdaptiveRouter,
        context_processor: ContextProcessor | None = None,
        telemetry: TelemetryCollector | None = None,
        tracer: TaskTraceRecorder | None = None,
        policy: EngineExecutionPolicy | None = None,
        feedback: AgentFeedbackStore | None = None,
    ) -> None:
        self.registry = registry
        self.router = router
        self.context_processor = context_processor or BudgetContextProcessor()
        self.telemetry = telemetry or TelemetryCollector()
        self.tracer = tracer
        self.policy = policy or EngineExecutionPolicy()
        self.feedback = feedback

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
            return result.model_copy(update={"metadata": {**result.metadata, "trace_id": trace_id}})

    async def _healthy(self, capability: Capability, request: AgentRequest) -> bool:
        engine = self.registry.get(capability)
        if engine is None:
            return False
        try:
            return bool(
                await asyncio.wait_for(
                    engine.health(),
                    timeout=self.policy.health_timeout_seconds,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.telemetry.emit(
                "engine.health_failed",
                capability=capability.value,
                error_type=type(exc).__name__,
            )
            if request.metadata.get("strict_engines"):
                raise
            return False

    def _record_feedback(
        self,
        request: AgentRequest,
        capability: Capability,
        success: bool,
        latency_ms: float,
    ) -> None:
        if self.feedback is not None:
            self.feedback.record(request.query, capability, success, latency_ms)

    async def _execute_engine_once(
        self,
        engine: object,
        capability: Capability,
        request: AgentRequest,
        trace_id: str | None,
        parent_span: str | None,
        attempt_number: int,
    ) -> EngineResult:
        execute: Callable[[AgentRequest], Awaitable[EngineResult]] = engine.execute  # type: ignore[attr-defined]
        if self.tracer and trace_id:
            attrs: dict[str, object] = {
                "capability": capability.value,
                "attempt": attempt_number,
            }
            async with self.tracer.async_span(
                "engine.execute",
                trace_id=trace_id,
                parent_id=parent_span,
                attributes=attrs,
            ):
                result = await execute(request)
                attrs["chunks"] = len(result.chunks)
                attrs["context_tokens"] = sum(chunk.tokens for chunk in result.chunks)
                return result
        return await execute(request)

    async def _run_engine(
        self,
        capability: Capability,
        request: AgentRequest,
        trace_id: str | None,
        parent_span: str | None,
    ) -> EngineResult | None:
        engine = self.registry.get(capability)
        if engine is None or not await self._healthy(capability, request):
            self.telemetry.emit("engine.skipped", capability=capability.value)
            return None
        retries = request.metadata.get("engine_retries", self.policy.max_retries)
        retries = (
            max(0, min(2, int(retries))) if isinstance(retries, int) else self.policy.max_retries
        )
        started = perf_counter()
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._execute_engine_once(
                        engine,
                        capability,
                        request,
                        trace_id,
                        parent_span,
                        attempt + 1,
                    ),
                    timeout=self.policy.execution_timeout_seconds,
                )
                latency_ms = (perf_counter() - started) * 1000
                self.telemetry.emit(
                    "engine.executed",
                    capability=capability.value,
                    duration_ms=latency_ms,
                    attempts=attempt + 1,
                )
                self._record_feedback(request, capability, True, latency_ms)
                return result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                self.telemetry.emit(
                    "engine.failed",
                    capability=capability.value,
                    error_type=type(exc).__name__,
                    attempt=attempt + 1,
                )
                if attempt < retries:
                    continue
        latency_ms = (perf_counter() - started) * 1000
        self._record_feedback(request, capability, False, latency_ms)
        if request.metadata.get("strict_engines") and last_error is not None:
            raise last_error
        return None

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
        capabilities = [item for item in plan.selected if item != Capability.CONTEXT]
        outcomes = await asyncio.gather(
            *(
                self._run_engine(capability, request, trace_id, parent_span)
                for capability in capabilities
            )
        )
        results = [result for result in outcomes if result is not None]
        all_chunks = [chunk for result in results for chunk in result.chunks]
        original_tokens = sum(chunk.tokens for chunk in all_chunks)
        fitted = await self.context_processor.fit(all_chunks, plan.context_budget)
        fitted_ids = {chunk.chunk_id for chunk in fitted}
        normalized_results = [
            result.model_copy(
                update={
                    "chunks": [chunk for chunk in result.chunks if chunk.chunk_id in fitted_ids]
                }
            )
            for result in results
        ]
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
