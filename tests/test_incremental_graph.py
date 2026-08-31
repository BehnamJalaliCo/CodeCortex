from codecortex.indexing.incremental_graph import IncrementalGraphIndex


def test_incremental_graph_reparses_only_dirty_files(tmp_path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    second.write_text("def beta():\n    return alpha()\n", encoding="utf-8")
    index = IncrementalGraphIndex(tmp_path)

    _, initial = index.refresh()
    assert initial.full_rebuild is True

    _, unchanged = index.refresh()
    assert unchanged.files_reparsed == 0

    first.write_text("def alpha():\n    return 2\n", encoding="utf-8")
    graph, changed = index.refresh()
    assert changed.full_rebuild is False
    assert changed.files_reparsed == 1
    assert any(node.name == "alpha" for node in graph.nodes)
