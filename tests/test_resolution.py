from codecortex.indexing.graph import GraphNode
from codecortex.indexing.resolution import CrossFileResolver


def test_resolver_prefers_same_directory_and_reports_ambiguity() -> None:
    resolver = CrossFileResolver()
    candidates = [
        GraphNode(id="a", kind="function", name="run", path="src/auth/helper.py"),
        GraphNode(id="b", kind="function", name="run", path="other/helper.py"),
    ]
    result = resolver.resolve("run", "src/auth/service.py", candidates, "calls")
    assert result.target_id == "a"
    assert result.confidence > 0.4
    assert 0.0 <= result.ambiguity <= 1.0
    assert len(result.candidates) == 2
