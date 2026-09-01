"""Build the repository knowledge graph."""

from __future__ import annotations

from pathlib import Path

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.indexing.relationships import RelationshipExtractor
from codecortex.indexing.resolution import CrossFileResolver
from codecortex.symbols import SymbolProviderRegistry

_EXCLUDED = {
    ".git",
    ".codecortex",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}


class ProjectIndexer:
    def __init__(self, root: Path, max_files: int = 5_000) -> None:
        self.root = root.resolve()
        self.max_files = max_files
        self.symbols = SymbolProviderRegistry()
        self.relationships = RelationshipExtractor()
        self.resolver = CrossFileResolver()

    def _files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if len(files) >= self.max_files:
                break
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            files.append(path)
        return sorted(files)

    @staticmethod
    def _symbol_id(relative: str, name: str, kind: str, line: int, container: str | None) -> str:
        owner = f"{container}::" if container else ""
        return f"symbol:{relative}:{line}:{kind}:{owner}{name}"

    def build(self) -> ProjectGraph:
        files = self._files()
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        node_ids: set[str] = set()
        names: dict[str, list[GraphNode]] = {}
        file_sources: dict[Path, str] = {}
        symbols_by_file: dict[str, list[GraphNode]] = {}

        for path in files:
            relative = path.relative_to(self.root)
            relative_name = relative.as_posix()
            file_id = f"file:{relative_name}"
            self._node(
                nodes,
                node_ids,
                GraphNode(
                    id=file_id,
                    kind="file",
                    name=relative.name,
                    path=relative_name,
                    metadata={"extension": relative.suffix.lower()},
                ),
            )
            if not self.symbols.supports(path):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            file_sources[path] = source
            for symbol in self.symbols.extract(path, source):
                if symbol.kind in {"import", "export"}:
                    continue
                symbol_id = self._symbol_id(
                    relative_name, symbol.name, symbol.kind, symbol.line, symbol.container
                )
                node = GraphNode(
                    id=symbol_id,
                    kind=symbol.kind,
                    name=symbol.name,
                    path=relative_name,
                    line=symbol.line,
                    metadata={
                        "language": symbol.language,
                        "container": symbol.container,
                    },
                )
                self._node(nodes, node_ids, node)
                edges.append(GraphEdge(source=file_id, target=symbol_id, kind="contains"))
                edges.append(GraphEdge(source=file_id, target=symbol_id, kind="defines"))
                names.setdefault(symbol.name, []).append(node)
                symbols_by_file.setdefault(relative_name, []).append(node)

        for path, source in file_sources.items():
            relative = path.relative_to(self.root)
            source_path = relative.as_posix()
            file_id = f"file:{source_path}"
            local_nodes = sorted(
                symbols_by_file.get(source_path, []),
                key=lambda item: (item.line or 0, item.id),
            )
            for relation in self.relationships.extract(path, source):
                source_id = self._relation_source_id(
                    file_id, local_nodes, relation.source_symbol, relation.line
                )
                target_id, metadata = self._resolve_target(
                    relation.target,
                    relation.kind,
                    source_path,
                    names,
                    nodes,
                    node_ids,
                )
                metadata["line"] = relation.line
                edges.append(
                    GraphEdge(
                        source=source_id,
                        target=target_id,
                        kind=relation.kind,
                        metadata=metadata,
                    )
                )

        unique_edges = {
            (edge.source, edge.target, edge.kind): edge
            for edge in edges
            if edge.source != edge.target
        }
        return ProjectGraph(nodes=nodes, edges=list(unique_edges.values()))

    @staticmethod
    def _relation_source_id(
        file_id: str,
        local_nodes: list[GraphNode],
        source_symbol: str | None,
        relation_line: int,
    ) -> str:
        if not source_symbol:
            return file_id
        candidates = [
            node
            for node in local_nodes
            if node.name == source_symbol and (node.line or 0) <= relation_line
        ]
        if not candidates:
            return file_id
        return max(candidates, key=lambda item: (item.line or 0, item.id)).id

    @staticmethod
    def _node(nodes: list[GraphNode], node_ids: set[str], node: GraphNode) -> None:
        if node.id not in node_ids:
            node_ids.add(node.id)
            nodes.append(node)

    def _resolve_target(
        self,
        target: str,
        kind: str,
        source_path: str,
        names: dict[str, list[GraphNode]],
        nodes: list[GraphNode],
        node_ids: set[str],
    ) -> tuple[str, dict[str, object]]:
        candidates = names.get(target, [])
        result = self.resolver.resolve(target, source_path, candidates, kind)
        if result.target_id is not None:
            return result.target_id, {
                "resolution_confidence": round(result.confidence, 4),
                "ambiguity": round(result.ambiguity, 4),
                "candidate_count": len(result.candidates),
                "candidates": [
                    {
                        "id": item.node_id,
                        "score": round(item.score, 4),
                        "reasons": list(item.reasons),
                    }
                    for item in result.candidates
                ],
            }
        prefix = "module" if kind == "imports" else "reference"
        target_id = f"{prefix}:{target}"
        if target_id not in node_ids:
            node_ids.add(target_id)
            nodes.append(GraphNode(id=target_id, kind=prefix, name=target))
        return target_id, {
            "resolution_confidence": 0.0,
            "ambiguity": 1.0,
            "candidate_count": 0,
        }
