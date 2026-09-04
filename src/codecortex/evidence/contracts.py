"""Provider contract every evidence source implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codecortex.evidence.models import EvidenceBundle, EvidenceRequest


class EvidenceProvider(ABC):
    """Contract for a source of ranked, attributable evidence.

    Providers are optional by construction: ``health`` reports whether the
    provider can serve a request at all, and ``collect`` must return a bundle
    describing its own state rather than raising when it is simply unavailable.
    """

    key: str

    @abstractmethod
    async def health(self) -> bool:
        """Return True when the provider can serve requests right now."""

    @abstractmethod
    async def collect(self, request: EvidenceRequest) -> EvidenceBundle:
        """Collect evidence, reporting provider state instead of failing hard."""
