"""Assembly of CodeCortex-owned orchestration with optional mature engines."""

from __future__ import annotations

import os
from dataclasses import dataclass

from codecortex.backends.context import ContextBackendAdapter
from codecortex.backends.graph import GraphBackendAdapter
from codecortex.backends.manager import BackendManager
from codecortex.backends.spec import BACKENDS
from codecortex.backends.symbols import SymbolBackendAdapter
from codecortex.config import CortexConfig
from codecortex.context import IntegratedContextProcessor
from codecortex.core.contracts import ContextProcessor, MemoryStore
from codecortex.engines import EngineRegistry
from codecortex.engines.builtin import build_default_registry


@dataclass(slots=True)
class BackendStack:
    registry: EngineRegistry
    context_processor: ContextProcessor
    manager: BackendManager
    active: tuple[str, ...]


def build_backend_stack(config: CortexConfig, memory_store: MemoryStore) -> BackendStack:
    registry = build_default_registry(config, memory_store=memory_store)
    manager = BackendManager()
    mode = os.getenv("CODECORTEX_BACKENDS", "auto").strip().lower()
    if mode not in {"auto", "builtin", "mature"}:
        mode = "auto"
    active: list[str] = []
    context_backend: ContextBackendAdapter | None = None
    if mode != "builtin":
        graph = GraphBackendAdapter(config.project_root, manager)
        symbols = SymbolBackendAdapter(config.project_root, manager)
        context = ContextBackendAdapter(config.project_root, manager)
        for key, adapter in (("graph", graph), ("symbols", symbols)):
            if mode == "mature" or manager.is_installed(BACKENDS[key]):
                registry.register(adapter)
                active.append(key)
        if mode == "mature" or manager.is_installed(BACKENDS["context"]):
            context_backend = context
            active.append("context")
    return BackendStack(
        registry=registry,
        context_processor=IntegratedContextProcessor(context_backend),
        manager=manager,
        active=tuple(active),
    )
