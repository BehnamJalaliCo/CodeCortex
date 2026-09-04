"""Persistent revisioned graph storage for distributed deployments."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph


class DistributedGraphStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS graph_revisions (
                    repository TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(repository, revision)
                );
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    repository TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(repository, revision, node_id)
                );
                CREATE TABLE IF NOT EXISTS graph_edges (
                    repository TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(repository, revision, source, target, kind)
                );
                CREATE INDEX IF NOT EXISTS idx_graph_revision_time
                    ON graph_revisions(repository, created_at DESC);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def replace(self, repository: str, revision: str, graph: ProjectGraph) -> None:
        if not repository.strip() or not revision.strip():
            raise ValueError("repository and revision are required")
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO graph_revisions(repository, revision, created_at) VALUES (?, ?, ?) ON CONFLICT(repository, revision) DO UPDATE SET created_at = excluded.created_at",
                (repository, revision, created_at),
            )
            connection.execute(
                "DELETE FROM graph_nodes WHERE repository = ? AND revision = ?",
                (repository, revision),
            )
            connection.execute(
                "DELETE FROM graph_edges WHERE repository = ? AND revision = ?",
                (repository, revision),
            )
            connection.executemany(
                "INSERT INTO graph_nodes(repository, revision, node_id, payload) VALUES (?, ?, ?, ?)",
                [
                    (
                        repository,
                        revision,
                        node.id,
                        json.dumps(
                            node.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
                        ),
                    )
                    for node in graph.nodes
                ],
            )
            connection.executemany(
                "INSERT INTO graph_edges(repository, revision, source, target, kind, payload) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        repository,
                        revision,
                        edge.source,
                        edge.target,
                        edge.kind,
                        json.dumps(
                            edge.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
                        ),
                    )
                    for edge in graph.edges
                ],
            )

    def latest_revision(self, repository: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision FROM graph_revisions WHERE repository = ? ORDER BY created_at DESC LIMIT 1",
                (repository,),
            ).fetchone()
        return None if row is None else str(row["revision"])

    def load(self, repository: str, revision: str | None = None) -> ProjectGraph:
        resolved = revision or self.latest_revision(repository)
        if resolved is None:
            return ProjectGraph()
        with self._connect() as connection:
            node_rows = connection.execute(
                "SELECT payload FROM graph_nodes WHERE repository = ? AND revision = ? ORDER BY node_id",
                (repository, resolved),
            ).fetchall()
            edge_rows = connection.execute(
                "SELECT payload FROM graph_edges WHERE repository = ? AND revision = ? ORDER BY source, kind, target",
                (repository, resolved),
            ).fetchall()
        return ProjectGraph(
            nodes=[GraphNode.model_validate(json.loads(row["payload"])) for row in node_rows],
            edges=[GraphEdge.model_validate(json.loads(row["payload"])) for row in edge_rows],
        )

    def repositories(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT repository FROM graph_revisions ORDER BY repository"
            ).fetchall()
        return tuple(str(row["repository"]) for row in rows)

    def prune(self, repository: str, *, keep: int = 3) -> int:
        bounded = max(1, keep)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT revision FROM graph_revisions WHERE repository = ? ORDER BY created_at DESC",
                (repository,),
            ).fetchall()
            doomed = [str(row["revision"]) for row in rows[bounded:]]
            for revision in doomed:
                connection.execute(
                    "DELETE FROM graph_nodes WHERE repository = ? AND revision = ?",
                    (repository, revision),
                )
                connection.execute(
                    "DELETE FROM graph_edges WHERE repository = ? AND revision = ?",
                    (repository, revision),
                )
                connection.execute(
                    "DELETE FROM graph_revisions WHERE repository = ? AND revision = ?",
                    (repository, revision),
                )
        return len(doomed)
