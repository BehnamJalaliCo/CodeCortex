from codecortex.setup import ProjectSetup


def test_project_setup_builds_index_graph_and_integration(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    result = ProjectSetup(tmp_path).run()
    assert result.index.tracked >= 1
    assert result.symbols >= 1
    assert result.graph_nodes >= 2
    assert result.integration_file.exists()
    assert (tmp_path / ".codecortex" / "index" / "graph.json").exists()
