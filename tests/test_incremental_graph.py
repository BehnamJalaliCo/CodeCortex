import json
from pathlib import Path

from codecortex.indexing.graph import GraphEdge, ProjectGraph
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.indexing.indexer import ProjectIndexer


def _semantic_edges(graph: ProjectGraph) -> set[tuple[str, str, str]]:
    return {
        (edge.source, edge.target, edge.kind)
        for edge in graph.edges
        if edge.kind not in {"contains", "defines"}
    }


def _canonical_graph(graph: ProjectGraph) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    nodes = sorted(
        (
            node.id,
            node.kind,
            node.name,
            node.path,
            node.line,
            json.dumps(node.metadata, sort_keys=True),
        )
        for node in graph.nodes
    )
    edges = sorted(
        (
            edge.source,
            edge.target,
            edge.kind,
            json.dumps(edge.metadata, sort_keys=True),
        )
        for edge in graph.edges
    )
    return nodes, edges


def _assert_matches_full(root: Path, graph: ProjectGraph) -> ProjectGraph:
    clean = ProjectIndexer(root).build()
    assert _canonical_graph(graph) == _canonical_graph(clean)
    return clean


def _calls(graph: ProjectGraph, source_name: str) -> list[GraphEdge]:
    nodes = {node.id: node for node in graph.nodes}
    return [
        edge
        for edge in graph.edges
        if edge.kind == "calls"
        and edge.source in nodes
        and nodes[edge.source].name == source_name
    ]


def test_incremental_graph_reparses_dirty_and_dependent_files(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    second.write_text("def beta():\n    return alpha()\n", encoding="utf-8")
    index = IncrementalGraphIndex(tmp_path)

    initial_graph, initial = index.refresh()
    assert initial.full_rebuild is True
    initial_calls = [edge for edge in initial_graph.edges if edge.kind == "calls"]
    assert any("beta" in edge.source and "alpha" in edge.target for edge in initial_calls)

    _, unchanged = index.refresh()
    assert unchanged.files_reparsed == 0

    first.write_text("# line shift\ndef alpha():\n    return 2\n", encoding="utf-8")
    graph, changed = index.refresh()
    assert changed.full_rebuild is False
    assert changed.files_reparsed == 2
    calls = [edge for edge in graph.edges if edge.kind == "calls"]
    assert any("beta" in edge.source and "alpha" in edge.target for edge in calls)

    clean = _assert_matches_full(tmp_path, graph)
    assert _semantic_edges(graph) == _semantic_edges(clean)


def test_incremental_graph_resolves_unchanged_caller_after_definition_is_added(tmp_path: Path) -> None:
    caller = tmp_path / "caller.py"
    caller.write_text("def beta():\n    return alpha()\n", encoding="utf-8")
    index = IncrementalGraphIndex(tmp_path)

    initial, _ = index.refresh()
    initial_calls = _calls(initial, "beta")
    assert len(initial_calls) == 1
    assert initial_calls[0].target == "reference:alpha"

    definition = tmp_path / "definition.py"
    definition.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    graph, changed = index.refresh()

    assert changed.full_rebuild is False
    assert changed.files_reparsed == 2
    calls = _calls(graph, "beta")
    assert len(calls) == 1
    assert "alpha" in calls[0].target
    assert all(node.id != "reference:alpha" for node in graph.nodes)
    _assert_matches_full(tmp_path, graph)


def test_incremental_graph_matches_full_after_definition_rename_and_removal(tmp_path: Path) -> None:
    definition = tmp_path / "definition.py"
    caller = tmp_path / "caller.py"
    definition.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    caller.write_text("def beta():\n    return alpha()\n", encoding="utf-8")
    index = IncrementalGraphIndex(tmp_path)
    index.refresh()

    definition.write_text("def omega():\n    return 2\n", encoding="utf-8")
    graph, renamed = index.refresh()
    assert renamed.files_reparsed == 2
    calls = _calls(graph, "beta")
    assert len(calls) == 1
    assert calls[0].target == "reference:alpha"
    _assert_matches_full(tmp_path, graph)

    caller.write_text("def beta():\n    return omega()\n", encoding="utf-8")
    graph, changed_caller = index.refresh()
    assert changed_caller.files_reparsed == 1
    calls = _calls(graph, "beta")
    assert len(calls) == 1
    assert "omega" in calls[0].target
    _assert_matches_full(tmp_path, graph)

    definition.unlink()
    graph, removed = index.refresh()
    assert removed.files_reparsed == 1
    calls = _calls(graph, "beta")
    assert len(calls) == 1
    assert calls[0].target == "reference:omega"
    _assert_matches_full(tmp_path, graph)


def test_incremental_graph_reresolves_ambiguity_when_same_name_target_is_added(tmp_path: Path) -> None:
    left = tmp_path / "left.py"
    caller = tmp_path / "caller.py"
    left.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    caller.write_text("def beta():\n    return alpha()\n", encoding="utf-8")
    index = IncrementalGraphIndex(tmp_path)
    index.refresh()

    right = tmp_path / "right.py"
    right.write_text("def alpha():\n    return 2\n", encoding="utf-8")
    graph, changed = index.refresh()

    assert changed.files_reparsed == 2
    calls = _calls(graph, "beta")
    assert len(calls) == 1
    assert calls[0].metadata["candidate_count"] == 2
    assert calls[0].metadata["ambiguity"] > 0
    assert len(calls[0].metadata["candidates"]) == 2
    _assert_matches_full(tmp_path, graph)


def test_incremental_graph_reresolves_unchanged_transitive_caller_after_dependency_change(tmp_path: Path) -> None:
    definitions = tmp_path / "definitions.py"
    middle = tmp_path / "middle.py"
    caller = tmp_path / "caller.py"
    definitions.write_text(
        "def alpha():\n    return 1\n\n"
        "def delta():\n    return 2\n",
        encoding="utf-8",
    )
    middle.write_text("def beta():\n    return alpha()\n", encoding="utf-8")
    caller.write_text("def gamma():\n    return beta()\n", encoding="utf-8")
    index = IncrementalGraphIndex(tmp_path)
    index.refresh()

    middle.write_text("# changed caller\ndef beta():\n    return delta()\n", encoding="utf-8")
    graph, changed = index.refresh()

    assert changed.files_reparsed == 2
    beta_calls = _calls(graph, "beta")
    gamma_calls = _calls(graph, "gamma")
    assert len(beta_calls) == 1 and "delta" in beta_calls[0].target
    assert len(gamma_calls) == 1 and "beta" in gamma_calls[0].target
    _assert_matches_full(tmp_path, graph)


def test_qualified_symbol_ids_do_not_collapse_same_method_name(tmp_path: Path) -> None:
    source = tmp_path / "models.py"
    source.write_text(
        "class A:\n"
        "    def save(self):\n"
        "        helper()\n\n"
        "class B:\n"
        "    def save(self):\n"
        "        other()\n\n"
        "def helper():\n    return 1\n\n"
        "def other():\n    return 2\n",
        encoding="utf-8",
    )
    graph = ProjectIndexer(tmp_path).build()
    saves = [node for node in graph.nodes if node.name == "save"]
    assert len(saves) == 2
    assert len({node.id for node in saves}) == 2
    assert any("A::save" in node.id for node in saves)
    assert any("B::save" in node.id for node in saves)


def test_incremental_graph_preserves_duplicate_method_identity_after_mutation(tmp_path: Path) -> None:
    source = tmp_path / "models.py"
    source.write_text(
        "class A:\n"
        "    def save(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    index = IncrementalGraphIndex(tmp_path)
    index.refresh()

    source.write_text(
        "class A:\n"
        "    def save(self):\n"
        "        return 1\n\n"
        "class B:\n"
        "    def save(self):\n"
        "        return 2\n",
        encoding="utf-8",
    )
    graph, changed = index.refresh()

    assert changed.files_reparsed == 1
    saves = [node for node in graph.nodes if node.name == "save"]
    assert len(saves) == 2
    assert len({node.id for node in saves}) == 2
    assert any("A::save" in node.id for node in saves)
    assert any("B::save" in node.id for node in saves)
    _assert_matches_full(tmp_path, graph)
