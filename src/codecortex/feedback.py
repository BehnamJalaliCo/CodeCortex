"""Durable agent outcome feedback used by adaptive routing."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from codecortex.core.models import Capability


@dataclass(frozen=True, slots=True)
class FeedbackSummary:
    capability: Capability
    samples: int
    success_rate: float
    average_latency_ms: float


class AgentFeedbackStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_feedback (
                    event_id TEXT PRIMARY KEY,
                    query_hash TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_capability_time
                    ON agent_feedback(capability, created_at DESC);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def record(
        self,
        query: str,
        capability: Capability,
        success: bool,
        latency_ms: float,
    ) -> None:
        query_hash = hashlib.blake2b(query.encode("utf-8"), digest_size=12).hexdigest()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO agent_feedback(event_id, query_hash, capability, success, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    query_hash,
                    capability.value,
                    int(success),
                    max(0.0, float(latency_ms)),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def summary(self, capability: Capability, limit: int = 200) -> FeedbackSummary | None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT success, latency_ms FROM agent_feedback WHERE capability = ? ORDER BY created_at DESC LIMIT ?",
                (capability.value, max(1, limit)),
            ).fetchall()
        if not rows:
            return None
        return FeedbackSummary(
            capability=capability,
            samples=len(rows),
            success_rate=sum(int(row["success"]) for row in rows) / len(rows),
            average_latency_ms=sum(float(row["latency_ms"]) for row in rows) / len(rows),
        )

    def routing_adjustment(self, capability: Capability) -> float:
        summary = self.summary(capability)
        if summary is None or summary.samples < 3:
            return 0.0
        quality = (summary.success_rate - 0.5) * 0.24
        latency_penalty = min(0.08, summary.average_latency_ms / 60_000.0 * 0.08)
        return max(-0.15, min(0.15, quality - latency_penalty))
