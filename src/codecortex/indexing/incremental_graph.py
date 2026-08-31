"""Incremental graph maintenance without full repository rebuilds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.indexing.incremental import IncrementalIndex, IndexStats
from codecortex.indexing.indexer import ProjectIndexer
from codecortex.indexing.relationships import RelationshipExtractor
from codecortex.indexing.resolution import CrossFileResolver
from codecortex.symbols import SymbolProviderRegistry


@dataclass(frozen=True, slots=True)
class GraphUpdateStats:
    index: IndexStats
    full_rebuild: bool
    nodes_before: int
    nodes_after: int
    edges_before: int
    edges_after: int
    files_reparsed: int


class IncrementalGraphIndex:
    """Persist and patch graph fragments for files reported dirty by the manifest."""

    def __init__(self, root: Path, graph_path: Path | None = None) -> None:
        self.root = root.resolve()
        self.graph_path = graph_path or self.root / ".codecortex" / "index" / "graph.json"
        self.manifest = IncrementalIndex(self.root)
        self.symbols = SymbolProviderRegistry()
        self.relationships = RelationshipExtractor()
        self.resolver = CrossFileResolver()

    def refresh(self) -> tuple[ProjectGraph, GraphUpdateStats]:
        index_stats = self.manifest.refresh()
        previous = ProjectGraph.load(self.graph_path)
        before_nodes = len(previous.nodes)
        before_edges = len(previous.edges)
        if not previous.nodes:
            graph = ProjectIndexer(self.root).build()
            graph.save(self.graph_path)
            return graph, GraphUpdateStats(
                index=index_stats,
                full_rebuild=True,
                nodes_before=before_nodes,
                nodes_after=len(graph.nodes),
                edges_before=before_edges,
                edges_after=len(graph.edges),
                files_reparsed=index_stats.tracked,
            )
        dirty = set(index_stats.added) | set(index_stats.changed) | set(index_stats.removed)
        if not dirty:
            return previous, GraphUpdateStats(
                index=index_stats,
                full_rebuild=False,
                nodes_before=before_nodes,
                nodes_after=before_nodes,
                edges_before=before_edges,
                edges_after=before_edges,
                files_reparsed=0,
            )

        removed_ids = {node.id for node in previous.nodes if node.path in dirty}
        retained_nodes = [node for node in previous.nodes if node.id not in removed_ids]
        retained_edges = [
            edge
            for edge in previous.edges
            if edge.source not in removed_ids and edge.target not in removed_ids
        ]
        new_nodes, new_edges = self._fragments(sorted(set(index_stats.added) | set(index_stats.changed)), retained_nodes)
        node_map = {node.id: node for node in retained_nodes}
        node_map.update({node.id: node for node in new_nodes})
        edge_map = {
            (edge.source, edge.target, edge.kind): edge
            for edge in retained_edges + new_edges
            if edge.source != edge.target
        }
        graph = ProjectGraph(nodes=list(node_map.values()), edges=list(edge_map.values()))
        graph.save(self.graph_path)
        return graph, GraphUpdateStats(
            index=index_stats,
            full_rebuild=False,
            nodes_before=before_nodes,
            nodes_after=len(graph.nodes),
            edges_before=before_edges,
            edges_after=len(graph.edges),
            files_reparsed=len(index_stats.added) + len(index_stats.changed),
        )

    def _fragments(
        self,
        paths: list[str],
        retained_nodes: list[GraphNode],
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        names: dict[str, list[GraphNode]] = {}
        for node in retained_nodes:
            if node.kind not in {"file", "module", "reference"}:
                names.setdefault(node.name, []).append(node)
        sources: dict[str, str] = {}
        local_symbols: dict[tuple[str, str], str] = {}

        for relative in paths:
            path = self.root / relative
            if not path.is_file():
                continue
            file_id = f"file:{relative}"
            nodes.append(
                GraphNode(
                    id=file_id,
                    kind="file",
                    name=path.name,
                    path=relative,
                    metadata={"extension": path.suffix.lower()},
                )
            )
            if not self.symbols.supports(path):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            sources[relative] = source
            for symbol in self.symbols.extract(path, source):
                if symbol.kind in {"import", "export"}:
                    continue
                node = GraphNode(
                    id=f"symbol:{relative}:{symbol.line}:{symbol.kind}:{symbol.name}",
                    kind=symbol.kind,
                    name=symbol.name,
                    path=relative,
                    line=symbol.line,
                    metadata={"language": symbol.language, "container": symbol.container},
                )
                nodes.append(node)
                names.setdefault(node.name, []).append(node)
                local_symbols[(relative, node.name)] = node.id
                edges.extend(
                    [
                        GraphEdge(source=file_id, target=node.id, kind="contains"),
                        GraphEdge(source=file_id, target=node.id, kind="defines"),
                    ]
                )

        existing_ids = {node.id for node in retained_nodes + nodes}
        for relative, source in sources.items():
            file_id = f"file:{relative}"
            path = self.root / relative
            for relation in self.relationships.extract(path, source):
                source_id = local_symbols.get((relative, relation.source_symbol or ""), file_id)
                resolution = self.resolver.resolve(
                    relation.target,
                    relative,
                    names.get(relation.target, []),
                    relation.kind,
                )
                if resolution.target_id:
                    target_id = resolution.target_id
                    metadata: dict[str, object] = {
                        "resolution_confidence": round(resolution.confidence, 4),
                        "ambiguity": round(resolution.ambiguity, 4),
                        "candidate_count": len(resolution.candidates),
                    }
                else:
                    prefix = "module" if relation.kind == "imports" else "reference"
                    target_id = f"{prefix}:{relation.target}"
                    metadata = {
                        "resolution_confidence": 0.0,
                        "ambiguity": 1.0,
                        "candidate_count": 0,
                    }
                    if target_id not in existing_ids:
                        existing_ids.add(target_id)
                        nodes.append(GraphNode(id=target_id, kind=prefix, name=relation.target))
                metadata["line"] = relation.line
                edges.append(
                    GraphEdge(
                        source=source_id,
                        target=target_id,
                        kind=relation.kind,
                        metadata=metadata,
                    )
                )
        return nodes, edges
