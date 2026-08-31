from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.indexing.impact import ImpactAnalyzer


def test_impact_analysis_walks_reverse_dependencies():
    graph = ProjectGraph(
        nodes=[
            GraphNode(id="a", kind="function", name="token"),
            GraphNode(id="b", kind="function", name="login"),
            GraphNode(id="c", kind="function", name="checkout"),
            GraphNode(id="t", kind="function", name="test_checkout", path="tests/test_pay.py"),
        ],
        edges=[
            GraphEdge(source="b", target="a", kind="calls"),
            GraphEdge(source="c", target="b", kind="calls"),
            GraphEdge(source="t", target="c", kind="calls"),
        ],
    )
    report = ImpactAnalyzer(graph).analyze("token")
    assert [item.node.name for item in report.direct] == ["login"]
    assert {item.node.name for item in report.indirect} == {"checkout", "test_checkout"}
    assert {item.node.name for item in report.affected_tests} == {"test_checkout"}
    assert report.risk_score > 0
