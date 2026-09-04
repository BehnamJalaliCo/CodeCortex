"""Incremental graph maintenance with full-build semantic equivalence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.indexing.incremental import IncrementalIndex, IndexStats
from codecortex.indexing.indexer import ProjectIndexer
from codecortex.indexing.relationships import RelationshipExtractor
from codecortex.indexing.resolution import CrossFileResolver
from codecortex.languages import LanguageRegistry


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
    """Patch a persistent graph while re-resolving unchanged dependants."""

    _STRUCTURAL_EDGE_KINDS = {"contains", "defines"}

    def __init__(self, root: Path, graph_path: Path | None = None) -> None:
        self.root = root.resolve()
        self.graph_path = graph_path or self.root / ".codecortex" / "index" / "graph.json"
        self.manifest = IncrementalIndex(self.root)
        self.languages = LanguageRegistry()
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
                index_stats,
                True,
                before_nodes,
                len(graph.nodes),
                before_edges,
                len(graph.edges),
                index_stats.tracked,
            )
        dirty = set(index_stats.added) | set(index_stats.changed) | set(index_stats.removed)
        if not dirty:
            return previous, GraphUpdateStats(
                index_stats, False, before_nodes, before_nodes, before_edges, before_edges, 0
            )

        node_by_id = {node.id: node for node in previous.nodes}
        removed_ids = {node.id for node in previous.nodes if node.path in dirty}
        affected_paths: set[str] = set()
        for edge in previous.edges:
            if edge.target not in removed_ids or edge.kind in self._STRUCTURAL_EDGE_KINDS:
                continue
            source = node_by_id.get(edge.source)
            if source is not None and source.path and source.path not in dirty:
                affected_paths.add(source.path)

        retained_nodes = [node for node in previous.nodes if node.id not in removed_ids]
        affected_source_ids = {node.id for node in retained_nodes if node.path in affected_paths}
        retained_edges = [
            edge
            for edge in previous.edges
            if edge.source not in removed_ids
            and edge.target not in removed_ids
            and not (
                edge.source in affected_source_ids and edge.kind not in self._STRUCTURAL_EDGE_KINDS
            )
        ]
        changed_paths = sorted(set(index_stats.added) | set(index_stats.changed))
        new_nodes, structural_edges, sources = self._parse_changed(changed_paths)
        all_nodes = [*retained_nodes, *new_nodes]
        relation_edges = self._relationship_edges(
            sorted(set(changed_paths) | affected_paths), all_nodes, sources
        )
        node_map = {node.id: node for node in all_nodes}
        edge_map = {
            (edge.source, edge.target, edge.kind): edge
            for edge in [*retained_edges, *structural_edges, *relation_edges]
            if edge.source != edge.target
        }
        graph = ProjectGraph(nodes=list(node_map.values()), edges=list(edge_map.values()))
        graph.save(self.graph_path)
        return graph, GraphUpdateStats(
            index_stats,
            False,
            before_nodes,
            len(graph.nodes),
            before_edges,
            len(graph.edges),
            len(changed_paths) + len(affected_paths),
        )

    @staticmethod
    def _symbol_id(relative: str, name: str, kind: str, line: int, container: str | None) -> str:
        owner = f"{container}::" if container else ""
        return f"symbol:{relative}:{line}:{kind}:{owner}{name}"

    def _parse_changed(
        self, paths: list[str]
    ) -> tuple[list[GraphNode], list[GraphEdge], dict[str, str]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        sources: dict[str, str] = {}
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
            spec = self.languages.language_for(path)
            if spec is None:
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            sources[relative] = source
            for unit in self.languages.parse(path, source):
                node = GraphNode(
                    id=self._symbol_id(relative, unit.name, unit.kind, unit.line, unit.container),
                    kind=unit.kind,
                    name=unit.name,
                    path=relative,
                    line=unit.line,
                    metadata={
                        "language": spec.name,
                        "container": unit.container,
                        "end_line": unit.end_line,
                        "signature": unit.signature,
                        "return_type": unit.return_type,
                    },
                )
                nodes.append(node)
                edges.extend(
                    [
                        GraphEdge(source=file_id, target=node.id, kind="contains"),
                        GraphEdge(source=file_id, target=node.id, kind="defines"),
                    ]
                )
        return nodes, edges, sources

    def _relationship_edges(
        self, paths: list[str], nodes: list[GraphNode], preloaded_sources: dict[str, str]
    ) -> list[GraphEdge]:
        names: dict[str, list[GraphNode]] = {}
        nodes_by_path: dict[str, list[GraphNode]] = {}
        existing_ids = {node.id for node in nodes}
        for node in nodes:
            if node.kind not in {"file", "module", "reference"}:
                names.setdefault(node.name, []).append(node)
                if node.path:
                    nodes_by_path.setdefault(node.path, []).append(node)
        edges: list[GraphEdge] = []
        for relative in paths:
            path = self.root / relative
            if not path.is_file() or self.languages.language_for(path) is None:
                continue
            source = preloaded_sources.get(relative)
            if source is None:
                try:
                    source = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
            file_id = f"file:{relative}"
            local_nodes = sorted(
                nodes_by_path.get(relative, []), key=lambda item: (item.line or 0, item.id)
            )
            for relation in self.relationships.extract(path, source):
                source_id = self._relation_source_id(
                    file_id, local_nodes, relation.source_symbol, relation.line
                )
                resolution = self.resolver.resolve(
                    relation.target, relative, names.get(relation.target, []), relation.kind
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
                        source=source_id, target=target_id, kind=relation.kind, metadata=metadata
                    )
                )
        return edges

    @staticmethod
    def _relation_source_id(
        file_id: str, local_nodes: list[GraphNode], source_symbol: str | None, relation_line: int
    ) -> str:
        if not source_symbol:
            return file_id
        candidates = [
            node
            for node in local_nodes
            if node.name == source_symbol and (node.line or 0) <= relation_line
        ]
        return (
            max(candidates, key=lambda item: (item.line or 0, item.id)).id
            if candidates
            else file_id
        )
