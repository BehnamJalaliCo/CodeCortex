"""Unified evidence model, provider contract, and fusion policy."""

from codecortex.evidence.contracts import EvidenceProvider
from codecortex.evidence.fusion import (
    STALE_PENALTY,
    TRUST_WEIGHTS,
    EvidenceFusionPolicy,
    FusionDecision,
)
from codecortex.evidence.models import (
    EvidenceBundle,
    EvidenceKind,
    EvidenceRecord,
    EvidenceRequest,
    ProviderReport,
    ProviderState,
    TrustTier,
)

__all__ = [
    "STALE_PENALTY",
    "TRUST_WEIGHTS",
    "EvidenceBundle",
    "EvidenceFusionPolicy",
    "EvidenceKind",
    "EvidenceProvider",
    "EvidenceRecord",
    "EvidenceRequest",
    "FusionDecision",
    "ProviderReport",
    "ProviderState",
    "TrustTier",
]
