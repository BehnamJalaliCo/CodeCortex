"""Engine contracts used by the orchestrator."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult


class Engine(ABC):
    """Base interface for every pluggable CodeCortex engine."""

    capability: Capability

    @abstractmethod
    async def health(self) -> bool:
        """Return True when the engine can serve requests."""

    @abstractmethod
    async def execute(self, request: AgentRequest) -> EngineResult:
        """Execute one request against the engine."""


class ContextProcessor(ABC):
    """Contract for context ranking and budget enforcement."""

    @abstractmethod
    async def fit(self, chunks: list[ContextChunk], budget: int) -> list[ContextChunk]:
        """Return the most useful context that fits inside the token budget."""


class MemoryStore(ABC):
    """Contract for project-scoped persistent memory."""

    @abstractmethod
    async def put(self, namespace: str, key: str, value: str) -> None:
        """Persist one memory value."""

    @abstractmethod
    async def get(self, namespace: str, key: str) -> str | None:
        """Load one memory value."""

    @abstractmethod
    async def search(self, namespace: str, query: str, limit: int = 10) -> list[str]:
        """Return relevant memory values."""
