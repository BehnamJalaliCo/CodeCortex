from codecortex.retrieval import (
    FeatureHashEmbeddingProvider,
    HybridRetriever,
    SemanticDocument,
    SemanticIndex,
)


def test_semantic_index_persists_and_hybrid_ranks_symbols(tmp_path) -> None:
    path = tmp_path / "semantic.json"
    provider = FeatureHashEmbeddingProvider(128)
    index = SemanticIndex(provider, path)
    index.upsert(
        [
            SemanticDocument(
                id="auth",
                text="refresh authentication token and session",
                metadata={"path": "src/auth/token.py", "symbol": "refresh_token"},
            ),
            SemanticDocument(
                id="billing",
                text="create invoice and calculate tax",
                metadata={"path": "src/billing/invoice.py", "symbol": "invoice"},
            ),
        ]
    )
    reloaded = SemanticIndex(provider, path)
    hits = HybridRetriever(reloaded).search("refresh_token authentication", limit=1)
    assert hits[0].document.id == "auth"
    assert hits[0].score > 0
