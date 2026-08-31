from codecortex.architecture import ArchitectureDriftDetector
from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph


def test_drift_detector_flags_new_dependency_direction() -> None:
    detector = ArchitectureDriftDetector()
    baseline_graph = ProjectGraph(
        nodes=[
            GraphNode(id="a", kind="function", name="a", path="src/domain/a.py"),
            GraphNode(id="b", kind="function", name="b", path="src/application/b.py"),
        ],
        edges=[GraphEdge(source="b", target="a", kind="calls")],
    )
    current_graph = ProjectGraph(
        nodes=baseline_graph.nodes
        + [GraphNode(id="i", kind="function", name="i", path="src/infrastructure/db.py")],
        edges=baseline_graph.edges + [GraphEdge(source="a", target="i", kind="calls")],
    )
    report = detector.compare(
        detector.fingerprint(baseline_graph),
        detector.fingerprint(current_graph),
    )
    assert report.drifted is True
    assert any(item.kind == "new-dependency-direction" for item in report.findings)
    assert report.score > 0
