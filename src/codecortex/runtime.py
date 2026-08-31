"""Runtime assembly for CLI and integration entry points."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecortex.config import CortexConfig
from codecortex.engines import EngineRegistry
from codecortex.engines.builtin import build_default_registry
from codecortex.gateway import CodeCortexGateway
from codecortex.memory import JsonMemoryStore
from codecortex.orchestrator import Orchestrator
from codecortex.router import AdaptiveRouter
from codecortex.telemetry import TelemetryCollector
from codecortex.tracing import TaskTraceRecorder


@dataclass(slots=True)
class CortexRuntime:
    config: CortexConfig
    memory: JsonMemoryStore
    registry: EngineRegistry
    router: AdaptiveRouter
    telemetry: TelemetryCollector
    tracer: TaskTraceRecorder
    orchestrator: Orchestrator
    gateway: CodeCortexGateway


def build_runtime(project_root: Path | None = None) -> CortexRuntime:
    config = CortexConfig(project_root=(project_root or Path.cwd()).resolve())
    config.ensure_directories()
    memory = JsonMemoryStore(config.memory_dir)
    registry = build_default_registry(config, memory_store=memory)
    router = AdaptiveRouter(default_budget=config.default_context_budget)
    telemetry = TelemetryCollector(
        enabled=config.telemetry_enabled,
        log_path=config.state_dir / "runtime" / "events.jsonl",
    )
    tracer = TaskTraceRecorder(config.state_dir / "runtime" / "traces.jsonl")
    orchestrator = Orchestrator(
        registry=registry,
        router=router,
        telemetry=telemetry,
        tracer=tracer,
    )
    gateway = CodeCortexGateway(
        router=router,
        orchestrator=orchestrator,
        registry=registry,
        memory=memory,
    )
    return CortexRuntime(
        config=config,
        memory=memory,
        registry=registry,
        router=router,
        telemetry=telemetry,
        tracer=tracer,
        orchestrator=orchestrator,
        gateway=gateway,
    )
