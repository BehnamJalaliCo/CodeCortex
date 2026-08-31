"""Concurrent shared team memory backed by SQLite."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from codecortex.core.contracts import MemoryStore


@dataclass(frozen=True, slots=True)
class TeamMemoryEntry:
    namespace: str
    key: str
    value: str
    revision: int
    actor: str
    source: str
    tags: tuple[str, ...]
    updated_at: str


class RevisionConflict(RuntimeError):
    pass


class TeamMemoryStore(MemoryStore):
    """Shared memory with revisions, audit history, and optimistic concurrency."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    source TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, key)
                );
                CREATE TABLE IF NOT EXISTS memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    source TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_namespace
                    ON memories(namespace);
                CREATE INDEX IF NOT EXISTS idx_history_key
                    ON memory_history(namespace, key, revision);
                """
            )

    async def put(self, namespace: str, key: str, value: str) -> None:
        self.put_entry(namespace, key, value)

    def put_entry(
        self,
        namespace: str,
        key: str,
        value: str,
        *,
        actor: str = "system",
        source: str = "manual",
        tags: tuple[str, ...] = (),
        expected_revision: int | None = None,
    ) -> TeamMemoryEntry:
        if not namespace.strip() or not key.strip():
            raise ValueError("namespace and key are required")
        now = datetime.now(UTC).isoformat()
        encoded_tags = json.dumps(sorted(set(tags)), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision FROM memories WHERE namespace = ? AND key = ?",
                (namespace, key),
            ).fetchone()
            current_revision = int(row["revision"]) if row else 0
            if expected_revision is not None and expected_revision != current_revision:
                raise RevisionConflict(
                    f"expected revision {expected_revision}, found {current_revision}"
                )
            revision = current_revision + 1
            connection.execute(
                """
                INSERT INTO memories(namespace, key, value, revision, actor, source, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, key) DO UPDATE SET
                    value = excluded.value,
                    revision = excluded.revision,
                    actor = excluded.actor,
                    source = excluded.source,
                    tags = excluded.tags,
                    updated_at = excluded.updated_at
                """,
                (namespace, key, value, revision, actor, source, encoded_tags, now),
            )
            connection.execute(
                """
                INSERT INTO memory_history(namespace, key, value, revision, actor, source, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (namespace, key, value, revision, actor, source, encoded_tags, now),
            )
        return TeamMemoryEntry(namespace, key, value, revision, actor, source, tags, now)

    async def get(self, namespace: str, key: str) -> str | None:
        entry = self.get_entry(namespace, key)
        return entry.value if entry else None

    def get_entry(self, namespace: str, key: str) -> TeamMemoryEntry | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE namespace = ? AND key = ?",
                (namespace, key),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    async def search(self, namespace: str, query: str, limit: int = 10) -> list[str]:
        return [entry.value for entry in self.search_entries(namespace, query, limit)]

    def search_entries(self, namespace: str, query: str, limit: int = 10) -> list[TeamMemoryEntry]:
        terms = [term.lower() for term in query.split() if term.strip()]
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memories WHERE namespace = ? ORDER BY updated_at DESC",
                (namespace,),
            ).fetchall()
        scored: list[tuple[int, TeamMemoryEntry]] = []
        for row in rows:
            entry = self._row_to_entry(row)
            haystack = f"{entry.key} {entry.value} {' '.join(entry.tags)}".lower()
            score = sum(3 if term in entry.key.lower() else 1 for term in terms if term in haystack)
            if score or not terms:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].updated_at), reverse=False)
        return [entry for _, entry in scored[: max(1, limit)]]

    def history(self, namespace: str, key: str, limit: int = 50) -> list[TeamMemoryEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT namespace, key, value, revision, actor, source, tags, updated_at
                FROM memory_history
                WHERE namespace = ? AND key = ?
                ORDER BY revision DESC
                LIMIT ?
                """,
                (namespace, key, max(1, limit)),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> TeamMemoryEntry:
        try:
            tags = tuple(str(item) for item in json.loads(row["tags"]))
        except (json.JSONDecodeError, TypeError):
            tags = ()
        return TeamMemoryEntry(
            namespace=str(row["namespace"]),
            key=str(row["key"]),
            value=str(row["value"]),
            revision=int(row["revision"]),
            actor=str(row["actor"]),
            source=str(row["source"]),
            tags=tags,
            updated_at=str(row["updated_at"]),
        )
