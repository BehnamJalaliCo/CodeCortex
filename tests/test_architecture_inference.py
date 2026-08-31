from codecortex.architecture import ArchitectureInferenceEngine
from codecortex.indexing.graph import GraphNode, ProjectGraph


def test_architecture_inference_uses_multiple_independent_signals() -> None:
    graph = ProjectGraph(
        nodes=[
            GraphNode(id="1", kind="file", name="auth.py", path="src/controllers/auth.py"),
            GraphNode(id="2", kind="file", name="auth.py", path="src/services/auth.py"),
            GraphNode(id="3", kind="file", name="user.py", path="src/repositories/user.py"),
            GraphNode(id="4", kind="file", name="user.py", path="src/models/user.py"),
        ]
    )
    report = ArchitectureInferenceEngine().analyze(graph)
    assert report.primary is not None
    assert report.primary.name in {"layered", "service-repository"}
    assert report.primary.confidence >= 0.5
    assert len(report.primary.evidence) >= 3
