"""Organization-level workspace policy, roles and audit retention."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

Role = Literal["owner", "admin", "member", "viewer"]
_ROLE_RANK: dict[str, int] = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class WorkspacePolicy:
    organization: str
    workspace: str
    allowed_tools: tuple[str, ...]
    max_context_tokens: int
    remote_access: bool
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    organization: str
    workspace: str | None
    actor: str
    action: str
    resource: str
    outcome: str
    metadata: dict[str, object]
    created_at: str


class _Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection


class AuditLog:
    def __init__(self, path: Path, retention_days: int = 90) -> None:
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        self.db = _Database(path)
        self.retention_days = retention_days
        with self.db.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    organization TEXT NOT NULL,
                    workspace TEXT,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_org_time
                    ON audit_events(organization, created_at);
                """
            )

    def record(
        self,
        organization: str,
        actor: str,
        action: str,
        resource: str,
        *,
        workspace: str | None = None,
        outcome: str = "success",
        metadata: dict[str, object] | None = None,
        created_at: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            uuid.uuid4().hex,
            organization,
            workspace,
            actor,
            action,
            resource,
            outcome,
            metadata or {},
            created_at or _now(),
        )
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events(
                    event_id, organization, workspace, actor, action,
                    resource, outcome, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.organization,
                    event.workspace,
                    event.actor,
                    event.action,
                    event.resource,
                    event.outcome,
                    json.dumps(event.metadata, sort_keys=True),
                    event.created_at,
                ),
            )
        return event

    def query(
        self,
        organization: str,
        *,
        workspace: str | None = None,
        actor: str | None = None,
        limit: int = 500,
    ) -> list[AuditEvent]:
        clauses = ["organization = ?"]
        params: list[object] = [organization]
        if workspace is not None:
            clauses.append("workspace = ?")
            params.append(workspace)
        if actor is not None:
            clauses.append("actor = ?")
            params.append(actor)
        params.append(max(1, limit))
        sql = (
            "SELECT * FROM audit_events WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC LIMIT ?"
        )
        with self.db.connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [self._row(row) for row in rows]

    def prune(self, *, now: datetime | None = None) -> int:
        threshold = (now or datetime.now(UTC)) - timedelta(days=self.retention_days)
        with self.db.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM audit_events WHERE created_at < ?", (threshold.isoformat(),)
            )
        return int(cursor.rowcount)

    @staticmethod
    def _row(row: sqlite3.Row) -> AuditEvent:
        return AuditEvent(
            event_id=str(row["event_id"]),
            organization=str(row["organization"]),
            workspace=None if row["workspace"] is None else str(row["workspace"]),
            actor=str(row["actor"]),
            action=str(row["action"]),
            resource=str(row["resource"]),
            outcome=str(row["outcome"]),
            metadata=dict(json.loads(row["metadata"])),
            created_at=str(row["created_at"]),
        )


class OrganizationPolicyStore:
    """Durable organization membership, workspace and access-policy administration."""

    def __init__(self, path: Path, *, audit_retention_days: int = 90) -> None:
        self.db = _Database(path)
        self.audit = AuditLog(path, audit_retention_days)
        with self.db.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                    slug TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS organization_members (
                    organization TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    role TEXT NOT NULL,
                    PRIMARY KEY(organization, principal)
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    organization TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    project_root TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(organization, workspace)
                );
                CREATE TABLE IF NOT EXISTS workspace_policies (
                    organization TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    allowed_tools TEXT NOT NULL,
                    max_context_tokens INTEGER NOT NULL,
                    remote_access INTEGER NOT NULL,
                    metadata TEXT NOT NULL,
                    PRIMARY KEY(organization, workspace)
                );
                """
            )

    def create_organization(self, slug: str, display_name: str, *, owner: str) -> None:
        if not slug.strip() or not display_name.strip() or not owner.strip():
            raise ValueError("slug, display_name and owner are required")
        with self.db.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO organizations(slug, display_name, created_at) VALUES (?, ?, ?)",
                (slug, display_name, _now()),
            )
            connection.execute(
                """
                INSERT INTO organization_members(organization, principal, role)
                VALUES (?, ?, 'owner')
                ON CONFLICT(organization, principal) DO UPDATE SET role = 'owner'
                """,
                (slug, owner),
            )
        self.audit.record(slug, owner, "organization.create", slug)

    def set_member(self, organization: str, actor: str, principal: str, role: Role) -> None:
        self.require_role(organization, actor, "admin")
        if role not in _ROLE_RANK:
            raise ValueError(f"unknown role: {role}")
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO organization_members(organization, principal, role)
                VALUES (?, ?, ?)
                ON CONFLICT(organization, principal) DO UPDATE SET role = excluded.role
                """,
                (organization, principal, role),
            )
        self.audit.record(
            organization,
            actor,
            "member.set_role",
            principal,
            metadata={"role": role},
        )

    def role(self, organization: str, principal: str) -> Role | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT role FROM organization_members WHERE organization = ? AND principal = ?",
                (organization, principal),
            ).fetchone()
        return None if row is None else str(row["role"])  # type: ignore[return-value]

    def require_role(self, organization: str, principal: str, minimum: Role) -> None:
        role = self.role(organization, principal)
        if role is None or _ROLE_RANK[role] < _ROLE_RANK[minimum]:
            self.audit.record(
                organization,
                principal,
                "authorization.denied",
                minimum,
                outcome="denied",
            )
            raise PermissionError(f"{principal} requires role {minimum} or higher")

    def create_workspace(
        self,
        organization: str,
        actor: str,
        workspace: str,
        *,
        project_root: str | None = None,
    ) -> None:
        self.require_role(organization, actor, "admin")
        if not workspace.strip():
            raise ValueError("workspace is required")
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO workspaces(organization, workspace, project_root, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(organization, workspace) DO UPDATE SET
                    project_root = excluded.project_root
                """,
                (organization, workspace, project_root, _now()),
            )
        self.audit.record(
            organization, actor, "workspace.create", workspace, workspace=workspace
        )

    def set_policy(
        self,
        organization: str,
        actor: str,
        workspace: str,
        *,
        allowed_tools: tuple[str, ...] = ("*",),
        max_context_tokens: int = 262_144,
        remote_access: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> WorkspacePolicy:
        self.require_role(organization, actor, "admin")
        if max_context_tokens < 1:
            raise ValueError("max_context_tokens must be positive")
        tools = tuple(sorted({tool for tool in allowed_tools if tool}))
        policy = WorkspacePolicy(
            organization,
            workspace,
            tools,
            max_context_tokens,
            remote_access,
            metadata or {},
        )
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO workspace_policies(
                    organization, workspace, allowed_tools, max_context_tokens,
                    remote_access, metadata
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(organization, workspace) DO UPDATE SET
                    allowed_tools = excluded.allowed_tools,
                    max_context_tokens = excluded.max_context_tokens,
                    remote_access = excluded.remote_access,
                    metadata = excluded.metadata
                """,
                (
                    organization,
                    workspace,
                    json.dumps(tools),
                    max_context_tokens,
                    int(remote_access),
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
        self.audit.record(
            organization,
            actor,
            "workspace.policy.update",
            workspace,
            workspace=workspace,
            metadata={"remote_access": remote_access, "max_context_tokens": max_context_tokens},
        )
        return policy

    def policy(self, organization: str, workspace: str) -> WorkspacePolicy | None:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM workspace_policies
                WHERE organization = ? AND workspace = ?
                """,
                (organization, workspace),
            ).fetchone()
        if row is None:
            return None
        return WorkspacePolicy(
            organization=str(row["organization"]),
            workspace=str(row["workspace"]),
            allowed_tools=tuple(str(item) for item in json.loads(row["allowed_tools"])),
            max_context_tokens=int(row["max_context_tokens"]),
            remote_access=bool(row["remote_access"]),
            metadata=dict(json.loads(row["metadata"])),
        )

    def authorize_tool(
        self, organization: str, workspace: str, principal: str, tool: str, *, remote: bool
    ) -> bool:
        role = self.role(organization, principal)
        policy = self.policy(organization, workspace)
        allowed = bool(role and policy)
        if allowed and remote and not policy.remote_access:
            allowed = False
        if allowed and policy is not None:
            allowed = "*" in policy.allowed_tools or tool in policy.allowed_tools
        self.audit.record(
            organization,
            principal,
            "tool.authorize",
            tool,
            workspace=workspace,
            outcome="allowed" if allowed else "denied",
            metadata={"remote": remote},
        )
        return allowed
