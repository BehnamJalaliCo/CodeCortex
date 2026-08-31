"""Repository-to-semantic-index ingestion."""

from __future__ import annotations

from pathlib import Path

from codecortex.indexing.graph import ProjectGraph
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.retrieval.hybrid import HybridRetriever, RetrievalHit
from codecortex.retrieval.index import SemanticDocument, SemanticIndex
from codecortex.retrieval.providers import EmbeddingProvider, FeatureHashEmbeddingProvider


class RepositorySemanticIndex:
    def __init__(
        self,
        root: Path,
        provider: EmbeddingProvider | None = None,
        index_path: Path | None = None,
        max_snippet_chars: int = 3_000,
    ) -> None:
        self.root = root.resolve()
        self.provider = provider or FeatureHashEmbeddingProvider()
        self.index_path = index_path or self.root / ".codecortex" / "index" / "semantic.json"
        self.index = SemanticIndex(self.provider, self.index_path)
        self.max_snippet_chars = max_snippet_chars

    def refresh(self, graph: ProjectGraph | None = None) -> int:
        graph = graph or IncrementalGraphIndex(self.root).refresh()[0]
        documents = [self._document(node, graph) for node in graph.nodes]
        filtered = [document for document in documents if document is not None]
        self.index.replace(filtered)
        return len(filtered)

    def search(self, query: str, limit: int = 20) -> list[RetrievalHit]:
        if not self.index.document_ids:
            self.refresh()
        return HybridRetriever(self.index).search(query, limit)

    def _document(self, node, graph: ProjectGraph) -> SemanticDocument | None:
        if node.kind in {"module", "reference"}:
            return None
        metadata = {
            "path": node.path or "",
            "symbol": node.name if node.kind != "file" else "",
            "kind": node.kind,
            "line": node.line or 0,
        }
        structural = self._structural_context(node.id, graph)
        if node.path:
            path = self.root / node.path
            snippet = self._snippet(path, node.line)
        else:
            snippet = ""
        text = "\n".join(
            part
            for part in (
                f"{node.kind} {node.name}",
                f"path {node.path}" if node.path else "",
                structural,
                snippet,
            )
            if part
        )
        return SemanticDocument(id=node.id, text=text, metadata=metadata)

    def _snippet(self, path: Path, line: int | None) -> str:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
        if line is None:
            return source[: self.max_snippet_chars]
        lines = source.splitlines()
        start = max(0, line - 8)
        end = min(len(lines), line + 20)
        return "\n".join(lines[start:end])[: self.max_snippet_chars]

    @staticmethod
    def _structural_context(node_id: str, graph: ProjectGraph) -> str:
        relations: list[str] = []
        node_map = {node.id: node for node in graph.nodes}
        for edge in graph.edges:
            if edge.source == node_id:
                target = node_map.get(edge.target)
                if target:
                    relations.append(f"{edge.kind} {target.name}")
            elif edge.target == node_id:
                source = node_map.get(edge.source)
                if source:
                    relations.append(f"used-by {source.name} via {edge.kind}")
            if len(relations) >= 20:
                break
        return "\n".join(relations)
