"""Durable multi-node indexing and retrieval worker coordination."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

TaskStatus = Literal["queued", "leased", "completed", "failed"]


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None = None) -> str:
    return (value or _now_dt()).isoformat()


@dataclass(frozen=True, slots=True)
class WorkerInfo:
    node_id: str
    capabilities: tuple[str, ...]
    metadata: dict[str, object]
    last_seen: str


@dataclass(frozen=True, slots=True)
class DistributedTask:
    task_id: str
    kind: str
    payload: dict[str, object]
    required_capabilities: tuple[str, ...]
    status: TaskStatus
    assigned_to: str | None
    lease_expires_at: str | None
    attempts: int
    created_at: str
    updated_at: str
    lease_token: str | None = None
    result: dict[str, object] | None = None
    error: str | None = None


class WorkerCoordinator:
    """SQLite-backed durable queue with leases, retries and fencing tokens."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workers (
                    node_id TEXT PRIMARY KEY,
                    capabilities TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    required_capabilities TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assigned_to TEXT,
                    lease_expires_at TEXT,
                    lease_token TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to, status);
                """
            )
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "lease_token" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN lease_token TEXT")

    def register_worker(
        self, node_id: str, capabilities: tuple[str, ...], metadata: dict[str, object] | None = None
    ) -> WorkerInfo:
        if not node_id.strip():
            raise ValueError("node_id is required")
        normalized = tuple(sorted({item.strip() for item in capabilities if item.strip()}))
        if not normalized:
            raise ValueError("at least one capability is required")
        last_seen = _iso()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO workers(node_id, capabilities, metadata, last_seen) VALUES (?, ?, ?, ?) ON CONFLICT(node_id) DO UPDATE SET capabilities = excluded.capabilities, metadata = excluded.metadata, last_seen = excluded.last_seen",
                (
                    node_id,
                    json.dumps(normalized),
                    json.dumps(metadata or {}, sort_keys=True),
                    last_seen,
                ),
            )
        return WorkerInfo(node_id, normalized, metadata or {}, last_seen)

    def heartbeat(self, node_id: str) -> WorkerInfo:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workers WHERE node_id = ?", (node_id,)
            ).fetchone()
            if row is None:
                raise KeyError(node_id)
            last_seen = _iso()
            connection.execute(
                "UPDATE workers SET last_seen = ? WHERE node_id = ?", (last_seen, node_id)
            )
        return WorkerInfo(
            node_id, tuple(json.loads(row["capabilities"])), json.loads(row["metadata"]), last_seen
        )

    def workers(self, *, active_within_seconds: float | None = None) -> list[WorkerInfo]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM workers ORDER BY node_id").fetchall()
        items = [self._row_to_worker(row) for row in rows]
        if active_within_seconds is None:
            return items
        threshold = _now_dt() - timedelta(seconds=max(0.0, active_within_seconds))
        return [item for item in items if datetime.fromisoformat(item.last_seen) >= threshold]

    def enqueue(
        self,
        kind: str,
        payload: dict[str, object],
        *,
        required_capabilities: tuple[str, ...] = (),
        task_id: str | None = None,
    ) -> DistributedTask:
        if not kind.strip():
            raise ValueError("kind is required")
        task_id = task_id or uuid.uuid4().hex
        capabilities = tuple(sorted({item for item in required_capabilities if item}))
        created_at = _iso()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tasks(task_id, kind, payload, required_capabilities, status, assigned_to, lease_expires_at, lease_token, attempts, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', NULL, NULL, NULL, 0, ?, ?)",
                (
                    task_id,
                    kind,
                    json.dumps(payload, sort_keys=True),
                    json.dumps(capabilities),
                    created_at,
                    created_at,
                ),
            )
        task = self.get_task(task_id)
        assert task is not None
        return task

    def claim(self, node_id: str, *, lease_seconds: float = 60.0) -> DistributedTask | None:
        worker = self.heartbeat(node_id)
        self.requeue_expired()
        expires = _iso(_now_dt() + timedelta(seconds=max(1.0, lease_seconds)))
        now = _iso()
        lease_token = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM tasks WHERE status = 'queued' ORDER BY created_at, task_id"
            ).fetchall()
            available = set(worker.capabilities)
            selected = next(
                (
                    row
                    for row in rows
                    if set(json.loads(row["required_capabilities"])).issubset(available)
                ),
                None,
            )
            if selected is None:
                return None
            task_id = str(selected["task_id"])
            cursor = connection.execute(
                "UPDATE tasks SET status = 'leased', assigned_to = ?, lease_expires_at = ?, lease_token = ?, attempts = attempts + 1, updated_at = ?, error = NULL WHERE task_id = ? AND status = 'queued'",
                (node_id, expires, lease_token, now, task_id),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_task(task_id)

    def renew_lease(
        self,
        task_id: str,
        node_id: str,
        *,
        lease_seconds: float = 60.0,
        lease_token: str | None = None,
    ) -> None:
        expires = _iso(_now_dt() + timedelta(seconds=max(1.0, lease_seconds)))
        with self._connect() as connection:
            if lease_token is None:
                cursor = connection.execute(
                    "UPDATE tasks SET lease_expires_at = ?, updated_at = ? WHERE task_id = ? AND status = 'leased' AND assigned_to = ?",
                    (expires, _iso(), task_id, node_id),
                )
            else:
                cursor = connection.execute(
                    "UPDATE tasks SET lease_expires_at = ?, updated_at = ? WHERE task_id = ? AND status = 'leased' AND assigned_to = ? AND lease_token = ?",
                    (expires, _iso(), task_id, node_id, lease_token),
                )
        if cursor.rowcount != 1:
            raise RuntimeError("task lease does not match this worker/fencing token")

    def complete(
        self,
        task_id: str,
        node_id: str,
        result: dict[str, object],
        *,
        lease_token: str | None = None,
    ) -> DistributedTask:
        return self._finish(
            task_id, node_id, "completed", result=result, error=None, lease_token=lease_token
        )

    def fail(
        self, task_id: str, node_id: str, error: str, *, lease_token: str | None = None
    ) -> DistributedTask:
        return self._finish(
            task_id, node_id, "failed", result=None, error=error, lease_token=lease_token
        )

    def _finish(
        self,
        task_id: str,
        node_id: str,
        status: TaskStatus,
        *,
        result: dict[str, object] | None,
        error: str | None,
        lease_token: str | None,
    ) -> DistributedTask:
        with self._connect() as connection:
            if lease_token is None:
                cursor = connection.execute(
                    "UPDATE tasks SET status = ?, result = ?, error = ?, lease_expires_at = NULL, lease_token = NULL, updated_at = ? WHERE task_id = ? AND status = 'leased' AND assigned_to = ?",
                    (
                        status,
                        None if result is None else json.dumps(result, sort_keys=True),
                        error,
                        _iso(),
                        task_id,
                        node_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    "UPDATE tasks SET status = ?, result = ?, error = ?, lease_expires_at = NULL, lease_token = NULL, updated_at = ? WHERE task_id = ? AND status = 'leased' AND assigned_to = ? AND lease_token = ?",
                    (
                        status,
                        None if result is None else json.dumps(result, sort_keys=True),
                        error,
                        _iso(),
                        task_id,
                        node_id,
                        lease_token,
                    ),
                )
        if cursor.rowcount != 1:
            raise RuntimeError("task lease does not match this worker/fencing token")
        task = self.get_task(task_id)
        assert task is not None
        return task

    def requeue_expired(self) -> int:
        now = _iso()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET status = 'queued', assigned_to = NULL, lease_expires_at = NULL, lease_token = NULL, updated_at = ? WHERE status = 'leased' AND lease_expires_at < ?",
                (now, now),
            )
        return int(cursor.rowcount)

    def get_task(self, task_id: str) -> DistributedTask | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def list_tasks(
        self, status: TaskStatus | None = None, limit: int = 100
    ) -> list[DistributedTask]:
        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (max(1, limit),)
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, max(1, limit)),
                ).fetchall()
        return [self._row_to_task(row) for row in rows]

    @staticmethod
    def _row_to_worker(row: sqlite3.Row) -> WorkerInfo:
        return WorkerInfo(
            str(row["node_id"]),
            tuple(str(item) for item in json.loads(row["capabilities"])),
            dict(json.loads(row["metadata"])),
            str(row["last_seen"]),
        )

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> DistributedTask:
        result = None if row["result"] is None else dict(json.loads(row["result"]))
        return DistributedTask(
            task_id=str(row["task_id"]),
            kind=str(row["kind"]),
            payload=dict(json.loads(row["payload"])),
            required_capabilities=tuple(
                str(item) for item in json.loads(row["required_capabilities"])
            ),
            status=str(row["status"]),
            assigned_to=None if row["assigned_to"] is None else str(row["assigned_to"]),
            lease_expires_at=None
            if row["lease_expires_at"] is None
            else str(row["lease_expires_at"]),
            attempts=int(row["attempts"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            lease_token=None if row["lease_token"] is None else str(row["lease_token"]),
            result=result,
            error=None if row["error"] is None else str(row["error"]),
        )
