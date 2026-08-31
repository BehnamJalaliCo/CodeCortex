from codecortex.workspace import MultiRepositoryWorkspace


def test_workspace_federates_search_and_links_shared_symbols(tmp_path) -> None:
    api = tmp_path / "api"
    worker = tmp_path / "worker"
    api.mkdir()
    worker.mkdir()
    (api / "auth.py").write_text("def refresh_token():\n    return True\n", encoding="utf-8")
    (worker / "jobs.py").write_text("def refresh_token():\n    return False\n", encoding="utf-8")

    workspace = MultiRepositoryWorkspace(tmp_path / "workspace.json")
    workspace.add_repository("api", api)
    workspace.add_repository("worker", worker)
    hits = workspace.search("refresh_token")
    assert {hit.repository for hit in hits[:2]} == {"api", "worker"}

    graph = workspace.federated_graph()
    assert any(edge.kind == "cross_repo_symbol" for edge in graph.edges)
    assert all(node.id.startswith("repo:") for node in graph.nodes)
