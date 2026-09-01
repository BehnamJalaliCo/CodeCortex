"""Remote shared-memory synchronization with transactional conflict resolution."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

ClockRelation = Literal["before", "after", "equal", "concurrent"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def compare_clocks(left: dict[str, int], right: dict[str, int]) -> ClockRelation:
    nodes = set(left) | set(right)
    left_le = all(left.get(node, 0) <= right.get(node, 0) for node in nodes)
    right_le = all(right.get(node, 0) <= left.get(node, 0) for node in nodes)
    if left_le and right_le:
        return "equal"
    if left_le:
        return "before"
    if right_le:
        return "after"
    return "concurrent"


def merge_clocks(*clocks: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for clock in clocks:
        for node, counter in clock.items():
            merged[node] = max(merged.get(node, 0), int(counter))
    return merged


@dataclass(frozen=True, slots=True)
class MemoryMutation:
    namespace: str
    key: str
    value: str | None
    node_id: str
    clock: dict[str, int]
    updated_at: str
    tombstone: bool = False

    def to_dict(self) -> dict[str, object]:
        return {"namespace": self.namespace, "key": self.key, "value": self.value, "node_id": self.node_id, "clock": dict(self.clock), "updated_at": self.updated_at, "tombstone": self.tombstone}

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> MemoryMutation:
        raw_clock = payload.get("clock", {})
        if not isinstance(raw_clock, dict):
            raise ValueError("clock must be an object")
        return cls(namespace=str(payload["namespace"]), key=str(payload["key"]), value=None if payload.get("value") is None else str(payload["value"]), node_id=str(payload["node_id"]), clock={str(key): int(value) for key, value in raw_clock.items()}, updated_at=str(payload["updated_at"]), tombstone=bool(payload.get("tombstone", False)))


@dataclass(frozen=True, slots=True)
class SyncResult:
    applied: int = 0
    ignored: int = 0
    conflicts: int = 0


class SharedMemoryReplica:
    def __init__(self, path: Path, node_id: str) -> None:
        if not node_id.strip():
            raise ValueError("node_id is required")
        self.path = path
        self.node_id = node_id
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS shared_memory (namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT, node_id TEXT NOT NULL, clock TEXT NOT NULL, updated_at TEXT NOT NULL, tombstone INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(namespace, key));
                CREATE TABLE IF NOT EXISTS shared_memory_changes (sequence INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL, key TEXT NOT NULL, mutation TEXT NOT NULL, UNIQUE(namespace, key, mutation));
                CREATE INDEX IF NOT EXISTS idx_shared_memory_changes_sequence ON shared_memory_changes(sequence);
                """
            )

    def get(self, namespace: str, key: str) -> MemoryMutation | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM shared_memory WHERE namespace = ? AND key = ?", (namespace, key)).fetchone()
        return self._row_to_mutation(row) if row else None

    def value(self, namespace: str, key: str) -> str | None:
        mutation = self.get(namespace, key)
        return None if mutation is None or mutation.tombstone else mutation.value

    def put(self, namespace: str, key: str, value: str) -> MemoryMutation:
        return self._local_mutation(namespace, key, value, tombstone=False)

    def delete(self, namespace: str, key: str) -> MemoryMutation:
        return self._local_mutation(namespace, key, None, tombstone=True)

    def _local_mutation(self, namespace: str, key: str, value: str | None, *, tombstone: bool) -> MemoryMutation:
        if not namespace.strip() or not key.strip():
            raise ValueError("namespace and key are required")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM shared_memory WHERE namespace = ? AND key = ?", (namespace, key)).fetchone()
            current = self._row_to_mutation(row) if row else None
            clock = dict(current.clock) if current else {}
            clock[self.node_id] = clock.get(self.node_id, 0) + 1
            mutation = MemoryMutation(namespace, key, value, self.node_id, clock, _now(), tombstone)
            self._store(connection, mutation, record_change=True)
        return mutation

    def export(self, after_sequence: int = 0, limit: int = 1000) -> list[tuple[int, MemoryMutation]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT sequence, mutation FROM shared_memory_changes WHERE sequence > ? ORDER BY sequence ASC LIMIT ?", (max(0, after_sequence), max(1, limit))).fetchall()
        return [(int(row["sequence"]), MemoryMutation.from_dict(json.loads(row["mutation"]))) for row in rows]

    def apply(self, mutations: list[MemoryMutation]) -> SyncResult:
        applied = ignored = conflicts = 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for incoming in mutations:
                row = connection.execute("SELECT * FROM shared_memory WHERE namespace = ? AND key = ?", (incoming.namespace, incoming.key)).fetchone()
                current = self._row_to_mutation(row) if row else None
                if current is None:
                    self._store(connection, incoming, record_change=True)
                    applied += 1
                    continue
                relation = compare_clocks(current.clock, incoming.clock)
                if relation == "before":
                    self._store(connection, incoming, record_change=True)
                    applied += 1
                    continue
                if relation in {"after", "equal"}:
                    ignored += 1
                    continue
                conflicts += 1
                winner = self._resolve_concurrent(current, incoming)
                if winner != current:
                    self._store(connection, winner, record_change=True)
                    applied += 1
                else:
                    ignored += 1
        return SyncResult(applied, ignored, conflicts)

    @staticmethod
    def _resolve_concurrent(current: MemoryMutation, incoming: MemoryMutation) -> MemoryMutation:
        selected = incoming if (incoming.updated_at, incoming.node_id) > (current.updated_at, current.node_id) else current
        return MemoryMutation(namespace=selected.namespace, key=selected.key, value=selected.value, node_id=selected.node_id, clock=merge_clocks(current.clock, incoming.clock), updated_at=selected.updated_at, tombstone=selected.tombstone)

    def _store(self, connection: sqlite3.Connection, mutation: MemoryMutation, *, record_change: bool) -> None:
        encoded = json.dumps(mutation.to_dict(), sort_keys=True, separators=(",", ":"))
        connection.execute(
            "INSERT INTO shared_memory(namespace, key, value, node_id, clock, updated_at, tombstone) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(namespace, key) DO UPDATE SET value = excluded.value, node_id = excluded.node_id, clock = excluded.clock, updated_at = excluded.updated_at, tombstone = excluded.tombstone",
            (mutation.namespace, mutation.key, mutation.value, mutation.node_id, json.dumps(mutation.clock, sort_keys=True), mutation.updated_at, int(mutation.tombstone)),
        )
        if record_change:
            connection.execute("INSERT OR IGNORE INTO shared_memory_changes(namespace, key, mutation) VALUES (?, ?, ?)", (mutation.namespace, mutation.key, encoded))

    @staticmethod
    def _row_to_mutation(row: sqlite3.Row) -> MemoryMutation:
        return MemoryMutation(namespace=str(row["namespace"]), key=str(row["key"]), value=None if row["value"] is None else str(row["value"]), node_id=str(row["node_id"]), clock={str(key): int(value) for key, value in json.loads(row["clock"]).items()}, updated_at=str(row["updated_at"]), tombstone=bool(row["tombstone"]))
