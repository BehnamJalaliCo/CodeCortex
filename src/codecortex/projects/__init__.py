"""Repository and runtime lifecycle primitives for the CodeCortex platform."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codecortex.projects.context import RepositoryContext
    from codecortex.projects.runtime_manager import CortexRuntimeManager

__all__ = ["CortexRuntimeManager", "RepositoryContext"]


def __getattr__(name: str) -> Any:
    """Load project primitives lazily to keep runtime assembly acyclic."""
    if name == "RepositoryContext":
        from codecortex.projects.context import RepositoryContext

        return RepositoryContext
    if name == "CortexRuntimeManager":
        from codecortex.projects.runtime_manager import CortexRuntimeManager

        return CortexRuntimeManager
    raise AttributeError(name)
