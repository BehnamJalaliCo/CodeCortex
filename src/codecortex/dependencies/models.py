"""Typed models for dependency inventory and version-aware documentation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Ecosystem(StrEnum):
    PYTHON = "python"
    NODE = "node"
    RUST = "rust"
    GO = "go"
    JVM = "jvm"
    DOTNET = "dotnet"


class DependencyScope(StrEnum):
    RUNTIME = "runtime"
    DEVELOPMENT = "development"
    OPTIONAL = "optional"
    BUILD = "build"


@dataclass(frozen=True, slots=True)
class DependencyRecord:
    """One dependency as declared and, where a lockfile exists, as resolved."""

    ecosystem: Ecosystem
    name: str
    declared: str | None = None
    resolved: str | None = None
    manifest: str = ""
    lock_source: str | None = None
    scope: DependencyScope = DependencyScope.RUNTIME

    @property
    def effective_version(self) -> str | None:
        """The version documentation should be requested for.

        The resolved lockfile version is authoritative: a declared constraint
        such as ``^5.0.0`` does not say which API the repository actually runs.
        """
        return self.resolved or None

    @property
    def key(self) -> str:
        return f"{self.ecosystem.value}:{self.name.lower()}"

    def to_dict(self) -> dict[str, object]:
        return {
            "ecosystem": self.ecosystem.value,
            "name": self.name,
            "declared_version": self.declared,
            "resolved_version": self.resolved,
            "effective_version": self.effective_version,
            "manifest": self.manifest,
            "lock_source": self.lock_source,
            "scope": self.scope.value,
        }


@dataclass(frozen=True, slots=True)
class ManifestReport:
    """A manifest that was read, and any problem encountered while reading it."""

    path: str
    ecosystem: Ecosystem
    parsed: bool
    detail: str = ""
    dependencies: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "ecosystem": self.ecosystem.value,
            "parsed": self.parsed,
            "detail": self.detail,
            "dependencies": self.dependencies,
        }


@dataclass(frozen=True, slots=True)
class DependencyInventory:
    """Every dependency discovered in the repository, merged across manifests."""

    records: tuple[DependencyRecord, ...] = ()
    manifests: tuple[ManifestReport, ...] = ()

    def find(self, name: str) -> tuple[DependencyRecord, ...]:
        needle = name.strip().lower()
        exact = tuple(item for item in self.records if item.name.lower() == needle)
        if exact:
            return exact
        return tuple(item for item in self.records if needle and needle in item.name.lower())

    def ecosystems(self) -> tuple[Ecosystem, ...]:
        return tuple(sorted({item.ecosystem for item in self.records}))

    def to_dict(self) -> dict[str, object]:
        return {
            "dependencies": [item.to_dict() for item in self.records],
            "manifests": [item.to_dict() for item in self.manifests],
            "ecosystems": [item.value for item in self.ecosystems()],
        }


@dataclass(frozen=True, slots=True)
class LibraryResolution:
    """A documentation provider's answer to "which library is this?"."""

    library_id: str
    title: str = ""
    description: str = ""
    versions: tuple[str, ...] = ()
    matched_version: str | None = None
    provider: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "library_id": self.library_id,
            "title": self.title,
            "description": self.description,
            "versions": list(self.versions),
            "matched_version": self.matched_version,
            "provider": self.provider,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class DocumentationEvidence:
    """One documentation excerpt tied to a library and a version."""

    library_id: str
    content: str
    version: str | None = None
    title: str = ""
    url: str = ""
    provider: str = ""
    stale: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "library_id": self.library_id,
            "title": self.title,
            "version": self.version,
            "url": self.url,
            "provider": self.provider,
            "stale": self.stale,
            "content": self.content,
            "metadata": dict(self.metadata),
        }


class DocumentationUnavailable(RuntimeError):
    """Raised when a documentation provider cannot answer.

    The reason is preserved so CodeCortex can report an explicit
    docs-unavailable state instead of inventing documentation.
    """

    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable
