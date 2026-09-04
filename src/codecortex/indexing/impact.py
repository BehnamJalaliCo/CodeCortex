"""Graph-based change impact analysis."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph

#: Resolution labels an edge can carry, ordered from strongest to weakest.
EXACT_RESOLUTIONS = frozenset({"exact"})
STALE_RESOLUTIONS = frozenset({"stale_exact"})

#: Multiplier applied to an edge's weight based on how it was resolved. An
#: exact edge is trusted fully; an unresolved one still contributes, because a
#: dependency CodeCortex could not resolve is a risk, not an absence of risk.
RESOLUTION_MULTIPLIERS = {
    "exact": 1.0,
    "stale_exact": 0.75,
    "inferred": 0.85,
    "unresolved": 0.6,
}


@dataclass(frozen=True, slots=True)
class ImpactItem:
    node: GraphNode
    depth: int
    via: str
    risk: float
    #: Strongest resolution seen on the path that reached this node.
    evidence: str = "inferred"

    @property
    def exact(self) -> bool:
        return self.evidence in EXACT_RESOLUTIONS

    @property
    def stale(self) -> bool:
        """True when the path relied on an index that no longer matches the source."""
        return self.evidence in STALE_RESOLUTIONS


@dataclass(frozen=True, slots=True)
class ImpactReport:
    target: GraphNode
    direct: tuple[ImpactItem, ...]
    indirect: tuple[ImpactItem, ...]
    affected_tests: tuple[ImpactItem, ...]
    risk_score: float

    @property
    def exact_items(self) -> tuple[ImpactItem, ...]:
        return tuple(item for item in (*self.direct, *self.indirect) if item.exact)

    def evidence_quality(self) -> dict[str, int]:
        """Count how each reached node was resolved, so risk can be read honestly."""
        counts: dict[str, int] = {}
        for item in (*self.direct, *self.indirect):
            counts[item.evidence] = counts.get(item.evidence, 0) + 1
        return counts

    def to_text(self) -> str:
        quality = self.evidence_quality()
        lines = [
            f"Target: {self.target.kind} {self.target.name}",
            f"Risk score: {self.risk_score:.2f}",
            f"Direct dependencies: {len(self.direct)}",
            f"Indirect dependencies: {len(self.indirect)}",
            f"Affected tests: {len(self.affected_tests)}",
            "Evidence: "
            + (
                ", ".join(f"{key}={value}" for key, value in sorted(quality.items()))
                if quality
                else "none"
            ),
        ]
        ranked = sorted(
            (*self.direct, *self.indirect),
            key=lambda item: (-item.risk, item.depth, item.node.name),
        )[:20]
        if ranked:
            lines.append("\nHighest risk:")
            lines.extend(
                f"- {item.node.name} [{item.via}, depth={item.depth}, "
                f"risk={item.risk:.2f}, evidence={item.evidence}]"
                for item in ranked
            )
        return "\n".join(lines)


class ImpactAnalyzer:
    WEIGHTS = {
        "references": 1.0,
        "calls": 1.0,
        "inherits": 1.0,
        "implements": 0.9,
        "imports": 0.7,
        "contains": 0.35,
    }

    @staticmethod
    def _resolution(edge: GraphEdge) -> str:
        """Classify how an edge was resolved, defaulting to heuristic inference."""
        declared = edge.metadata.get("resolution")
        if isinstance(declared, str) and declared in RESOLUTION_MULTIPLIERS:
            return declared
        confidence = edge.metadata.get("resolution_confidence")
        if isinstance(confidence, (int, float)) and confidence <= 0.0:
            return "unresolved"
        return "inferred"

    @classmethod
    def _edge_weight(cls, edge: GraphEdge) -> tuple[float, str]:
        resolution = cls._resolution(edge)
        base = cls.WEIGHTS.get(edge.kind, 0.5)
        return base * RESOLUTION_MULTIPLIERS[resolution], resolution

    def __init__(self, graph: ProjectGraph, max_depth: int = 5) -> None:
        self.graph = graph
        self.max_depth = max_depth
        self._nodes = {node.id: node for node in graph.nodes}
        incoming: dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in graph.edges:
            incoming[edge.target].append(edge)
        self._incoming = incoming

    def _find_target(self, query: str) -> GraphNode:
        lowered = query.lower()
        exact = [node for node in self.graph.nodes if node.name.lower() == lowered]
        if exact:
            exact.sort(key=lambda node: (node.kind == "file", node.path or ""))
            return exact[0]
        matches = self.graph.search(query, limit=1)
        if not matches:
            raise ValueError(f"No graph node found for: {query}")
        return matches[0]

    def analyze(self, query: str) -> ImpactReport:
        target = self._find_target(query)
        queue: deque[tuple[str, int, float, str, str]] = deque()
        for edge in self._incoming.get(target.id, []):
            weight, resolution = self._edge_weight(edge)
            queue.append((edge.source, 1, weight, edge.kind, resolution))

        seen: dict[str, ImpactItem] = {}
        while queue:
            node_id, depth, strength, via, resolution = queue.popleft()
            if depth > self.max_depth or node_id == target.id:
                continue
            node = self._nodes.get(node_id)
            if node is None:
                continue
            risk = strength / max(1.0, depth * 0.85)
            existing = seen.get(node_id)
            if existing is not None and existing.risk >= risk:
                continue
            item = ImpactItem(
                node=node, depth=depth, via=via, risk=min(1.0, risk), evidence=resolution
            )
            seen[node_id] = item
            for edge in self._incoming.get(node_id, []):
                weight, edge_resolution = self._edge_weight(edge)
                queue.append(
                    (edge.source, depth + 1, strength * weight, edge.kind, edge_resolution)
                )

        items = list(seen.values())
        direct = tuple(sorted((item for item in items if item.depth == 1), key=self._sort))
        indirect = tuple(sorted((item for item in items if item.depth > 1), key=self._sort))
        tests = tuple(item for item in items if self._is_test(item.node))
        if items:
            average = sum(item.risk for item in items) / len(items)
            breadth = min(1.0, len(items) / 25)
            risk_score = min(1.0, average * 0.7 + breadth * 0.3)
        else:
            risk_score = 0.0
        return ImpactReport(target, direct, indirect, tests, risk_score)

    @staticmethod
    def _sort(item: ImpactItem) -> tuple[float, int, str]:
        return (-item.risk, item.depth, item.node.name)

    @staticmethod
    def _is_test(node: GraphNode) -> bool:
        path = (node.path or "").lower()
        name = node.name.lower()
        return (
            "/test" in f"/{path}"
            or "tests/" in path
            or name.startswith("test_")
            or name.endswith("test")
            or name.endswith("tests")
        )
