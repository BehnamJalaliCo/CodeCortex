"""Expose structural matches as ranked evidence."""

from __future__ import annotations

import asyncio
from pathlib import Path

from codecortex.config import CortexConfig
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
from codecortex.structural.models import StructuralError, StructuralMatch
from codecortex.structural.search import StructuralSearch

PROVIDER_KEY = "structural"
PROVENANCE = "structural-match"

#: A structural match is a parsed-syntax fact about the current worktree: it is
#: stronger than a name match but does not resolve which declaration is meant.
STRUCTURAL_CONFIDENCE = 0.8

#: Request metadata keys used to pass a structural query through the router.
PATTERN_METADATA_KEY = "structural_pattern"
LANGUAGE_METADATA_KEY = "structural_language"


class StructuralEvidenceProvider(EvidenceProvider):
    """Serve syntax-aware matches for pattern-shaped questions."""

    key = PROVIDER_KEY

    def __init__(
        self,
        root: Path,
        config: CortexConfig | None = None,
        search: StructuralSearch | None = None,
    ) -> None:
        self.root = root.resolve()
        self.config = config or CortexConfig.load(self.root)
        self.search = search or StructuralSearch(self.root, self.config)

    async def health(self) -> bool:
        status = await asyncio.to_thread(self.search.status)
        return status.available

    @staticmethod
    def record(match: StructuralMatch) -> EvidenceRecord:
        return EvidenceRecord(
            kind=EvidenceKind.STRUCTURAL_MATCH,
            provider=PROVIDER_KEY,
            provenance=PROVENANCE,
            trust=TrustTier.STRUCTURAL,
            path=match.path,
            start_line=match.start_line,
            start_column=match.start_column,
            end_line=match.end_line,
            end_column=match.end_column,
            content=match.matched_text,
            confidence=STRUCTURAL_CONFIDENCE,
            metadata={
                "captures": match.captures,
                "language": match.language,
                "rule_id": match.rule_id,
            },
        )

    async def collect(self, request: EvidenceRequest) -> EvidenceBundle:
        pattern = str(request.metadata.get(PATTERN_METADATA_KEY, "") or "")
        language = str(
            request.metadata.get(LANGUAGE_METADATA_KEY, "") or request.language or ""
        )
        if not pattern or not language:
            return EvidenceBundle(
                records=[],
                providers=[
                    ProviderReport(
                        provider=self.key,
                        state=ProviderState.NOT_CONFIGURED,
                        detail="a structural pattern and language are required",
                        fallback="lexical and symbol search",
                    )
                ],
            )
        try:
            matches = await asyncio.to_thread(
                self.search.search, pattern, language, limit=request.limit
            )
        except StructuralError as exc:
            return EvidenceBundle(
                records=[],
                providers=[
                    ProviderReport(
                        provider=self.key,
                        state=ProviderState.UNAVAILABLE,
                        detail=str(exc),
                        fallback="lexical and symbol search",
                    )
                ],
            )
        return EvidenceBundle(
            records=[self.record(match) for match in matches],
            providers=[ProviderReport(provider=self.key, state=ProviderState.AVAILABLE)],
        )
