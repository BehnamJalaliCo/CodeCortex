"""Contract for pluggable dependency documentation providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codecortex.dependencies.models import DocumentationEvidence, LibraryResolution


class DependencyDocumentationProvider(ABC):
    """Resolve a library and return documentation for a specific version.

    Implementations must raise
    :class:`~codecortex.dependencies.models.DocumentationUnavailable` rather
    than returning fabricated content when they cannot answer.
    """

    key: str

    @abstractmethod
    async def health(self) -> bool:
        """Return True when the provider is configured and reachable."""

    @abstractmethod
    async def resolve_library(
        self,
        name: str,
        query: str,
        version: str | None,
    ) -> LibraryResolution:
        """Map a package name to the provider's library identifier."""

    @abstractmethod
    async def query_docs(
        self,
        library_id: str,
        query: str,
        version: str | None,
    ) -> list[DocumentationEvidence]:
        """Return documentation excerpts for a library at a version."""
