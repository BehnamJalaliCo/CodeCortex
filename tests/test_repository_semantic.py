from codecortex.retrieval import RepositorySemanticIndex


def test_repository_semantic_index_ingests_graph_and_source(tmp_path) -> None:
    (tmp_path / "auth.py").write_text(
        "def refresh_token():\n    return 'rotating session token'\n",
        encoding="utf-8",
    )
    index = RepositorySemanticIndex(tmp_path)
    count = index.refresh()
    hits = index.search("rotating session refresh", limit=5)
    assert count >= 2
    assert any(hit.document.metadata.get("symbol") == "refresh_token" for hit in hits)
