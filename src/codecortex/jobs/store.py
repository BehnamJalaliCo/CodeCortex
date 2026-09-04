"""Persistent job ledger for API and distributed operations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    kind: str
    status: JobStatus
    progress: float
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    actor: str
    workspace: str | None
    repository_id: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS platform_jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL,
                    payload TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    actor TEXT NOT NULL,
                    workspace TEXT,
                    repository_id TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_platform_jobs_created
                    ON platform_jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_platform_jobs_repo
                    ON platform_jobs(repository_id, created_at DESC);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def create(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        actor: str,
        workspace: str | None = None,
        repository_id: str | None = None,
    ) -> JobRecord:
        if not kind.strip() or not actor.strip():
            raise ValueError("job kind and actor are required")
        job_id = uuid.uuid4().hex
        created_at = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO platform_jobs(job_id, kind, status, progress, payload, actor, workspace, repository_id, created_at) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    kind,
                    JobStatus.QUEUED.value,
                    json.dumps(payload, sort_keys=True),
                    actor,
                    workspace,
                    repository_id,
                    created_at,
                ),
            )
        record = self.get(job_id)
        assert record is not None
        return record

    def start(self, job_id: str) -> JobRecord:
        return self._transition(job_id, JobStatus.RUNNING, started_at=_now())

    def progress(self, job_id: str, value: float) -> JobRecord:
        bounded = min(1.0, max(0.0, float(value)))
        with self._connect() as connection:
            connection.execute(
                "UPDATE platform_jobs SET progress = ? WHERE job_id = ? AND status = ?",
                (bounded, job_id, JobStatus.RUNNING.value),
            )
        record = self.get(job_id)
        if record is None:
            raise KeyError(job_id)
        return record

    def complete(self, job_id: str, result: dict[str, Any]) -> JobRecord:
        return self._transition(
            job_id,
            JobStatus.COMPLETED,
            progress=1.0,
            result=json.dumps(result, sort_keys=True),
            completed_at=_now(),
        )

    def fail(self, job_id: str, error: str) -> JobRecord:
        return self._transition(
            job_id,
            JobStatus.FAILED,
            error=error[:4000],
            completed_at=_now(),
        )

    def cancel(self, job_id: str) -> JobRecord:
        record = self.get(job_id)
        if record is None:
            raise KeyError(job_id)
        if record.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return record
        return self._transition(job_id, JobStatus.CANCELLED, completed_at=_now())

    def get(self, job_id: str) -> JobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM platform_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return None if row is None else self._row(row)

    def list(self, *, repository_id: str | None = None, limit: int = 100) -> tuple[JobRecord, ...]:
        bounded = min(1000, max(1, limit))
        with self._connect() as connection:
            if repository_id is None:
                rows = connection.execute(
                    "SELECT * FROM platform_jobs ORDER BY created_at DESC LIMIT ?", (bounded,)
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM platform_jobs WHERE repository_id = ? ORDER BY created_at DESC LIMIT ?",
                    (repository_id, bounded),
                ).fetchall()
        return tuple(self._row(row) for row in rows)

    def _transition(self, job_id: str, status: JobStatus, **fields: Any) -> JobRecord:
        assignments = ["status = ?"]
        values: list[Any] = [status.value]
        for key in ("progress", "result", "error", "started_at", "completed_at"):
            if key in fields:
                assignments.append(f"{key} = ?")
                values.append(fields[key])
        values.append(job_id)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE platform_jobs SET {', '.join(assignments)} WHERE job_id = ?",  # nosec B608 - fixed field list
                tuple(values),
            )
        if cursor.rowcount < 1:
            raise KeyError(job_id)
        record = self.get(job_id)
        assert record is not None
        return record

    @staticmethod
    def _row(row: sqlite3.Row) -> JobRecord:
        raw_result = None if row["result"] is None else json.loads(row["result"])
        return JobRecord(
            job_id=str(row["job_id"]),
            kind=str(row["kind"]),
            status=JobStatus(str(row["status"])),
            progress=float(row["progress"]),
            payload=dict(json.loads(row["payload"])),
            result=None if raw_result is None else dict(raw_result),
            error=None if row["error"] is None else str(row["error"]),
            actor=str(row["actor"]),
            workspace=None if row["workspace"] is None else str(row["workspace"]),
            repository_id=None if row["repository_id"] is None else str(row["repository_id"]),
            created_at=str(row["created_at"]),
            started_at=None if row["started_at"] is None else str(row["started_at"]),
            completed_at=None if row["completed_at"] is None else str(row["completed_at"]),
        )
