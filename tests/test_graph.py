from codecortex.indexing import ProjectIndexer


def test_project_indexer_builds_file_symbol_and_import_edges(tmp_path) -> None:
    (tmp_path / "service.py").write_text(
        "from helper import run\n\nclass Service:\n    def execute(self):\n        return run()\n",
        encoding="utf-8",
    )
    (tmp_path / "helper.py").write_text("def run():\n    return True\n", encoding="utf-8")

    graph = ProjectIndexer(tmp_path).build()

    assert any(node.kind == "class" and node.name == "Service" for node in graph.nodes)
    assert any(node.kind == "function" and node.name == "run" for node in graph.nodes)
    assert any(edge.kind == "defines" for edge in graph.edges)
    assert any(edge.kind == "imports" for edge in graph.edges)
