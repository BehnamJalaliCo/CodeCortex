"""Repository semantic-search application service with explainable ranking output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.retrieval import RepositorySemanticIndex


class RepositorySearchService:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def search(self, query: str, limit: int = 20) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("search query is required")
        bounded = min(100, max(1, limit))
        graph, _ = IncrementalGraphIndex(self.root).refresh()
        index = RepositorySemanticIndex(self.root)
        index.refresh(graph)
        hits = index.search(query, bounded)
        return {
            "query": query,
            "hits": [
                {
                    "id": hit.document.id,
                    "score": hit.score,
                    "vector_score": hit.vector_score,
                    "lexical_score": hit.lexical_score,
                    "structural_score": hit.structural_score,
                    "metadata": hit.document.metadata,
                }
                for hit in hits
            ],
        }
