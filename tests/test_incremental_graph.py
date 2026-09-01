from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.indexing.indexer import ProjectIndexer


def _semantic_edges(graph):
    return {
        (edge.source, edge.target, edge.kind)
        for edge in graph.edges
        if edge.kind not in {"contains", "defines"}
    }


def test_incremental_graph_reparses_dirty_and_dependent_files(tmp_path) -> None:
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

    clean = ProjectIndexer(tmp_path).build()
    assert _semantic_edges(graph) == _semantic_edges(clean)


def test_qualified_symbol_ids_do_not_collapse_same_method_name(tmp_path) -> None:
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
