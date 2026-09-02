"""Versioned zero-service SQLite persistence for platform control-plane data."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class RepositoryRecord:
    repository_id: str
    workspace: str
    name: str
    root: str
    created_at: str


class PlatformDatabase:
    """Local control-plane store with explicit schema versioning.

    Runtime/index data remains in its specialized stores; this database owns platform
    metadata such as repository registration and later web-control-plane records.
    """

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            current = 0 if row is None else int(row["version"])
            if current > _SCHEMA_VERSION:
                raise RuntimeError(
                    f"platform database schema {current} is newer than supported {_SCHEMA_VERSION}"
                )
            if current < 1:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS platform_repositories (
                        repository_id TEXT PRIMARY KEY,
                        workspace TEXT NOT NULL,
                        name TEXT NOT NULL,
                        root TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        UNIQUE(workspace, name)
                    );
                    CREATE INDEX IF NOT EXISTS idx_platform_repositories_workspace
                        ON platform_repositories(workspace, name);
                    """
                )
                connection.execute("DELETE FROM schema_version")
                connection.execute("INSERT INTO schema_version(version) VALUES (1)")

    @property
    def schema_version(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return 0 if row is None else int(row["version"])

    def register_repository(
        self,
        workspace: str,
        name: str,
        root: Path | str,
        *,
        repository_id: str | None = None,
    ) -> RepositoryRecord:
        if not workspace.strip() or not name.strip():
            raise ValueError("workspace and repository name are required")
        resolved = Path(root).expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"repository root does not exist: {resolved}")
        identifier = repository_id or uuid.uuid4().hex
        created_at = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO platform_repositories(repository_id, workspace, name, root, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(root) DO UPDATE SET workspace=excluded.workspace, name=excluded.name
                """,
                (identifier, workspace, name, str(resolved), created_at),
            )
            row = connection.execute(
                "SELECT * FROM platform_repositories WHERE root = ?", (str(resolved),)
            ).fetchone()
        assert row is not None
        return self._repository(row)

    def repositories(self, workspace: str | None = None) -> tuple[RepositoryRecord, ...]:
        with self._connect() as connection:
            if workspace is None:
                rows = connection.execute(
                    "SELECT * FROM platform_repositories ORDER BY workspace, name"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM platform_repositories WHERE workspace = ? ORDER BY name",
                    (workspace,),
                ).fetchall()
        return tuple(self._repository(row) for row in rows)

    def repository(self, repository_id: str) -> RepositoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM platform_repositories WHERE repository_id = ?", (repository_id,)
            ).fetchone()
        return None if row is None else self._repository(row)

    def remove_repository(self, repository_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM platform_repositories WHERE repository_id = ?", (repository_id,)
            )
        return cursor.rowcount > 0

    @staticmethod
    def _repository(row: sqlite3.Row) -> RepositoryRecord:
        return RepositoryRecord(
            repository_id=str(row["repository_id"]),
            workspace=str(row["workspace"]),
            name=str(row["name"]),
            root=str(row["root"]),
            created_at=str(row["created_at"]),
        )
