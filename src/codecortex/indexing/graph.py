"""Typed project knowledge graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codecortex.state import AtomicJsonFile


class GraphNode(BaseModel):
    id: str
    kind: str
    name: str
    path: str | None = None
    line: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    kind: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> ProjectGraph:
        payload = AtomicJsonFile(path).read({})
        if not isinstance(payload, dict):
            return cls()
        try:
            return cls.model_validate(payload)
        except ValueError:
            return cls()

    def save(self, path: Path) -> None:
        AtomicJsonFile(path).write(self.model_dump(mode="json"))

    def search(self, query: str, limit: int = 40) -> list[GraphNode]:
        terms = {
            term.lower().strip(".,:;()[]{}") for term in query.split() if len(term.strip()) > 2
        }
        scored: list[tuple[int, GraphNode]] = []
        for node in self.nodes:
            name = node.name.lower()
            path = (node.path or "").lower()
            score = sum(
                5 if term == name else 3 if term in name else 1 if term in path else 0
                for term in terms
            )
            if score:
                scored.append((score, node))
        scored.sort(key=lambda item: (-item[0], item[1].kind, item[1].name))
        return [node for _, node in scored[: max(1, limit)]]

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for node in self.nodes:
            result[node.kind] = result.get(node.kind, 0) + 1
        return result

    def nodes_for_path(self, path: str) -> list[GraphNode]:
        return [node for node in self.nodes if node.path == path]
