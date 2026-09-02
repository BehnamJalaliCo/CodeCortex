"""Shared incremental repository context reused across product requests."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from codecortex.indexing.graph import GraphNode, ProjectGraph
from codecortex.indexing.incremental_graph import GraphUpdateStats, IncrementalGraphIndex


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    graph: ProjectGraph
    stats: GraphUpdateStats
    generation: int


class RepositoryContext:
    """Own repository intelligence that is expensive to construct repeatedly.

    Refresh remains safe to call for every request because IncrementalGraphIndex only
    reparses changed files. The context also gives all built-in engines one graph view.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.expanduser().resolve()
        self._index = IncrementalGraphIndex(self.project_root)
        self._lock = threading.RLock()
        self._snapshot: RepositorySnapshot | None = None
        self._generation = 0

    def refresh(self) -> RepositorySnapshot:
        with self._lock:
            graph, stats = self._index.refresh()
            self._generation += 1
            self._snapshot = RepositorySnapshot(graph, stats, self._generation)
            return self._snapshot

    def graph(self) -> ProjectGraph:
        return self.refresh().graph

    def symbols(self) -> tuple[GraphNode, ...]:
        graph = self.graph()
        return tuple(
            node
            for node in graph.nodes
            if node.kind not in {"file", "module", "reference"}
        )

    @property
    def snapshot(self) -> RepositorySnapshot | None:
        with self._lock:
            return self._snapshot
