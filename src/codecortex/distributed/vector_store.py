"""Persistent vector-store provider contract and a zero-service SQLite implementation."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse


@dataclass(frozen=True, slots=True)
class VectorMatch:
    key: str
    score: float
    payload: dict[str, object]


class PersistentVectorStore(Protocol):
    def upsert(
        self,
        namespace: str,
        key: str,
        vector: list[float],
        payload: dict[str, object] | None = None,
    ) -> None: ...

    def delete(self, namespace: str, key: str) -> bool: ...

    def search(
        self, namespace: str, vector: list[float], limit: int = 10
    ) -> list[VectorMatch]: ...

    def count(self, namespace: str) -> int: ...


class SQLiteVectorStore:
    """Persistent vector store for local or shared-volume deployments.

    It intentionally uses exact cosine search so the core stays dependency-free.
    Large installations can register a provider for pgvector, Qdrant, Milvus,
    Weaviate, or another persistent service without changing retrieval callers.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS vectors (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    vector TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, key)
                );
                CREATE INDEX IF NOT EXISTS idx_vectors_namespace ON vectors(namespace);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def upsert(
        self,
        namespace: str,
        key: str,
        vector: list[float],
        payload: dict[str, object] | None = None,
    ) -> None:
        normalized = _validate_vector(vector)
        if not namespace.strip() or not key.strip():
            raise ValueError("namespace and key are required")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO vectors(namespace, key, dimension, vector, payload, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, key) DO UPDATE SET
                    dimension = excluded.dimension,
                    vector = excluded.vector,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    namespace,
                    key,
                    len(normalized),
                    json.dumps(normalized, separators=(",", ":")),
                    json.dumps(payload or {}, sort_keys=True, separators=(",", ":")),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def delete(self, namespace: str, key: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM vectors WHERE namespace = ? AND key = ?", (namespace, key)
            )
        return cursor.rowcount > 0

    def count(self, namespace: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM vectors WHERE namespace = ?", (namespace,)
            ).fetchone()
        return int(row["total"] if row else 0)

    def search(
        self, namespace: str, vector: list[float], limit: int = 10
    ) -> list[VectorMatch]:
        query = _validate_vector(vector)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT key, dimension, vector, payload FROM vectors WHERE namespace = ?",
                (namespace,),
            ).fetchall()
        matches: list[VectorMatch] = []
        for row in rows:
            if int(row["dimension"]) != len(query):
                continue
            candidate = [float(value) for value in json.loads(row["vector"])]
            score = _cosine(query, candidate)
            payload = json.loads(row["payload"])
            if not isinstance(payload, dict):
                payload = {}
            matches.append(VectorMatch(str(row["key"]), score, payload))
        matches.sort(key=lambda item: (-item.score, item.key))
        return matches[: max(1, limit)]


ProviderFactory = Callable[[str], PersistentVectorStore]
_PROVIDERS: dict[str, ProviderFactory] = {}


def register_vector_store_provider(scheme: str, factory: ProviderFactory) -> None:
    """Register a persistent vector DB provider by URI scheme."""
    normalized = scheme.strip().lower()
    if not normalized or normalized == "sqlite":
        raise ValueError("provider scheme must be non-empty and cannot replace sqlite")
    _PROVIDERS[normalized] = factory


def open_vector_store(uri: str | Path) -> PersistentVectorStore:
    """Open a store from a filesystem path or provider URI.

    Examples: `/var/lib/cortex/vectors.db`, `sqlite:///tmp/vectors.db`, or a
    registered external provider URI such as `qdrant://cluster/collection`.
    """
    if isinstance(uri, Path):
        return SQLiteVectorStore(uri)
    parsed = urlparse(uri)
    if not parsed.scheme or (len(parsed.scheme) == 1 and parsed.path.startswith("\\")):
        return SQLiteVectorStore(Path(uri))
    scheme = parsed.scheme.lower()
    if scheme == "sqlite":
        raw_path = unquote(parsed.path)
        netloc = unquote(parsed.netloc)
        if netloc:
            if len(netloc) == 2 and netloc[0].isalpha() and netloc[1] == ":":
                raw_path = f"{netloc}{raw_path}"
            elif netloc != "localhost":
                raw_path = f"//{netloc}{raw_path}"
        if raw_path.startswith("/") and len(raw_path) >= 3:
            if raw_path[1].isalpha() and raw_path[2] == ":":
                raw_path = raw_path[1:]
        if not raw_path:
            raise ValueError("sqlite URI requires a path")
        return SQLiteVectorStore(Path(raw_path))
    factory = _PROVIDERS.get(scheme)
    if factory is None:
        raise ValueError(f"unknown vector store provider: {scheme}")
    return factory(uri)


def _validate_vector(vector: list[float]) -> list[float]:
    if not vector:
        raise ValueError("vector cannot be empty")
    values = [float(value) for value in vector]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("vector values must be finite")
    if not any(value != 0.0 for value in values):
        raise ValueError("vector cannot be all zeros")
    return values


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    denominator = left_norm * right_norm
    return dot / denominator if denominator else 0.0
