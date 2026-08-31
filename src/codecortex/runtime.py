"""Runtime assembly for CLI and integration entry points."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecortex.backends.factory import build_backend_stack
from codecortex.backends.manager import BackendManager
from codecortex.config import CortexConfig
from codecortex.engines import EngineRegistry
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
    backend_manager: BackendManager
    active_backends: tuple[str, ...]
    orchestrator: Orchestrator
    gateway: CodeCortexGateway


def build_runtime(project_root: Path | None = None) -> CortexRuntime:
    config = CortexConfig(project_root=(project_root or Path.cwd()).resolve())
    config.ensure_directories()
    memory = JsonMemoryStore(config.memory_dir)
    stack = build_backend_stack(config, memory)
    router = AdaptiveRouter(default_budget=config.default_context_budget)
    telemetry = TelemetryCollector(
        enabled=config.telemetry_enabled,
        log_path=config.state_dir / "runtime" / "events.jsonl",
    )
    tracer = TaskTraceRecorder(config.state_dir / "runtime" / "traces.jsonl")
    orchestrator = Orchestrator(
        registry=stack.registry,
        router=router,
        context_processor=stack.context_processor,
        telemetry=telemetry,
        tracer=tracer,
    )
    gateway = CodeCortexGateway(
        router=router,
        orchestrator=orchestrator,
        registry=stack.registry,
        memory=memory,
    )
    return CortexRuntime(
        config=config,
        memory=memory,
        registry=stack.registry,
        router=router,
        telemetry=telemetry,
        tracer=tracer,
        backend_manager=stack.manager,
        active_backends=stack.active,
        orchestrator=orchestrator,
        gateway=gateway,
    )
