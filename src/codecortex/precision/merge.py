"""Fuse exact precision evidence into the existing project graph.

The heuristic relationship extractor is never removed. When the precision index
resolves the same relationship, the exact edge becomes primary and the weaker
edge is superseded rather than deleted from view: its previous resolution stays
in the edge metadata so conflicts remain debuggable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.precision.models import (
    PrecisionIndex,
    PrecisionOccurrence,
    scoped_symbol_key,
)

#: Edge kind emitted for an exact reference resolved by the precision index.
PRECISE_REFERENCE_KIND = "references"

#: Resolution labels written into edge metadata.
RESOLUTION_EXACT = "exact"
RESOLUTION_INFERRED = "inferred"
RESOLUTION_STALE = "stale_exact"

PROVENANCE_PRECISION = "precision-index"
PROVENANCE_HEURISTIC = "cross-file-heuristic"


@dataclass(frozen=True, slots=True)
class GraphFusionReport:
    """What precision fusion changed, for telemetry and diagnostics."""

    exact_edges: int = 0
    superseded_edges: int = 0
    conflicts: tuple[str, ...] = ()
    unresolved_occurrences: int = 0
    stale: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "exact_edges": self.exact_edges,
            "superseded_edges": self.superseded_edges,
            "conflicts": list(self.conflicts),
            "unresolved_occurrences": self.unresolved_occurrences,
            "stale": self.stale,
        }


@dataclass(slots=True)
class _NodeLocator:
    """Map an indexed position back onto graph symbol nodes."""

    by_path: dict[str, list[GraphNode]] = field(default_factory=dict)

    @classmethod
    def build(cls, graph: ProjectGraph) -> _NodeLocator:
        by_path: dict[str, list[GraphNode]] = {}
        for node in graph.nodes:
            if node.path is None or node.kind in {"file", "module", "reference"}:
                continue
            by_path.setdefault(node.path, []).append(node)
        for nodes in by_path.values():
            nodes.sort(key=lambda item: (item.line or 0, item.id))
        return cls(by_path=by_path)

    def definition_node(self, path: str, line: int) -> GraphNode | None:
        """Return the symbol node declared on ``line`` (one-based)."""
        for node in self.by_path.get(path, []):
            if node.line == line:
                return node
        return None

    def enclosing_node(self, path: str, line: int) -> GraphNode | None:
        """Return the innermost symbol node whose body covers ``line``."""
        best: GraphNode | None = None
        for node in self.by_path.get(path, []):
            start = node.line or 0
            if start > line:
                continue
            end = node.metadata.get("end_line")
            end_line = end if isinstance(end, int) else start
            if end_line >= line and (best is None or start >= (best.line or 0)):
                best = node
        return best


class PrecisionGraphFusion:
    """Merge exact occurrence edges into a project graph."""

    def __init__(self, *, stale: bool = False) -> None:
        self.stale = stale

    def apply(self, graph: ProjectGraph, index: PrecisionIndex) -> GraphFusionReport:
        """Mutate ``graph`` in place, returning what changed."""
        locator = _NodeLocator.build(graph)
        edges_by_key = {
            (edge.source, edge.target, edge.kind): edge for edge in graph.edges
        }
        definitions = self._definition_nodes(index, locator)
        exact = 0
        superseded = 0
        unresolved = 0
        conflicts: list[str] = []
        resolution = RESOLUTION_STALE if self.stale else RESOLUTION_EXACT
        confidence = 0.55 if self.stale else 1.0

        for document in index.documents:
            for occurrence in document.occurrences:
                if occurrence.is_definition:
                    continue
                target = definitions.get(
                    scoped_symbol_key(occurrence.path, occurrence.symbol)
                )
                if target is None:
                    unresolved += 1
                    continue
                source = self._source_node(occurrence, locator, graph)
                if source is None or source == target.id:
                    unresolved += 1
                    continue
                key = (source, target.id, PRECISE_REFERENCE_KIND)
                metadata: dict[str, object] = {
                    "resolution": resolution,
                    "provenance": PROVENANCE_PRECISION,
                    "confidence": confidence,
                    "line": occurrence.range.start_line + 1,
                    "symbol": occurrence.symbol,
                }
                existing = edges_by_key.get(key)
                if existing is not None and existing.metadata.get("resolution") == resolution:
                    continue
                edges_by_key[key] = GraphEdge(
                    source=source,
                    target=target.id,
                    kind=PRECISE_REFERENCE_KIND,
                    metadata=metadata,
                )
                exact += 1
                for weaker_kind in ("calls", "imports"):
                    weaker = edges_by_key.get((source, target.id, weaker_kind))
                    if weaker is None:
                        continue
                    previous = weaker.metadata.get("resolution", RESOLUTION_INFERRED)
                    if previous == resolution:
                        continue
                    superseded += 1
                    conflicts.append(f"{source} -{weaker_kind}-> {target.id}")
                    edges_by_key[(source, target.id, weaker_kind)] = GraphEdge(
                        source=source,
                        target=target.id,
                        kind=weaker_kind,
                        metadata={
                            **weaker.metadata,
                            "superseded_by": resolution,
                            "superseded_provenance": PROVENANCE_PRECISION,
                            "previous_resolution": previous,
                            "previous_provenance": weaker.metadata.get(
                                "provenance", PROVENANCE_HEURISTIC
                            ),
                        },
                    )

        graph.edges = list(edges_by_key.values())
        return GraphFusionReport(
            exact_edges=exact,
            superseded_edges=superseded,
            conflicts=tuple(sorted(set(conflicts))[:20]),
            unresolved_occurrences=unresolved,
            stale=self.stale,
        )

    @staticmethod
    def _definition_nodes(
        index: PrecisionIndex, locator: _NodeLocator
    ) -> dict[str, GraphNode]:
        """Map each defined symbol to its graph node.

        Keys are document-scoped, so a ``local`` id declared in two files does
        not resolve every file's references onto whichever definition happened
        to be indexed first.
        """
        definitions: dict[str, GraphNode] = {}
        for document in index.documents:
            for occurrence in document.occurrences:
                key = scoped_symbol_key(occurrence.path, occurrence.symbol)
                if not occurrence.is_definition or key in definitions:
                    continue
                node = locator.definition_node(
                    occurrence.path, occurrence.range.start_line + 1
                )
                if node is not None:
                    definitions[key] = node
        return definitions

    @staticmethod
    def _source_node(
        occurrence: PrecisionOccurrence,
        locator: _NodeLocator,
        graph: ProjectGraph,
    ) -> str | None:
        node = locator.enclosing_node(occurrence.path, occurrence.range.start_line + 1)
        if node is not None:
            return node.id
        file_id = f"file:{occurrence.path}"
        return file_id if any(item.id == file_id for item in graph.nodes) else None
