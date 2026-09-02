"""Durable control-plane notifications."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True, slots=True)
class Notification:
    notification_id: str
    kind: str
    severity: Severity
    title: str
    detail: str
    resource: str
    metadata: dict[str, Any]
    created_at: str
    acknowledged_at: str | None = None


class NotificationStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS notifications(
                notification_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                resource TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                acknowledged_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_time ON notifications(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_notifications_ack ON notifications(acknowledged_at, created_at DESC);
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def emit(
        self,
        kind: str,
        severity: Severity,
        title: str,
        detail: str,
        resource: str,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        item = Notification(
            uuid.uuid4().hex,
            kind,
            severity,
            title,
            detail,
            resource,
            metadata or {},
            datetime.now(UTC).isoformat(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO notifications VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    item.notification_id,
                    item.kind,
                    item.severity,
                    item.title,
                    item.detail,
                    item.resource,
                    json.dumps(item.metadata, sort_keys=True),
                    item.created_at,
                ),
            )
        return item

    def list(self, *, include_acknowledged: bool = False, limit: int = 200) -> list[Notification]:
        sql = (
            "SELECT * FROM notifications"
            + ("" if include_acknowledged else " WHERE acknowledged_at IS NULL")
            + " ORDER BY created_at DESC LIMIT ?"
        )
        with self._connect() as connection:
            rows = connection.execute(sql, (max(1, limit),)).fetchall()
        return [self._row(row) for row in rows]

    def acknowledge(self, notification_id: str) -> bool:
        when = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE notifications SET acknowledged_at = ? WHERE notification_id = ? AND acknowledged_at IS NULL",
                (when, notification_id),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _row(row: sqlite3.Row) -> Notification:
        return Notification(
            str(row["notification_id"]),
            str(row["kind"]),
            str(row["severity"]),
            str(row["title"]),
            str(row["detail"]),
            str(row["resource"]),
            dict(json.loads(row["metadata"])),
            str(row["created_at"]),
            None if row["acknowledged_at"] is None else str(row["acknowledged_at"]),
        )  # type: ignore[arg-type]

    @staticmethod
    def payload(item: Notification) -> dict[str, Any]:
        return asdict(item)
