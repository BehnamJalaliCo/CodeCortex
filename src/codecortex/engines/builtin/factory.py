"""Default local engine assembly."""

from __future__ import annotations

from codecortex.config import CortexConfig
from codecortex.engines.builtin.memory import MemoryEngine
from codecortex.engines.builtin.repository import RepositoryEngine
from codecortex.engines.builtin.symbols import SymbolEngine
from codecortex.engines.builtin.validation import ValidationEngine
from codecortex.engines.registry import EngineRegistry
from codecortex.memory import JsonMemoryStore


def build_default_registry(config: CortexConfig) -> EngineRegistry:
    config.ensure_directories()
    memory = JsonMemoryStore(config.memory_dir)
    registry = EngineRegistry()
    registry.register(RepositoryEngine(config.project_root))
    registry.register(SymbolEngine(config.project_root))
    registry.register(MemoryEngine(memory))
    registry.register(ValidationEngine(config.project_root))
    return registry
