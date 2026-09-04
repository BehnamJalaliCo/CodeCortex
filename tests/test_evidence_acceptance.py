"""End-to-end acceptance scenarios for the evidence layers.

These check the behaviour a user actually depends on when things are *not*
ideal: an index that has gone stale, a documentation provider that is offline,
a structural engine that is not installed. The requirement in every case is
the same — answer from whatever is healthy, and never present a degraded
answer as an undegraded one.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from codecortex.config import (
    CortexConfig,
    DependencyDocsConfig,
    PrecisionIndexConfig,
    StructuralConfig,
)
from codecortex.dependencies.service import DependencyIntelligence
from codecortex.evidence.fusion import EvidenceFusionPolicy
from codecortex.evidence.models import (
    EvidenceKind,
    EvidenceRequest,
    ProviderState,
    TrustTier,
)
from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.precision.merge import PrecisionGraphFusion
from codecortex.precision.provider import PrecisionEvidenceProvider
from codecortex.structural.provider import StructuralEvidenceProvider
from tests.fixtures.precision_index import (
    DEFINITION,
    Document,
    IndexBuilder,
    Occurrence,
    SymbolInfo,
    symbol,
)

SERVICE = symbol("app", "service/`handler`().")
CALLER = symbol("app", "main/`run`().")


def _project(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "service.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    (root / "src" / "main.py").write_text(
        "from service import handler\n\n\ndef run():\n    return handler()\n", encoding="utf-8"
    )
    return root


def _index() -> bytes:
    return (
        IndexBuilder()
        .add(
            Document(
                relative_path="src/service.py",
                occurrences=(Occurrence(SERVICE, 0, 4, 11, roles=DEFINITION),),
                symbols=(SymbolInfo(SERVICE, display_name="handler"),),
            )
        )
        .add(
            Document(
                relative_path="src/main.py",
                occurrences=(
                    Occurrence(CALLER, 3, 4, 7, roles=DEFINITION),
                    Occurrence(SERVICE, 4, 11, 18),
                ),
                symbols=(SymbolInfo(CALLER, display_name="run"),),
            )
        )
        .encode()
    )


def _fresh_index(root: Path) -> Path:
    path = root / "index.scip"
    path.write_bytes(_index())
    later = time.time() + 600
    os.utime(path, (later, later))
    return path


# -- Scenario E: every optional provider degraded ---------------------------


@pytest.mark.asyncio
async def test_a_stale_index_still_answers_but_never_claims_exactness(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "stale")
    _fresh_index(root)
    provider = PrecisionEvidenceProvider(root, CortexConfig(project_root=root))

    fresh = provider.evidence_for_symbol(SERVICE, EvidenceKind.DEFINITION)
    assert fresh.records and fresh.records[0].exact

    # Edit a source file after indexing.
    later = time.time() + 1200
    os.utime(root / "src" / "service.py", (later, later))
    provider.store.invalidate()

    degraded = provider.evidence_for_symbol(SERVICE, EvidenceKind.DEFINITION)
    assert degraded.records, "stale evidence is still useful and must not vanish"
    record = degraded.records[0]
    assert record.stale and not record.exact
    assert record.trust is not TrustTier.EXACT
    report = degraded.report_for("precision_index")
    assert report is not None and report.state is ProviderState.STALE
    assert "ranked below fresh structural evidence" in (report.fallback or "")


@pytest.mark.asyncio
async def test_an_offline_documentation_provider_leaves_local_facts_intact(
    tmp_path: Path,
) -> None:
    root = tmp_path / "offline"
    root.mkdir()
    (root / "package.json").write_text(
        json.dumps({"dependencies": {"next": "15.1.8"}}), encoding="utf-8"
    )
    (root / "package-lock.json").write_text(
        json.dumps(
            {"lockfileVersion": 3, "packages": {"node_modules/next": {"version": "15.1.8"}}}
        ),
        encoding="utf-8",
    )
    config = CortexConfig(
        project_root=root,
        # A port nothing is listening on: the provider is enabled but offline.
        dependency_docs=DependencyDocsConfig(
            enabled=True,
            base_url="http://127.0.0.1:9/api",
            max_retries=0,
            connect_timeout_seconds=1.0,
            read_timeout_seconds=1.0,
        ),
    )
    service = DependencyIntelligence(root, config)
    service._provider = None
    from codecortex.dependencies.remote import RemoteDocumentationProvider

    service._provider = RemoteDocumentationProvider(config.dependency_docs, "ctx7sk-test")

    result = await service.docs("next", "middleware")
    assert not result.available
    assert result.provider_state is ProviderState.OFFLINE
    # The local facts survive the outage and are the honest answer.
    assert result.dependency is not None
    assert result.dependency.resolved == "15.1.8"
    assert result.report().fallback == (
        "local manifest versions only; no documentation was retrieved"
    )


@pytest.mark.asyncio
async def test_an_unavailable_structural_engine_reports_itself(tmp_path: Path) -> None:
    root = _project(tmp_path / "nostructural")
    config = CortexConfig(
        project_root=root,
        structural=StructuralConfig(command="codecortex-no-such-engine"),
    )
    provider = StructuralEvidenceProvider(root, config)
    bundle = await provider.collect(
        EvidenceRequest(query="find old_api($X)", language="python")
    )
    assert bundle.records == []
    report = bundle.report_for(provider.key)
    assert report is not None
    assert report.state in {ProviderState.UNAVAILABLE, ProviderState.NOT_CONFIGURED}
    assert report.fallback


@pytest.mark.asyncio
async def test_all_three_providers_degraded_still_answers_and_says_so(
    tmp_path: Path,
) -> None:
    """Scenario E: nothing optional is healthy, and nothing pretends otherwise."""
    root = _project(tmp_path / "degraded")
    _fresh_index(root)
    later = time.time() + 1200
    os.utime(root / "src" / "service.py", (later, later))

    config = CortexConfig(
        project_root=root,
        precision_index=PrecisionIndexConfig(),
        dependency_docs=DependencyDocsConfig(enabled=False),
        structural=StructuralConfig(command="codecortex-no-such-engine"),
    )
    precision = PrecisionEvidenceProvider(root, config)
    structural = StructuralEvidenceProvider(root, config)

    precision_bundle = precision.evidence_for_symbol(SERVICE, EvidenceKind.REFERENCE)
    structural_bundle = await structural.collect(
        EvidenceRequest(query="handler($X)", language="python")
    )
    merged = EvidenceFusionPolicy.merge_bundles([precision_bundle, structural_bundle])

    # An answer is still produced, from the one degraded-but-usable source.
    assert merged.records
    assert merged.degraded, "a degraded bundle must announce itself"
    # And no record in it claims exactness.
    assert merged.exact == []
    assert all(not item.exact for item in merged.records)
    states = {report.provider: report.state for report in merged.providers}
    assert ProviderState.STALE in states.values()
    assert any(
        state in {ProviderState.UNAVAILABLE, ProviderState.NOT_CONFIGURED}
        for state in states.values()
    )


# -- Phase 6: mixed-evidence impact -----------------------------------------


def _mixed_graph() -> ProjectGraph:
    """A graph carrying an exact edge, a heuristic edge, and a test edge."""
    nodes = [
        GraphNode(id="sym:handler", kind="function", name="handler", path="src/service.py", line=1),
        GraphNode(id="sym:run", kind="function", name="run", path="src/main.py", line=4),
        GraphNode(id="sym:guess", kind="function", name="guess", path="src/other.py", line=2),
        GraphNode(
            id="sym:test_handler",
            kind="function",
            name="test_handler",
            path="tests/test_service.py",
            line=3,
        ),
        GraphNode(id="file:src/main.py", kind="file", name="main.py", path="src/main.py"),
    ]
    edges = [
        GraphEdge(
            source="sym:run",
            target="sym:handler",
            kind="references",
            metadata={"resolution": "exact", "provenance": "precision-index"},
        ),
        GraphEdge(
            source="sym:guess",
            target="sym:handler",
            kind="calls",
            metadata={"resolution": "inferred", "provenance": "cross-file-heuristic"},
        ),
        GraphEdge(
            source="sym:test_handler",
            target="sym:handler",
            kind="calls",
            metadata={"provenance": "cross-file-heuristic"},
        ),
    ]
    return ProjectGraph(nodes=nodes, edges=edges)


def test_exact_edges_lead_impact_without_erasing_weaker_ones() -> None:
    report = ImpactAnalyzer(_mixed_graph()).analyze("handler")
    reached = {item.node.id: item for item in (*report.direct, *report.indirect)}

    assert "sym:run" in reached and reached["sym:run"].exact
    # The heuristic dependent is still reported, at a lower resolution.
    assert "sym:guess" in reached and not reached["sym:guess"].exact
    assert reached["sym:run"].risk > reached["sym:guess"].risk

    quality = report.evidence_quality()
    assert quality.get("exact", 0) >= 1
    assert sum(quality.values()) == len(reached)
    # Affected tests stay visible whatever resolved them.
    assert {item.node.name for item in report.affected_tests} == {"test_handler"}


def test_a_stale_exact_edge_is_downgraded_but_still_counted() -> None:
    graph = _mixed_graph()
    graph.edges[0] = GraphEdge(
        source="sym:run",
        target="sym:handler",
        kind="references",
        metadata={"resolution": "stale_exact", "provenance": "precision-index"},
    )
    report = ImpactAnalyzer(graph).analyze("handler")
    item = next(entry for entry in report.direct if entry.node.id == "sym:run")
    assert item.stale
    assert item.evidence == "stale_exact"
    assert "stale_exact" in report.evidence_quality()

    fresh = ImpactAnalyzer(_mixed_graph()).analyze("handler")
    fresh_item = next(entry for entry in fresh.direct if entry.node.id == "sym:run")
    assert item.risk < fresh_item.risk


def test_precision_fusion_upgrades_the_graph_impact_reads(tmp_path: Path) -> None:
    """The exact edge that impact consumes is the one graph fusion writes."""
    from codecortex.precision.importer import import_index

    graph = ProjectGraph(
        nodes=[
            GraphNode(
                id="sym:handler",
                kind="function",
                name="handler",
                path="src/service.py",
                line=1,
            ),
            GraphNode(
                id="sym:run",
                kind="function",
                name="run",
                path="src/main.py",
                line=4,
                metadata={"end_line": 5},
            ),
        ],
        edges=[
            GraphEdge(
                source="sym:run",
                target="sym:handler",
                kind="calls",
                metadata={"provenance": "cross-file-heuristic"},
            )
        ],
    )
    fusion = PrecisionGraphFusion().apply(graph, import_index(_index()))
    assert fusion.exact_edges >= 1
    assert fusion.superseded_edges >= 1

    report = ImpactAnalyzer(graph).analyze("handler")
    assert any(item.exact for item in report.direct)
    # The superseded heuristic edge keeps its history rather than disappearing.
    weaker = next(
        edge for edge in graph.edges if edge.kind == "calls" and edge.source == "sym:run"
    )
    assert weaker.metadata["superseded_by"] == "exact"
    assert weaker.metadata["previous_provenance"] == "cross-file-heuristic"
