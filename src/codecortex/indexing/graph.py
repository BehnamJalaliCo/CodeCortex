"""Typed project knowledge graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


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
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return cls()
        try:
            return cls.model_validate(payload)
        except ValueError:
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(path)

    def search(self, query: str, limit: int = 40) -> list[GraphNode]:
        terms = {
            term.lower().strip(".,:;()[]{}")
            for term in query.split()
            if len(term.strip()) > 2
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
        return [node for _, node in scored[:limit]]

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for node in self.nodes:
            result[node.kind] = result.get(node.kind, 0) + 1
        return result

    def nodes_for_path(self, path: str) -> list[GraphNode]:
        return [node for node in self.nodes if node.path == path]
