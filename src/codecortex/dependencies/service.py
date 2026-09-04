"""Dependency intelligence facade: local inventory plus optional version-aware docs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from codecortex.config import CortexConfig
from codecortex.dependencies.cache import DocumentationCache
from codecortex.dependencies.contracts import DependencyDocumentationProvider
from codecortex.dependencies.models import (
    DependencyInventory,
    DependencyRecord,
    DocumentationEvidence,
    DocumentationUnavailable,
    LibraryResolution,
)
from codecortex.dependencies.remote import RemoteDocumentationProvider, redact_secrets
from codecortex.dependencies.resolver import DependencyResolver
from codecortex.evidence.models import ProviderReport, ProviderState

PROVIDER_KEY = "dependency_docs"


@dataclass(frozen=True, slots=True)
class DependencyDocsStatus:
    """Capability report for the documentation provider."""

    enabled: bool
    provider: str
    credentials_present: bool
    cache_writable: bool
    detail: str = ""

    @property
    def label(self) -> str:
        if not self.enabled:
            return "disabled"
        if not self.credentials_present:
            return "credentials missing"
        return "available"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.label,
            "enabled": self.enabled,
            "provider": self.provider,
            "credentials_present": self.credentials_present,
            "cache_writable": self.cache_writable,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class DocumentationResult:
    """Documentation for one dependency, always carrying its provenance state."""

    library: str
    dependency: DependencyRecord | None
    resolution: LibraryResolution | None
    evidence: tuple[DocumentationEvidence, ...]
    cache_state: str
    provider_state: ProviderState
    detail: str = ""

    @property
    def available(self) -> bool:
        return bool(self.evidence)

    def report(self) -> ProviderReport:
        return ProviderReport(
            provider=PROVIDER_KEY,
            state=self.provider_state,
            detail=self.detail,
            fallback=None
            if self.available
            else "local manifest versions only; no documentation was retrieved",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "library": self.library,
            "dependency": self.dependency.to_dict() if self.dependency else None,
            "declared_version": self.dependency.declared if self.dependency else None,
            "resolved_version": self.dependency.resolved if self.dependency else None,
            "manifest": self.dependency.manifest if self.dependency else None,
            "resolution": self.resolution.to_dict() if self.resolution else None,
            "documentation": [item.to_dict() for item in self.evidence],
            "documentation_available": self.available,
            "cache_state": self.cache_state,
            "provider": self.report().model_dump(mode="json"),
        }


class DependencyIntelligence:
    """Answer version-aware dependency questions, degrading to local facts."""

    def __init__(
        self,
        root: Path,
        config: CortexConfig | None = None,
        provider: DependencyDocumentationProvider | None = None,
    ) -> None:
        self.root = root.resolve()
        self.config = config or CortexConfig.load(self.root)
        self.settings = self.config.dependency_docs
        self.cache = DocumentationCache(
            self.config.cache_dir / "dependency-docs.json",
            ttl_seconds=self.settings.cache_ttl_seconds,
        )
        self._provider = provider
        self._inventory: DependencyInventory | None = None

    # -- local facts --------------------------------------------------------

    def inventory(self, *, refresh: bool = False) -> DependencyInventory:
        if self._inventory is None or refresh:
            self._inventory = DependencyResolver(self.root).inventory()
        return self._inventory

    def lookup(self, library: str) -> DependencyRecord | None:
        """Return the best local record for a dependency name."""
        matches = self.inventory().find(library)
        if not matches:
            return None
        return sorted(matches, key=lambda item: (item.resolved is None, item.name.lower()))[0]

    # -- provider wiring ----------------------------------------------------

    def api_key(self) -> str | None:
        """Read the API key from the configured environment variable only.

        Credentials are never read from, or written to, project state.
        """
        value = os.environ.get(self.settings.api_key_env, "")
        return value.strip() or None

    def provider(self) -> DependencyDocumentationProvider | None:
        if self._provider is not None:
            return self._provider
        if not self.settings.enabled or not self.settings.base_url.strip():
            return None
        self._provider = RemoteDocumentationProvider(self.settings, self.api_key())
        return self._provider

    def status(self) -> DependencyDocsStatus:
        provider = self.provider()
        injected = provider is not None and not isinstance(provider, RemoteDocumentationProvider)
        credentials = injected or bool(self.api_key())
        detail = ""
        if not self.settings.enabled:
            detail = "dependency documentation is disabled in configuration"
        elif not self.settings.base_url.strip():
            detail = "set dependency_docs.base_url to enable documentation lookups"
        elif not credentials:
            detail = f"set {self.settings.api_key_env} to enable documentation lookups"
        return DependencyDocsStatus(
            enabled=self.settings.enabled,
            provider=self.settings.provider,
            credentials_present=credentials,
            cache_writable=self.cache.writable(),
            detail=detail,
        )

    # -- documentation ------------------------------------------------------

    async def docs(self, library: str, query: str) -> DocumentationResult:
        """Return documentation for a library at the version this repository uses."""
        dependency = self.lookup(library)
        version = dependency.effective_version if dependency else None
        provider = self.provider()
        if provider is None:
            return DocumentationResult(
                library=library,
                dependency=dependency,
                resolution=None,
                evidence=(),
                cache_state="bypassed",
                provider_state=ProviderState.NOT_CONFIGURED,
                detail="dependency documentation is disabled in configuration",
            )
        if isinstance(provider, RemoteDocumentationProvider) and not provider.has_credentials:
            return DocumentationResult(
                library=library,
                dependency=dependency,
                resolution=None,
                evidence=(),
                cache_state="bypassed",
                provider_state=ProviderState.CREDENTIALS_MISSING,
                detail=f"set {self.settings.api_key_env} to enable documentation lookups",
            )

        cache_key = self.cache.key(provider.key, library.lower(), version, query)
        fresh = self.cache.get(cache_key)
        if fresh.hit and fresh.evidence is not None:
            return DocumentationResult(
                library=library,
                dependency=dependency,
                # The stored resolution carries the version-match provenance.
                # Without it a cached fallback answer would be reported the
                # same way as a cached exact-version one.
                resolution=fresh.resolution,
                evidence=fresh.evidence,
                cache_state="hit",
                provider_state=ProviderState.AVAILABLE,
            )

        try:
            resolution = await provider.resolve_library(library, query, version)
            # Pin only a version the provider actually publishes. Appending the
            # repository's version regardless would ask for documentation that
            # does not exist, and read the provider's fallback as if it were an
            # exact-version answer.
            evidence = await provider.query_docs(
                resolution.library_id, query, resolution.matched_version
            )
        except DocumentationUnavailable as exc:
            return self._offline_result(
                library, dependency, cache_key, redact_secrets(exc.reason), pending=exc.pending
            )

        if not evidence:
            return self._offline_result(
                library, dependency, cache_key, "provider returned no documentation"
            )
        self.cache.put(cache_key, evidence, resolution)
        detail = "" if resolution.exact_version else resolution.version_detail
        return DocumentationResult(
            library=library,
            dependency=dependency,
            resolution=resolution,
            evidence=tuple(evidence),
            cache_state="miss",
            provider_state=ProviderState.AVAILABLE,
            detail=detail,
        )

    def _offline_result(
        self,
        library: str,
        dependency: DependencyRecord | None,
        cache_key: str,
        detail: str,
        *,
        pending: bool = False,
    ) -> DocumentationResult:
        """Fall back to local facts, optionally serving clearly-marked stale docs.

        A stale entry is served during an outage but never as fresh evidence:
        every record keeps ``stale=True`` and the result reports the
        ``stale`` cache state, so ranking cannot mistake it for a live answer.
        """
        if self.settings.serve_stale_when_offline:
            stale = self.cache.get(cache_key, allow_stale=True)
            if stale.hit and stale.evidence is not None:
                return DocumentationResult(
                    library=library,
                    dependency=dependency,
                    resolution=stale.resolution,
                    evidence=stale.evidence,
                    cache_state="stale",
                    provider_state=ProviderState.OFFLINE,
                    detail=f"{detail}; serving cached documentation marked stale",
                )
        return DocumentationResult(
            library=library,
            dependency=dependency,
            resolution=None,
            evidence=(),
            cache_state="miss",
            # A library the provider has but has not finished preparing is not
            # the same as a provider that cannot be reached: retrying later may
            # succeed, and the report should say which case this is.
            provider_state=ProviderState.STALE if pending else ProviderState.OFFLINE,
            detail=detail,
        )

    async def context(self, library: str, query: str) -> dict[str, object]:
        """Combine local dependency facts with documentation for an agent request."""
        result = await self.docs(library, query)
        inventory = self.inventory()
        return {
            **result.to_dict(),
            "manifests": [item.to_dict() for item in inventory.manifests],
            "ecosystems": [item.value for item in inventory.ecosystems()],
        }
