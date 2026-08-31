"""Build the repository knowledge graph."""

from __future__ import annotations

from pathlib import Path

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.indexing.relationships import RelationshipExtractor
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

    def build(self) -> ProjectGraph:
        files = self._files()
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        node_ids: set[str] = set()
        names: dict[str, list[str]] = {}
        file_sources: dict[Path, str] = {}
        symbol_for_file: dict[tuple[str, str], str] = {}

        for path in files:
            relative = path.relative_to(self.root)
            file_id = f"file:{relative.as_posix()}"
            self._node(nodes, node_ids, GraphNode(
                id=file_id,
                kind="file",
                name=relative.name,
                path=relative.as_posix(),
                metadata={"extension": relative.suffix.lower()},
            ))
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
                symbol_id = (
                    f"symbol:{relative.as_posix()}:{symbol.line}:{symbol.kind}:{symbol.name}"
                )
                self._node(nodes, node_ids, GraphNode(
                    id=symbol_id,
                    kind=symbol.kind,
                    name=symbol.name,
                    path=relative.as_posix(),
                    line=symbol.line,
                    metadata={
                        "language": symbol.language,
                        "container": symbol.container,
                    },
                ))
                edges.append(GraphEdge(source=file_id, target=symbol_id, kind="contains"))
                names.setdefault(symbol.name, []).append(symbol_id)
                symbol_for_file[(relative.as_posix(), symbol.name)] = symbol_id

        for path, source in file_sources.items():
            relative = path.relative_to(self.root)
            file_id = f"file:{relative.as_posix()}"
            for relation in self.relationships.extract(path, source):
                source_id = file_id
                if relation.source_symbol:
                    source_id = symbol_for_file.get(
                        (relative.as_posix(), relation.source_symbol),
                        file_id,
                    )
                target_id = self._resolve_target(
                    relation.target,
                    relation.kind,
                    names,
                    nodes,
                    node_ids,
                )
                edges.append(GraphEdge(
                    source=source_id,
                    target=target_id,
                    kind=relation.kind,
                    metadata={"line": relation.line},
                ))

        unique_edges = {
            (edge.source, edge.target, edge.kind): edge
            for edge in edges
            if edge.source != edge.target
        }
        return ProjectGraph(nodes=nodes, edges=list(unique_edges.values()))

    @staticmethod
    def _node(nodes: list[GraphNode], node_ids: set[str], node: GraphNode) -> None:
        if node.id not in node_ids:
            node_ids.add(node.id)
            nodes.append(node)

    @staticmethod
    def _resolve_target(
        target: str,
        kind: str,
        names: dict[str, list[str]],
        nodes: list[GraphNode],
        node_ids: set[str],
    ) -> str:
        candidates = names.get(target)
        if candidates and len(candidates) == 1:
            return candidates[0]
        prefix = "module" if kind == "imports" else "reference"
        target_id = f"{prefix}:{target}"
        if target_id not in node_ids:
            node_ids.add(target_id)
            nodes.append(GraphNode(id=target_id, kind=prefix, name=target))
        return target_id
