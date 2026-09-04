"""Ranking invariants the evidence model must hold for every input.

These are the properties the rest of the system is allowed to assume. Each is
checked exhaustively over the tier and flag space rather than at a handful of
sampled points, because a ranking bug shows up as a plausible-looking answer in
the wrong order, not as a crash.
"""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from codecortex.evidence.fusion import (
    MIN_CONFIDENCE_FACTOR,
    STALE_PENALTY,
    TRUST_WEIGHTS,
    EvidenceFusionPolicy,
)
from codecortex.evidence.models import (
    MAX_TRUST_BY_PROVENANCE,
    EvidenceBundle,
    EvidenceKind,
    EvidenceRecord,
    ProviderReport,
    ProviderState,
    TrustTier,
)

TIERS = tuple(TrustTier)
CONFIDENCES = (0.0, 0.25, 0.5, 0.75, 1.0)


def _record(
    *,
    trust: TrustTier = TrustTier.INFERRED,
    stale: bool = False,
    exact: bool = False,
    confidence: float = 0.5,
    provider: str = "test",
    provenance: str = "test-provenance",
    path: str = "a.py",
    line: int = 1,
    column: int = 1,
    kind: EvidenceKind = EvidenceKind.REFERENCE,
    symbol: str = "sym",
    content: str = "body",
) -> EvidenceRecord:
    return EvidenceRecord(
        kind=kind,
        provider=provider,
        provenance=provenance,
        trust=trust,
        path=path,
        start_line=line,
        start_column=column,
        symbol=symbol,
        content=content,
        confidence=confidence,
        exact=exact,
        stale=stale,
    )


# -- invariant 1: stale evidence is never exact -----------------------------


def test_exact_evidence_must_use_the_exact_tier() -> None:
    with pytest.raises(ValidationError, match="exact trust tier"):
        _record(trust=TrustTier.STRUCTURAL, exact=True)


def test_stale_evidence_cannot_be_exact() -> None:
    """Exactness is a claim about now; stale evidence cannot make it."""
    with pytest.raises(ValidationError, match="stale evidence cannot be exact"):
        _record(trust=TrustTier.EXACT, exact=True, stale=True)


def test_a_bundle_reports_no_exact_records_when_everything_is_stale() -> None:
    bundle = EvidenceBundle(
        records=[_record(trust=TrustTier.EXACT, stale=True), _record(stale=True)]
    )
    assert bundle.exact == []


# -- invariant 2: stale exact never outranks fresh structural ---------------


@pytest.mark.parametrize("stale_confidence", CONFIDENCES)
@pytest.mark.parametrize("fresh_confidence", CONFIDENCES)
def test_stale_exact_never_outranks_fresh_structural(
    stale_confidence: float, fresh_confidence: float
) -> None:
    """Holds at every confidence pairing, including the worst case.

    The strongest possible stale exact record must still lose to the weakest
    fresh structural one, or a stale answer leads the ranking.
    """
    stale_exact = _record(trust=TrustTier.EXACT, stale=True, confidence=stale_confidence)
    fresh_structural = _record(trust=TrustTier.STRUCTURAL, confidence=fresh_confidence)
    assert EvidenceFusionPolicy.score(stale_exact) < EvidenceFusionPolicy.score(
        fresh_structural
    )


def test_the_stale_penalty_is_derived_from_the_bound_it_must_satisfy() -> None:
    """State the bound directly, not just the pairings that happen to be sampled.

    A softened penalty would break the invariant above only at some confidence
    pairings, which is exactly the kind of regression a sampled test misses.
    """
    best_possible_stale = TRUST_WEIGHTS[TrustTier.EXACT] * 1.0 * STALE_PENALTY
    worst_fresh_structural = TRUST_WEIGHTS[TrustTier.STRUCTURAL] * MIN_CONFIDENCE_FACTOR
    assert best_possible_stale < worst_fresh_structural


def test_stale_records_remain_ordered_among_themselves() -> None:
    """The penalty scales, so a stale exact result still beats a stale guess."""
    strong = _record(trust=TrustTier.EXACT, stale=True, confidence=1.0)
    weak = _record(trust=TrustTier.WEAK, stale=True, confidence=1.0)
    less_confident = _record(trust=TrustTier.EXACT, stale=True, confidence=0.25)
    assert EvidenceFusionPolicy.score(strong) > EvidenceFusionPolicy.score(weak)
    assert EvidenceFusionPolicy.score(strong) > EvidenceFusionPolicy.score(less_confident)


@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize("confidence", CONFIDENCES)
def test_staleness_never_increases_a_score(tier: TrustTier, confidence: float) -> None:
    fresh = _record(trust=tier, confidence=confidence)
    stale = _record(trust=tier, confidence=confidence, stale=True)
    assert EvidenceFusionPolicy.score(stale) < EvidenceFusionPolicy.score(fresh)


@pytest.mark.parametrize(("stronger", "weaker"), list(itertools.pairwise(TIERS)))
def test_a_stronger_tier_outranks_a_weaker_one_at_equal_confidence(
    stronger: TrustTier, weaker: TrustTier
) -> None:
    for confidence in CONFIDENCES:
        assert EvidenceFusionPolicy.score(
            _record(trust=stronger, confidence=confidence)
        ) > EvidenceFusionPolicy.score(_record(trust=weaker, confidence=confidence))


@pytest.mark.parametrize("tier", TIERS)
def test_scores_stay_inside_the_unit_interval(tier: TrustTier) -> None:
    for confidence in CONFIDENCES:
        for stale in (False, True):
            score = EvidenceFusionPolicy.score(
                _record(trust=tier, confidence=confidence, stale=stale)
            )
            assert 0.0 <= score <= 1.0


def test_ranking_is_deterministic_regardless_of_input_order() -> None:
    records = [
        _record(trust=tier, confidence=confidence, path=f"{index}.py")
        for index, (tier, confidence) in enumerate(itertools.product(TIERS, CONFIDENCES))
    ]
    forward = [item.evidence_id for item in EvidenceFusionPolicy.rank(records)]
    backward = [item.evidence_id for item in EvidenceFusionPolicy.rank(list(reversed(records)))]
    assert forward == backward


# -- invariant 3: duplicates do not consume duplicate context ---------------


def test_the_same_location_from_two_providers_yields_one_chunk() -> None:
    exact = _record(
        trust=TrustTier.EXACT, exact=True, provider="precision", provenance="precision-index"
    )
    inferred = _record(trust=TrustTier.INFERRED, provider="heuristic")
    chunks = EvidenceFusionPolicy.to_chunks([exact, inferred])
    assert len(chunks) == 1
    assert chunks[0].metadata["trust"] == TrustTier.EXACT.value


def test_distinct_locations_are_not_collapsed() -> None:
    records = [_record(line=1), _record(line=2), _record(path="b.py")]
    assert len(EvidenceFusionPolicy.deduplicate(records)) == 3


def test_the_same_position_for_a_different_kind_is_not_a_duplicate() -> None:
    definition = _record(kind=EvidenceKind.DEFINITION)
    reference = _record(kind=EvidenceKind.REFERENCE)
    assert len(EvidenceFusionPolicy.deduplicate([definition, reference])) == 2


# -- invariant 4: superseded evidence stays debuggable ----------------------


def test_a_superseded_record_is_recorded_not_erased() -> None:
    exact = _record(
        trust=TrustTier.EXACT, exact=True, provider="precision", provenance="precision-index"
    )
    weaker = _record(trust=TrustTier.WEAK, provider="name-match", confidence=0.9)
    merged = EvidenceFusionPolicy.deduplicate([exact, weaker])
    assert len(merged) == 1
    superseded = merged[0].metadata["superseded"]
    assert [item["provider"] for item in superseded] == ["name-match"]
    assert superseded[0]["trust"] == TrustTier.WEAK.value
    assert superseded[0]["confidence"] == 0.9


def test_conflicts_report_only_genuine_disagreements() -> None:
    exact = _record(
        trust=TrustTier.EXACT, exact=True, provider="a", provenance="precision-index"
    )
    weaker = _record(trust=TrustTier.INFERRED, provider="b")
    same_tier = _record(trust=TrustTier.EXACT, exact=True, provider="c", provenance="precision-index")

    assert len(EvidenceFusionPolicy.conflicts([exact, weaker])) == 1
    assert EvidenceFusionPolicy.conflicts([exact, same_tier]) == []


# -- invariant 5: a failing provider does not erase healthy evidence --------


def test_one_provider_failing_leaves_the_others_intact() -> None:
    healthy = EvidenceBundle(
        records=[_record(trust=TrustTier.STRUCTURAL, provider="structural")],
        providers=[ProviderReport(provider="structural", state=ProviderState.AVAILABLE)],
    )
    broken = EvidenceBundle(
        records=[],
        providers=[
            ProviderReport(
                provider="docs", state=ProviderState.OFFLINE, fallback="local facts only"
            )
        ],
    )
    merged = EvidenceFusionPolicy.merge_bundles([healthy, broken])
    assert len(merged.records) == 1
    assert merged.degraded
    report = merged.report_for("docs")
    assert report is not None and report.fallback == "local facts only"


def test_a_degraded_bundle_says_so_even_when_it_has_records() -> None:
    bundle = EvidenceBundle(
        records=[_record()],
        providers=[
            ProviderReport(provider="a", state=ProviderState.AVAILABLE),
            ProviderReport(provider="b", state=ProviderState.STALE),
        ],
    )
    assert bundle.degraded


# -- invariant 6: no provider may elevate its own trust tier ----------------


@pytest.mark.parametrize(
    ("provenance", "ceiling"), sorted(MAX_TRUST_BY_PROVENANCE.items())
)
def test_a_known_provenance_cannot_claim_a_stronger_tier(
    provenance: str, ceiling: TrustTier
) -> None:
    """A tier is a claim about method, so the method sets the ceiling."""
    ranks = list(TIERS)
    stronger = ranks[: ranks.index(ceiling)]
    for tier in stronger:
        with pytest.raises(ValidationError, match="may not claim trust"):
            _record(
                trust=tier,
                provenance=provenance,
                exact=tier is TrustTier.EXACT,
            )
    # The ceiling itself, and everything weaker, is allowed.
    for tier in ranks[ranks.index(ceiling) :]:
        _record(trust=tier, provenance=provenance, exact=tier is TrustTier.EXACT)


def test_only_an_index_derived_result_may_claim_exact() -> None:
    exact_capable = {
        name for name, tier in MAX_TRUST_BY_PROVENANCE.items() if tier is TrustTier.EXACT
    }
    assert exact_capable == {"precision-index"}


def test_a_structural_match_cannot_call_itself_exact() -> None:
    with pytest.raises(ValidationError, match="may not claim trust"):
        _record(trust=TrustTier.EXACT, exact=True, provenance="structural-match")


def test_documentation_cannot_claim_to_resolve_a_repository_symbol_exactly() -> None:
    with pytest.raises(ValidationError, match="may not claim trust"):
        _record(trust=TrustTier.EXACT, exact=True, provenance="dependency-documentation")


def test_an_unlisted_provenance_is_unconstrained() -> None:
    """The ceiling guards known layers; it is not a registry of every caller."""
    record = _record(trust=TrustTier.EXACT, exact=True, provenance="some-new-layer")
    assert record.trust is TrustTier.EXACT
