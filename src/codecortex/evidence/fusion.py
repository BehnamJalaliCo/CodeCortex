"""Central evidence ranking, deduplication, and context conversion policy.

Every intelligence layer routes its findings through this module so that a
single, documented policy decides what outranks what. The policy keeps two
signals side by side:

* a **categorical trust tier** that is exposed to agents verbatim, and
* a **numeric ranking score** used only for ordering and budget selection.

The numeric score is a ranking device, not a calibrated probability. It is
derived from the tier weight and the provider's own confidence, and is reduced
when evidence is known to be stale.
"""

from __future__ import annotations

from dataclasses import dataclass

from codecortex.core.models import ContextChunk
from codecortex.evidence.models import EvidenceBundle, EvidenceRecord, TrustTier

#: Ranking weight per trust tier. Higher means "prefer this evidence".
TRUST_WEIGHTS: dict[TrustTier, float] = {
    TrustTier.EXACT: 1.00,
    TrustTier.NEAR_EXACT: 0.88,
    TrustTier.STRUCTURAL: 0.72,
    TrustTier.INFERRED_HIGH: 0.58,
    TrustTier.INFERRED: 0.42,
    TrustTier.WEAK: 0.20,
}

#: Floor of the confidence factor in :meth:`EvidenceFusionPolicy.score`. A
#: record with zero confidence still scores this fraction of its tier weight,
#: because the tier itself carries information.
MIN_CONFIDENCE_FACTOR = 0.35

#: Smallest score any fresh structural record can reach: its tier weight at
#: zero confidence.
_WEAKEST_FRESH_STRUCTURAL = TRUST_WEIGHTS[TrustTier.STRUCTURAL] * MIN_CONFIDENCE_FACTOR

#: Multiplier applied to stale evidence.
#:
#: Derived, not chosen. The policy guarantees that stale exact evidence never
#: outranks fresh structural evidence, and that guarantee has to hold at every
#: confidence pairing - including the worst one, where the stale record is
#: fully confident and the fresh one is not confident at all. Since a fresh
#: score never exceeds 1.0, scaling stale scores by a factor strictly below the
#: weakest possible fresh structural score makes the property true by
#: construction rather than by arithmetic that happens to work out.
#:
#: A flat multiplier picked by eye does not do this: at 0.55, a stale exact
#: record at confidence 0.25 scored 0.282 against a fresh structural record's
#: 0.252, and led the ranking.
#:
#: Scaling rather than clamping keeps stale records ordered among themselves,
#: so a stale exact result still outranks a stale guess.
STALE_PENALTY = round(_WEAKEST_FRESH_STRUCTURAL * 0.99, 6)


@dataclass(frozen=True, slots=True)
class FusionDecision:
    """Why one record was kept and which weaker records it superseded."""

    kept: EvidenceRecord
    superseded: tuple[EvidenceRecord, ...]


class EvidenceFusionPolicy:
    """Rank, deduplicate, and budget evidence from heterogeneous providers."""

    @staticmethod
    def score(record: EvidenceRecord) -> float:
        weight = TRUST_WEIGHTS.get(record.trust, TRUST_WEIGHTS[TrustTier.WEAK])
        score = weight * (
            MIN_CONFIDENCE_FACTOR + (1.0 - MIN_CONFIDENCE_FACTOR) * record.confidence
        )
        if record.stale:
            score *= STALE_PENALTY
        return round(min(1.0, max(0.0, score)), 6)

    @staticmethod
    def _identity(record: EvidenceRecord) -> tuple[str, ...]:
        """Location identity used to detect that two providers found the same thing."""
        return (
            record.kind.value,
            record.path or "",
            str(record.start_line),
            str(record.start_column),
            record.symbol or record.target_symbol or "",
        )

    @classmethod
    def rank(cls, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        """Return records ordered strongest-first with a deterministic tiebreak."""
        return sorted(
            records,
            key=lambda record: (
                -cls.score(record),
                record.trust.value,
                record.path or "",
                record.start_line if record.start_line is not None else 0,
                record.start_column if record.start_column is not None else 0,
                record.evidence_id,
            ),
        )

    @classmethod
    def fuse(cls, records: list[EvidenceRecord]) -> list[FusionDecision]:
        """Collapse duplicate observations, keeping the strongest and recording the rest."""
        decisions: dict[tuple[str, ...], FusionDecision] = {}
        for record in cls.rank(records):
            identity = cls._identity(record)
            existing = decisions.get(identity)
            if existing is None:
                decisions[identity] = FusionDecision(kept=record, superseded=())
                continue
            decisions[identity] = FusionDecision(
                kept=existing.kept,
                superseded=(*existing.superseded, record),
            )
        return list(decisions.values())

    @classmethod
    def deduplicate(cls, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        """Return the strongest record per location, annotated with what it superseded.

        The weaker record is never silently erased: its provider and trust tier
        are retained in ``metadata['superseded']`` so conflicts stay visible for
        debugging and diagnostics.
        """
        merged: list[EvidenceRecord] = []
        for decision in cls.fuse(records):
            record = decision.kept
            if decision.superseded:
                metadata = dict(record.metadata)
                metadata["superseded"] = [
                    {
                        "provider": item.provider,
                        "provenance": item.provenance,
                        "trust": item.trust.value,
                        "confidence": item.confidence,
                    }
                    for item in decision.superseded
                ]
                record = record.model_copy(update={"metadata": metadata})
            merged.append(record)
        return merged

    @classmethod
    def conflicts(cls, records: list[EvidenceRecord]) -> list[FusionDecision]:
        """Return only the fusion decisions where providers disagreed on trust."""
        return [
            decision
            for decision in cls.fuse(records)
            if any(item.trust is not decision.kept.trust for item in decision.superseded)
        ]

    @classmethod
    def to_chunks(cls, records: list[EvidenceRecord]) -> list[ContextChunk]:
        """Convert ranked evidence into context chunks that keep their provenance."""
        chunks: list[ContextChunk] = []
        for record in cls.deduplicate(records):
            body = record.content.strip()
            header = f"[{record.trust.value}] {record.kind.value}"
            if record.location:
                header = f"{header} {record.location}"
            if record.symbol:
                header = f"{header} — {record.symbol}"
            content = f"{header}\n{body}" if body else header
            chunks.append(
                ContextChunk(
                    source=f"evidence:{record.provider}",
                    content=content,
                    tokens=0,
                    relevance=cls.score(record),
                    metadata={
                        "path": record.path,
                        "evidence_id": record.evidence_id,
                        "evidence_kind": record.kind.value,
                        "trust": record.trust.value,
                        "provenance": record.provenance,
                        "exact": record.exact,
                        "stale": record.stale,
                    },
                )
            )
        return chunks

    @classmethod
    def merge_bundles(cls, bundles: list[EvidenceBundle]) -> EvidenceBundle:
        """Combine bundles from several providers into one ranked bundle."""
        records = [record for bundle in bundles for record in bundle.records]
        providers = [report for bundle in bundles for report in bundle.providers]
        return EvidenceBundle(records=cls.deduplicate(records), providers=providers)
