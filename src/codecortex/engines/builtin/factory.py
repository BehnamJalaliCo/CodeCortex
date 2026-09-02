"""Default local engine assembly."""

from __future__ import annotations

from codecortex.config import CortexConfig
from codecortex.core.contracts import MemoryStore
from codecortex.engines.builtin.memory import MemoryEngine
from codecortex.engines.builtin.repository import RepositoryEngine
from codecortex.engines.builtin.symbols import SymbolEngine
from codecortex.engines.builtin.validation import ValidationEngine
from codecortex.engines.registry import EngineRegistry
from codecortex.memory import JsonMemoryStore
from codecortex.projects import RepositoryContext


def build_default_registry(
    config: CortexConfig,
    memory_store: MemoryStore | None = None,
) -> EngineRegistry:
    config.ensure_directories()
    memory = memory_store or JsonMemoryStore(config.memory_dir)
    repository = RepositoryContext(config.project_root)
    registry = EngineRegistry()
    registry.register(RepositoryEngine(config.project_root, context=repository))
    registry.register(SymbolEngine(config.project_root, context=repository))
    registry.register(MemoryEngine(memory))
    registry.register(ValidationEngine(config.project_root))
    return registry
