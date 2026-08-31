from codecortex.indexing.indexer import ProjectIndexer


def test_graph_contains_calls_imports_and_inheritance(tmp_path):
    (tmp_path / "base.py").write_text(
        "class Base:\n    pass\n\ndef helper():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "service.py").write_text(
        "from base import Base\nfrom base import helper\n"
        "class Service(Base):\n    def run(self):\n        return helper()\n",
        encoding="utf-8",
    )
    graph = ProjectIndexer(tmp_path).build()
    kinds = {edge.kind for edge in graph.edges}
    assert {"contains", "imports", "calls", "inherits"} <= kinds
