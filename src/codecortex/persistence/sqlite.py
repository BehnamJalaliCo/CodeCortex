"""Versioned zero-service SQLite persistence for platform control-plane data."""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA_VERSION = 2


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    workspace_id: str
    name: str
    created_at: str


@dataclass(frozen=True, slots=True)
class RepositoryRecord:
    repository_id: str
    workspace: str
    name: str
    root: str
    created_at: str


class PlatformDatabase:
    def __init__(self, path: Path, *, repository_root: Path | None = None) -> None:
        self.path = path.expanduser().resolve()
        self.repository_root = (repository_root or Path.cwd()).expanduser().resolve()
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
                current = 1
            if current < 2:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS platform_workspaces (
                        workspace_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                names = connection.execute(
                    "SELECT DISTINCT workspace FROM platform_repositories ORDER BY workspace"
                ).fetchall()
                for item in names:
                    connection.execute(
                        "INSERT OR IGNORE INTO platform_workspaces(workspace_id, name, created_at) VALUES (?, ?, ?)",
                        (uuid.uuid4().hex, str(item["workspace"]), _now()),
                    )
                connection.execute("UPDATE schema_version SET version = 2")

    @property
    def schema_version(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return 0 if row is None else int(row["version"])

    def create_workspace(self, name: str, *, workspace_id: str | None = None) -> WorkspaceRecord:
        normalized = name.strip()
        if not normalized:
            raise ValueError("workspace name is required")
        identifier = workspace_id or uuid.uuid4().hex
        created_at = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO platform_workspaces(workspace_id, name, created_at) VALUES (?, ?, ?)",
                (identifier, normalized, created_at),
            )
            row = connection.execute(
                "SELECT * FROM platform_workspaces WHERE name = ?", (normalized,)
            ).fetchone()
        assert row is not None
        return self._workspace(row)

    def workspaces(self) -> tuple[WorkspaceRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM platform_workspaces ORDER BY name").fetchall()
        return tuple(self._workspace(row) for row in rows)

    def remove_workspace(self, workspace_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT name FROM platform_workspaces WHERE workspace_id = ?", (workspace_id,)
            ).fetchone()
            if row is None:
                return False
            count = connection.execute(
                "SELECT COUNT(*) AS total FROM platform_repositories WHERE workspace = ?",
                (str(row["name"]),),
            ).fetchone()
            if count is not None and int(count["total"]) > 0:
                raise ValueError("workspace still contains repositories")
            cursor = connection.execute(
                "DELETE FROM platform_workspaces WHERE workspace_id = ?", (workspace_id,)
            )
        return cursor.rowcount > 0

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
        self.create_workspace(workspace)
        safe_root = os.path.realpath(os.fspath(self.repository_root))
        candidate = os.path.realpath(os.path.join(safe_root, os.fspath(root)))
        safe_prefix = safe_root if safe_root.endswith(os.sep) else safe_root + os.sep
        if candidate != safe_root and not candidate.startswith(safe_prefix):
            raise ValueError(f"repository root must be within {safe_root}")
        resolved = Path(candidate)
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
                (identifier, workspace.strip(), name.strip(), str(resolved), created_at),
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
    def _workspace(row: sqlite3.Row) -> WorkspaceRecord:
        return WorkspaceRecord(
            workspace_id=str(row["workspace_id"]),
            name=str(row["name"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _repository(row: sqlite3.Row) -> RepositoryRecord:
        return RepositoryRecord(
            repository_id=str(row["repository_id"]),
            workspace=str(row["workspace"]),
            name=str(row["name"]),
            root=str(row["root"]),
            created_at=str(row["created_at"]),
        )
