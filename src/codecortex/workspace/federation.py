"""Federated multi-repository context and graph search."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.indexing.incremental_graph import IncrementalGraphIndex


@dataclass(frozen=True, slots=True)
class RepositoryDescriptor:
    name: str
    root: Path
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class FederatedHit:
    repository: str
    node: GraphNode
    score: float


class MultiRepositoryWorkspace:
    VERSION = 1

    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path
        self._repositories: dict[str, RepositoryDescriptor] = {}
        self._graphs: dict[str, ProjectGraph] = {}
        if state_path and state_path.exists():
            self.load()

    @property
    def repositories(self) -> tuple[RepositoryDescriptor, ...]:
        return tuple(self._repositories[name] for name in sorted(self._repositories))

    def add_repository(self, name: str, root: Path, weight: float = 1.0) -> None:
        if not name or ":" in name:
            raise ValueError("repository name must be non-empty and cannot contain ':'")
        resolved = root.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"repository root does not exist: {resolved}")
        self._repositories[name] = RepositoryDescriptor(name, resolved, max(0.01, weight))
        if self.state_path:
            self.save()

    def remove_repository(self, name: str) -> None:
        self._repositories.pop(name, None)
        self._graphs.pop(name, None)
        if self.state_path:
            self.save()

    def refresh(self) -> dict[str, ProjectGraph]:
        graphs: dict[str, ProjectGraph] = {}
        for descriptor in self.repositories:
            graph, _ = IncrementalGraphIndex(descriptor.root).refresh()
            graphs[descriptor.name] = graph
        self._graphs = graphs
        return dict(graphs)

    def search(self, query: str, limit: int = 40, per_repository: int = 20) -> list[FederatedHit]:
        if not self._graphs:
            self.refresh()
        query_terms = {
            term.lower().strip(".,:;()[]{}") for term in query.split() if len(term.strip()) > 2
        }
        hits: list[FederatedHit] = []
        for descriptor in self.repositories:
            graph = self._graphs.get(descriptor.name, ProjectGraph())
            for node in graph.search(query, per_repository):
                name = node.name.lower()
                path = (node.path or "").lower()
                lexical = sum(
                    5 if term == name else 3 if term in name else 1 if term in path else 0
                    for term in query_terms
                )
                structural = 1.10 if node.kind not in {"file", "module", "reference"} else 1.0
                hits.append(
                    FederatedHit(descriptor.name, node, lexical * descriptor.weight * structural)
                )
        hits.sort(key=lambda item: (-item.score, item.repository, item.node.id))
        return hits[: max(1, limit)]

    def federated_graph(self) -> ProjectGraph:
        if not self._graphs:
            self.refresh()
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        symbol_groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
        file_aliases: dict[str, list[tuple[str, str]]] = {}
        unresolved: list[tuple[str, GraphNode, str]] = []

        for repository, graph in self._graphs.items():
            for node in graph.nodes:
                namespaced = self._node_id(repository, node.id)
                metadata = dict(node.metadata)
                metadata["repository"] = repository
                nodes.append(node.model_copy(update={"id": namespaced, "metadata": metadata}))
                if node.kind not in {"file", "module", "reference"}:
                    symbol_groups.setdefault((node.kind, node.name.lower()), []).append(
                        (repository, namespaced)
                    )
                elif node.kind == "file" and node.path:
                    for alias in self._path_aliases(node.path):
                        file_aliases.setdefault(alias, []).append((repository, namespaced))
                elif node.kind in {"module", "reference"}:
                    unresolved.append((repository, node, namespaced))
            for edge in graph.edges:
                metadata = dict(edge.metadata)
                metadata["repository"] = repository
                edges.append(
                    edge.model_copy(
                        update={
                            "source": self._node_id(repository, edge.source),
                            "target": self._node_id(repository, edge.target),
                            "metadata": metadata,
                        }
                    )
                )

        for members in symbol_groups.values():
            if len({repository for repository, _ in members}) < 2:
                continue
            for index, (left_repo, left_id) in enumerate(members):
                for right_repo, right_id in members[index + 1 :]:
                    if left_repo == right_repo:
                        continue
                    edges.append(
                        GraphEdge(
                            source=left_id,
                            target=right_id,
                            kind="cross_repo_symbol",
                            metadata={
                                "confidence": 0.85,
                                "left_repository": left_repo,
                                "right_repository": right_repo,
                            },
                        )
                    )

        for source_repo, node, source_id in unresolved:
            normalized = self._normalize_dependency(node.name)
            candidates = file_aliases.get(normalized, [])
            confidence = 0.92
            if not candidates:
                candidates = [
                    item
                    for alias, values in file_aliases.items()
                    if alias.endswith(f"/{normalized}") or alias.endswith(f".{normalized}")
                    for item in values
                ]
                confidence = 0.76
            for target_repo, target_id in candidates:
                if target_repo == source_repo:
                    continue
                edges.append(
                    GraphEdge(
                        source=source_id,
                        target=target_id,
                        kind="cross_repo_dependency",
                        metadata={
                            "confidence": confidence,
                            "source_repository": source_repo,
                            "target_repository": target_repo,
                            "dependency": node.name,
                        },
                    )
                )
        unique = {
            (edge.source, edge.target, edge.kind): edge
            for edge in edges
            if edge.source != edge.target
        }
        return ProjectGraph(nodes=nodes, edges=list(unique.values()))

    @staticmethod
    def _normalize_dependency(value: str) -> str:
        normalized = value.strip().replace("\\", "/").lstrip("./")
        for suffix in (".py", ".js", ".ts", ".go", ".rs"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized.replace(".", "/").strip("/")

    @classmethod
    def _path_aliases(cls, path: str) -> set[str]:
        posix = PurePosixPath(path).as_posix()
        without_suffix = str(PurePosixPath(posix).with_suffix(""))
        normalized = cls._normalize_dependency(without_suffix)
        stem = PurePosixPath(without_suffix).name
        return {normalized, without_suffix, without_suffix.replace("/", "."), stem}

    def save(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "repositories": [
                {**asdict(item), "root": str(item.root)} for item in self.repositories
            ],
        }
        temp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.state_path)

    def load(self) -> None:
        if self.state_path is None:
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("version") != self.VERSION:
            return
        for item in payload.get("repositories", []):
            try:
                self.add_repository(
                    str(item["name"]), Path(str(item["root"])), float(item.get("weight", 1.0))
                )
            except (KeyError, TypeError, ValueError):
                continue

    @staticmethod
    def _node_id(repository: str, node_id: str) -> str:
        return f"repo:{repository}:{node_id}"
