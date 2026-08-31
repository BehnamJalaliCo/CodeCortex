"""Assembly of CodeCortex-owned intelligence with optional configured adapters."""

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
    mode = os.getenv("CODECORTEX_BACKENDS", "builtin").strip().lower()
    if mode == "mature":
        mode = "external"
    if mode not in {"auto", "builtin", "external"}:
        mode = "builtin"

    active: list[str] = []
    context_backend: ContextBackendAdapter | None = None
    if mode != "builtin":
        graph = GraphBackendAdapter(config.project_root, manager)
        symbols = SymbolBackendAdapter(config.project_root, manager)
        context = ContextBackendAdapter(config.project_root, manager)
        for key, adapter in (("graph", graph), ("symbols", symbols)):
            spec = BACKENDS[key]
            if spec.configured and (mode == "external" or manager.is_installed(spec)):
                registry.register(adapter)
                active.append(key)
        context_spec = BACKENDS["context"]
        if context_spec.configured and (
            mode == "external" or manager.is_installed(context_spec)
        ):
            context_backend = context
            active.append("context")

    return BackendStack(
        registry=registry,
        context_processor=IntegratedContextProcessor(context_backend),
        manager=manager,
        active=tuple(active),
    )
