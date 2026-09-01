import asyncio

import pytest

from codecortex.context.budget import BudgetContextProcessor
from codecortex.context.pipeline import ContextCache, ContextPipeline
from codecortex.context.tokenizer import ApproxTokenCounter
from codecortex.core.models import ContextChunk
from codecortex.indexing.graph import GraphNode, ProjectGraph
from codecortex.retrieval.repository import RepositorySemanticIndex


def test_budget_recounts_and_preserves_distinct_provenance() -> None:
    processor = BudgetContextProcessor(ApproxTokenCounter())
    chunks = [
        ContextChunk(source="file-a", content="same text", tokens=999, metadata={"path": "a.py"}),
        ContextChunk(source="file-b", content="same text", tokens=999, metadata={"path": "b.py"}),
    ]
    fitted = asyncio.run(processor.fit(chunks, 20))
    assert len(fitted) == 2
    assert all(chunk.tokens < 999 for chunk in fitted)


def test_context_cache_key_changes_with_graph_revision() -> None:
    key_a = ContextCache.key("query", 100, ["a"], "graph-a")
    key_b = ContextCache.key("query", 100, ["a"], "graph-b")
    assert key_a != key_b


def test_context_pipeline_rejects_budget_over_project_hard_limit(tmp_path) -> None:
    state = tmp_path / ".codecortex"
    state.mkdir()
    (state / "config.json").write_text('{"context_budget": 10, "hard_context_limit": 20}', encoding="utf-8")
    pipeline = ContextPipeline(tmp_path, ProjectGraph())
    with pytest.raises(ValueError):
        asyncio.run(pipeline.prepare("query", [], 21))


def test_semantic_refresh_only_embeds_changed_documents(tmp_path) -> None:
    class Provider:
        name = "counting"
        dimensions = 2

        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls.append(list(texts))
            return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]

    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    provider = Provider()
    graph = ProjectGraph(nodes=[GraphNode(id="file:a.py", kind="file", name="a.py", path="a.py")])
    semantic = RepositorySemanticIndex(tmp_path, provider=provider)
    semantic.refresh(graph)
    first_calls = len(provider.calls)
    semantic.refresh(graph)
    assert len(provider.calls) == first_calls
