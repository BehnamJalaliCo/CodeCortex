"""Expose dependency documentation as ranked evidence."""

from __future__ import annotations

import asyncio
from pathlib import Path

from codecortex.config import CortexConfig
from codecortex.dependencies.contracts import DependencyDocumentationProvider
from codecortex.dependencies.service import PROVIDER_KEY, DependencyIntelligence
from codecortex.evidence.contracts import EvidenceProvider
from codecortex.evidence.models import (
    EvidenceBundle,
    EvidenceKind,
    EvidenceRecord,
    EvidenceRequest,
    ProviderReport,
    ProviderState,
    TrustTier,
)

#: Documentation is authoritative for API shape but is not source truth, so it
#: never claims the exact tier reserved for compiler-resolved code evidence.
FRESH_DOC_CONFIDENCE = 0.85
STALE_DOC_CONFIDENCE = 0.45

#: Metadata key an agent request uses to name the library it is asking about.
LIBRARY_METADATA_KEY = "library"


class DependencyEvidenceProvider(EvidenceProvider):
    """Turn version-aware documentation into evidence records."""

    key = PROVIDER_KEY

    def __init__(
        self,
        root: Path,
        config: CortexConfig | None = None,
        documentation: DependencyDocumentationProvider | None = None,
    ) -> None:
        self.root = root.resolve()
        self.config = config or CortexConfig.load(self.root)
        self.service = DependencyIntelligence(self.root, self.config, documentation)

    async def health(self) -> bool:
        status = await asyncio.to_thread(self.service.status)
        return status.enabled and status.credentials_present

    async def collect(self, request: EvidenceRequest) -> EvidenceBundle:
        library = str(request.metadata.get(LIBRARY_METADATA_KEY, "") or request.symbol or "")
        if not library:
            return EvidenceBundle(
                records=[],
                providers=[
                    ProviderReport(
                        provider=self.key,
                        state=ProviderState.NOT_CONFIGURED,
                        detail="no library was named in the request",
                        fallback="local repository evidence only",
                    )
                ],
            )
        result = await self.service.docs(library, request.query or library)
        version = result.dependency.effective_version if result.dependency else None
        records = [
            EvidenceRecord(
                kind=EvidenceKind.DOCUMENTATION,
                provider=self.key,
                provenance=item.provider or "dependency-documentation",
                trust=TrustTier.STRUCTURAL if not item.stale else TrustTier.INFERRED,
                symbol=item.library_id,
                content=item.content,
                confidence=STALE_DOC_CONFIDENCE if item.stale else FRESH_DOC_CONFIDENCE,
                stale=item.stale,
                metadata={
                    "library": library,
                    "library_id": item.library_id,
                    "version": item.version or version,
                    "declared_version": result.dependency.declared if result.dependency else None,
                    "resolved_version": version,
                    "manifest": result.dependency.manifest if result.dependency else None,
                    "cache_state": result.cache_state,
                    "url": item.url,
                },
            )
            for item in result.evidence[: request.limit]
        ]
        return EvidenceBundle(records=records, providers=[result.report()])
