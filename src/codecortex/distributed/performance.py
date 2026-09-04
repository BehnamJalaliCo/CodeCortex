"""Persistent longitudinal performance history and trend analysis."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean


@dataclass(frozen=True, slots=True)
class PerformanceSnapshot:
    snapshot_id: str
    commit: str
    suite: str
    metrics: dict[str, float | int | None]
    recorded_at: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class MetricTrend:
    metric: str
    samples: int
    first: float | None
    latest: float | None
    minimum: float | None
    maximum: float | None
    average: float | None
    change_percent: float | None


class PerformanceHistoryStore:
    """SQLite performance ledger suitable for local use and CI artifact publication."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS performance_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    commit_sha TEXT NOT NULL,
                    suite TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_performance_suite_time
                    ON performance_snapshots(suite, recorded_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def record(
        self,
        commit: str,
        suite: str,
        metrics: dict[str, float | int | None],
        *,
        metadata: dict[str, object] | None = None,
        recorded_at: str | None = None,
        snapshot_id: str | None = None,
    ) -> PerformanceSnapshot:
        import uuid

        if not commit.strip() or not suite.strip():
            raise ValueError("commit and suite are required")
        normalized: dict[str, float | int | None] = {}
        for key, value in metrics.items():
            if value is not None and not isinstance(value, (int, float)):
                raise TypeError(f"metric {key!r} must be numeric or null")
            normalized[str(key)] = value
        timestamp = recorded_at or datetime.now(UTC).isoformat()
        identifier = snapshot_id or uuid.uuid4().hex
        snapshot = PerformanceSnapshot(
            identifier, commit, suite, normalized, timestamp, metadata or {}
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO performance_snapshots(
                    snapshot_id, commit_sha, suite, metrics, metadata, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    commit_sha = excluded.commit_sha,
                    suite = excluded.suite,
                    metrics = excluded.metrics,
                    metadata = excluded.metadata,
                    recorded_at = excluded.recorded_at
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.commit,
                    snapshot.suite,
                    json.dumps(snapshot.metrics, sort_keys=True),
                    json.dumps(snapshot.metadata, sort_keys=True),
                    snapshot.recorded_at,
                ),
            )
        return snapshot

    def history(self, suite: str | None = None, limit: int = 500) -> list[PerformanceSnapshot]:
        with self._connect() as connection:
            if suite is None:
                rows = connection.execute(
                    "SELECT * FROM performance_snapshots ORDER BY recorded_at DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM performance_snapshots WHERE suite = ?
                    ORDER BY recorded_at DESC LIMIT ?
                    """,
                    (suite, max(1, limit)),
                ).fetchall()
        return [self._row_to_snapshot(row) for row in rows]

    def trend(self, suite: str, metric: str, limit: int = 100) -> MetricTrend:
        snapshots = list(reversed(self.history(suite, limit)))
        values = [
            float(value)
            for snapshot in snapshots
            if (value := snapshot.metrics.get(metric)) is not None
        ]
        if not values:
            return MetricTrend(metric, 0, None, None, None, None, None, None)
        first = values[0]
        latest = values[-1]
        change = None
        if first != 0:
            change = ((latest - first) / abs(first)) * 100.0
        return MetricTrend(
            metric=metric,
            samples=len(values),
            first=first,
            latest=latest,
            minimum=min(values),
            maximum=max(values),
            average=mean(values),
            change_percent=change,
        )

    def export_json(self, path: Path, *, limit: int = 5000) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "snapshots": [asdict(item) for item in reversed(self.history(limit=limit))],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def import_json(self, path: Path) -> int:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshots = payload.get("snapshots", [])
        if not isinstance(snapshots, list):
            raise ValueError("performance history snapshots must be a list")
        imported = 0
        for raw in snapshots:
            if not isinstance(raw, dict):
                continue
            metrics = raw.get("metrics", {})
            metadata = raw.get("metadata", {})
            if not isinstance(metrics, dict) or not isinstance(metadata, dict):
                continue
            self.record(
                str(raw["commit"]),
                str(raw["suite"]),
                {str(key): value for key, value in metrics.items()},
                metadata={str(key): value for key, value in metadata.items()},
                recorded_at=str(raw["recorded_at"]),
                snapshot_id=str(raw["snapshot_id"]),
            )
            imported += 1
        return imported

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> PerformanceSnapshot:
        return PerformanceSnapshot(
            snapshot_id=str(row["snapshot_id"]),
            commit=str(row["commit_sha"]),
            suite=str(row["suite"]),
            metrics=dict(json.loads(row["metrics"])),
            recorded_at=str(row["recorded_at"]),
            metadata=dict(json.loads(row["metadata"])),
        )
