from __future__ import annotations

import pytest

from codecortex.core.models import AgentRequest, RequestKind
from codecortex.evidence import (
    STALE_PENALTY,
    TRUST_WEIGHTS,
    EvidenceBundle,
    EvidenceFusionPolicy,
    EvidenceKind,
    EvidenceRecord,
    ProviderReport,
    ProviderState,
    TrustTier,
)
from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.precision import PrecisionGraphFusion, import_index
from codecortex.router import AdaptiveRouter, EvidenceLayer, plan_evidence
from tests.fixtures.precision_index import (
    DEFINITION,
    Document,
    IndexBuilder,
    Occurrence,
    symbol,
)


def _record(
    trust: TrustTier,
    *,
    provider: str = "p",
    line: int = 10,
    confidence: float = 0.9,
    stale: bool = False,
    kind: EvidenceKind = EvidenceKind.REFERENCE,
) -> EvidenceRecord:
    return EvidenceRecord(
        kind=kind,
        provider=provider,
        provenance=f"{provider}-provenance",
        trust=trust,
        path="src/app.py",
        start_line=line,
        start_column=1,
        symbol="Service",
        content=f"{provider} says line {line}",
        confidence=confidence,
        exact=trust is TrustTier.EXACT and not stale,
        stale=stale,
    )


# -- model ------------------------------------------------------------------


def test_evidence_ids_are_deterministic_and_content_addressed() -> None:
    first = _record(TrustTier.STRUCTURAL)
    second = _record(TrustTier.STRUCTURAL)
    assert first.evidence_id == second.evidence_id
    assert _record(TrustTier.STRUCTURAL, line=11).evidence_id != first.evidence_id
    assert len(first.evidence_id) == 32


def test_exact_evidence_must_declare_the_exact_trust_tier() -> None:
    with pytest.raises(ValueError, match="exact trust tier"):
        EvidenceRecord(
            kind=EvidenceKind.DEFINITION,
            provider="p",
            provenance="q",
            trust=TrustTier.INFERRED,
            exact=True,
        )


def test_confidence_is_bounded_and_location_renders() -> None:
    with pytest.raises(ValueError):
        EvidenceRecord(kind=EvidenceKind.CALL, provider="p", provenance="q", confidence=1.5)
    assert _record(TrustTier.EXACT).location == "src/app.py:10:1"
    assert EvidenceRecord(kind=EvidenceKind.MEMORY, provider="p", provenance="q").location == ""
    partial = EvidenceRecord(
        kind=EvidenceKind.MEMORY, provider="p", provenance="q", path="a.py", start_line=3
    )
    assert partial.location == "a.py:3"
    only_path = EvidenceRecord(
        kind=EvidenceKind.MEMORY, provider="p", provenance="q", path="a.py"
    )
    assert only_path.location == "a.py"


# -- ranking policy ---------------------------------------------------------


def test_trust_tiers_rank_in_the_documented_order() -> None:
    tiers = [
        TrustTier.EXACT,
        TrustTier.NEAR_EXACT,
        TrustTier.STRUCTURAL,
        TrustTier.INFERRED_HIGH,
        TrustTier.INFERRED,
        TrustTier.WEAK,
    ]
    scores = [EvidenceFusionPolicy.score(_record(tier, confidence=0.9)) for tier in tiers]
    assert scores == sorted(scores, reverse=True)
    assert TRUST_WEIGHTS[TrustTier.EXACT] == 1.0


def test_stale_exact_evidence_never_outranks_fresh_structural_evidence() -> None:
    stale_exact = _record(TrustTier.EXACT, stale=True, confidence=1.0)
    fresh_structural = _record(TrustTier.STRUCTURAL, provider="q", confidence=0.8)
    assert EvidenceFusionPolicy.score(stale_exact) < EvidenceFusionPolicy.score(
        fresh_structural
    )
    assert STALE_PENALTY < 1.0


def test_deduplication_keeps_the_strongest_and_records_what_it_superseded() -> None:
    exact = _record(TrustTier.EXACT, provider="precision", confidence=1.0)
    heuristic = _record(TrustTier.INFERRED, provider="graph", confidence=0.6)
    merged = EvidenceFusionPolicy.deduplicate([heuristic, exact])
    assert len(merged) == 1
    assert merged[0].provider == "precision"
    superseded = merged[0].metadata["superseded"]
    assert superseded == [
        {
            "provider": "graph",
            "provenance": "graph-provenance",
            "trust": "inferred",
            "confidence": 0.6,
        }
    ]


def test_conflicts_expose_disagreeing_providers() -> None:
    records = [
        _record(TrustTier.EXACT, provider="precision", confidence=1.0),
        _record(TrustTier.INFERRED, provider="graph", confidence=0.6),
        _record(TrustTier.STRUCTURAL, provider="ast", line=40),
    ]
    conflicts = EvidenceFusionPolicy.conflicts(records)
    assert len(conflicts) == 1
    assert conflicts[0].kept.provider == "precision"
    assert [item.provider for item in conflicts[0].superseded] == ["graph"]


def test_evidence_converts_to_context_chunks_with_provenance() -> None:
    chunks = EvidenceFusionPolicy.to_chunks([_record(TrustTier.EXACT, confidence=1.0)])
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.source == "evidence:p"
    assert chunk.metadata["trust"] == "exact"
    assert chunk.metadata["exact"] is True
    assert chunk.metadata["path"] == "src/app.py"
    assert "src/app.py:10:1" in chunk.content

    bare = EvidenceFusionPolicy.to_chunks(
        [
            EvidenceRecord(
                kind=EvidenceKind.MEMORY, provider="m", provenance="mem", content=""
            )
        ]
    )
    assert bare[0].content == "[inferred] memory"


def test_bundles_merge_and_report_degradation() -> None:
    available = EvidenceBundle(
        records=[_record(TrustTier.EXACT, confidence=1.0)],
        providers=[ProviderReport(provider="precision", state=ProviderState.AVAILABLE)],
    )
    offline = EvidenceBundle(
        records=[_record(TrustTier.STRUCTURAL, provider="docs", line=99)],
        providers=[ProviderReport(provider="docs", state=ProviderState.OFFLINE)],
    )
    merged = EvidenceFusionPolicy.merge_bundles([available, offline])
    assert len(merged.records) == 2
    assert merged.degraded
    assert len(merged.exact) == 1
    assert not available.degraded
    assert merged.report_for("docs") is not None
    assert merged.report_for("absent") is None
    assert ProviderReport(provider="p", state=ProviderState.STALE).usable


# -- router planning --------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Where is AuthService defined?", {EvidenceLayer.PRECISION}),
        ("Who calls refresh_token?", {EvidenceLayer.PRECISION}),
        ("What changed in this file?", set()),
        (
            "Is this method deprecated in our installed version?",
            {EvidenceLayer.DEPENDENCY_DOCS},
        ),
        (
            "How should we migrate to the current router API?",
            {EvidenceLayer.DEPENDENCY_DOCS},
        ),
        ("Find all usages of this old API shape.", {EvidenceLayer.STRUCTURAL}),
    ],
)
def test_router_plans_only_the_layers_a_question_needs(
    query: str, expected: set[EvidenceLayer]
) -> None:
    request = AgentRequest(query=query)
    plan = plan_evidence(request, RequestKind.UNKNOWN)
    assert expected <= set(plan.layers)
    if EvidenceLayer.DEPENDENCY_DOCS not in expected:
        assert EvidenceLayer.DEPENDENCY_DOCS not in plan.layers


def test_migration_requests_plan_every_layer() -> None:
    request = AgentRequest(
        query="Migrate all old library API calls to the supported shape everywhere",
        kind=RequestKind.REFACTOR,
    )
    plan = plan_evidence(request, RequestKind.REFACTOR)
    assert set(plan.layers) == {
        EvidenceLayer.PRECISION,
        EvidenceLayer.DEPENDENCY_DOCS,
        EvidenceLayer.STRUCTURAL,
    }
    assert len(plan.reasons) == len(plan.layers)
    assert plan.wants(EvidenceLayer.STRUCTURAL)
    assert plan.to_dict()["layers"] == [item.value for item in plan.layers]


def test_router_attaches_the_evidence_plan_to_the_route() -> None:
    plan = AdaptiveRouter().route(AgentRequest(query="Who calls refresh_token?"))
    assert "precision" in plan.evidence_layers
    assert plan.evidence_reasons
    assert "dependency_docs" not in plan.evidence_layers

    metadata_driven = AdaptiveRouter().route(
        AgentRequest(
            query="update this call",
            metadata={"path": "src/a.py", "line": 3, "library": "next"},
        )
    )
    assert {"precision", "dependency_docs"} <= set(metadata_driven.evidence_layers)


def test_route_plan_evidence_fields_default_to_empty() -> None:
    plan = AdaptiveRouter().route(AgentRequest(query="explain the architecture"))
    assert plan.evidence_layers == []
    assert plan.model_dump(mode="json")["evidence_reasons"] == []


# -- graph fusion -----------------------------------------------------------

SERVICE = symbol("app", "auth/`Service`#")


def _graph() -> ProjectGraph:
    return ProjectGraph(
        nodes=[
            GraphNode(id="file:src/auth.py", kind="file", name="auth.py", path="src/auth.py"),
            GraphNode(
                id="symbol:src/auth.py:3:class:Service",
                kind="class",
                name="Service",
                path="src/auth.py",
                line=3,
                metadata={"end_line": 8},
            ),
            GraphNode(id="file:src/api.py", kind="file", name="api.py", path="src/api.py"),
            GraphNode(
                id="symbol:src/api.py:2:function:handle",
                kind="function",
                name="handle",
                path="src/api.py",
                line=2,
                metadata={"end_line": 5},
            ),
        ],
        edges=[
            GraphEdge(
                source="symbol:src/api.py:2:function:handle",
                target="symbol:src/auth.py:3:class:Service",
                kind="calls",
                metadata={"resolution_confidence": 0.58, "ambiguity": 0.4},
            )
        ],
    )


def _index() -> bytes:
    return (
        IndexBuilder()
        .add(
            Document(
                relative_path="src/auth.py",
                occurrences=(Occurrence(SERVICE, 2, 6, 13, roles=DEFINITION),),
            )
        )
        .add(
            Document(
                relative_path="src/api.py",
                occurrences=(Occurrence(SERVICE, 3, 11, 18),),
            )
        )
        .encode()
    )


def test_graph_fusion_adds_exact_edges_and_supersedes_weaker_ones() -> None:
    graph = _graph()
    report = PrecisionGraphFusion().apply(graph, import_index(_index()))

    assert report.exact_edges == 1
    assert report.superseded_edges == 1
    assert report.conflicts
    assert not report.stale

    exact = next(edge for edge in graph.edges if edge.kind == "references")
    assert exact.source == "symbol:src/api.py:2:function:handle"
    assert exact.target == "symbol:src/auth.py:3:class:Service"
    assert exact.metadata["resolution"] == "exact"
    assert exact.metadata["provenance"] == "precision-index"
    assert exact.metadata["confidence"] == 1.0

    weaker = next(edge for edge in graph.edges if edge.kind == "calls")
    assert weaker.metadata["superseded_by"] == "exact"
    assert weaker.metadata["previous_resolution"] == "inferred"
    assert weaker.metadata["resolution_confidence"] == 0.58
    assert report.to_dict()["exact_edges"] == 1


def test_graph_fusion_marks_stale_indexes_and_is_idempotent() -> None:
    graph = _graph()
    fusion = PrecisionGraphFusion(stale=True)
    first = fusion.apply(graph, import_index(_index()))
    assert first.stale
    edge = next(item for item in graph.edges if item.kind == "references")
    assert edge.metadata["resolution"] == "stale_exact"
    assert edge.metadata["confidence"] == 0.55

    second = fusion.apply(graph, import_index(_index()))
    assert second.exact_edges == 0
    assert len([item for item in graph.edges if item.kind == "references"]) == 1


def test_graph_fusion_counts_occurrences_it_cannot_place() -> None:
    graph = ProjectGraph(
        nodes=[GraphNode(id="file:src/api.py", kind="file", name="api.py", path="src/api.py")]
    )
    report = PrecisionGraphFusion().apply(graph, import_index(_index()))
    assert report.exact_edges == 0
    assert report.unresolved_occurrences == 1


def test_impact_analysis_weighs_exact_edges_above_inferred_ones() -> None:
    graph = _graph()
    inferred = ImpactAnalyzer(graph).analyze("Service")
    assert inferred.direct[0].evidence == "inferred"
    assert not inferred.direct[0].exact

    PrecisionGraphFusion().apply(graph, import_index(_index()))
    fused = ImpactAnalyzer(graph).analyze("Service")
    assert fused.direct[0].exact
    assert fused.direct[0].risk > inferred.direct[0].risk
    assert fused.evidence_quality()["exact"] == 1
    assert len(fused.exact_items) == 1
    assert "evidence=exact" in fused.to_text()


def test_impact_analysis_marks_unresolved_and_stale_edges() -> None:
    graph = ProjectGraph(
        nodes=[
            GraphNode(id="a", kind="function", name="target"),
            GraphNode(id="b", kind="function", name="caller"),
            GraphNode(id="c", kind="function", name="ghost"),
        ],
        edges=[
            GraphEdge(
                source="b", target="a", kind="calls", metadata={"resolution_confidence": 0.0}
            ),
            GraphEdge(
                source="c", target="a", kind="references", metadata={"resolution": "stale_exact"}
            ),
        ],
    )
    report = ImpactAnalyzer(graph).analyze("target")
    by_name = {item.node.name: item for item in report.direct}
    assert by_name["caller"].evidence == "unresolved"
    assert by_name["ghost"].stale and not by_name["ghost"].exact
    assert report.evidence_quality() == {"unresolved": 1, "stale_exact": 1}


def test_impact_text_reports_no_evidence_for_an_isolated_node() -> None:
    graph = ProjectGraph(nodes=[GraphNode(id="a", kind="function", name="lonely")])
    assert "Evidence: none" in ImpactAnalyzer(graph).analyze("lonely").to_text()
