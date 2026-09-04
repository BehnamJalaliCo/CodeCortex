"""Dependency intelligence: manifest inventory and version-aware documentation."""

from codecortex.dependencies.cache import CacheLookup, DocumentationCache
from codecortex.dependencies.contracts import DependencyDocumentationProvider
from codecortex.dependencies.manifests import ManifestScanner
from codecortex.dependencies.models import (
    DependencyInventory,
    DependencyRecord,
    DependencyScope,
    DocumentationEvidence,
    DocumentationUnavailable,
    Ecosystem,
    LibraryResolution,
    ManifestReport,
)
from codecortex.dependencies.provider import DependencyEvidenceProvider
from codecortex.dependencies.remote import RemoteDocumentationProvider, redact_secrets
from codecortex.dependencies.resolver import DependencyResolver
from codecortex.dependencies.service import (
    DependencyDocsStatus,
    DependencyIntelligence,
    DocumentationResult,
)

__all__ = [
    "CacheLookup",
    "DependencyDocsStatus",
    "DependencyDocumentationProvider",
    "DependencyEvidenceProvider",
    "DependencyIntelligence",
    "DependencyInventory",
    "DependencyRecord",
    "DependencyResolver",
    "DependencyScope",
    "DocumentationCache",
    "DocumentationEvidence",
    "DocumentationResult",
    "DocumentationUnavailable",
    "Ecosystem",
    "LibraryResolution",
    "ManifestReport",
    "ManifestScanner",
    "RemoteDocumentationProvider",
    "redact_secrets",
]
