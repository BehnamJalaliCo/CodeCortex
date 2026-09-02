"""Small platform-level audit adapter shared by mutation surfaces."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from codecortex.distributed.organization import AuditEvent, AuditLog


class PlatformAudit:
    def __init__(self, state_root: Path) -> None:
        self.log = AuditLog(state_root / "distributed" / "organization.db")

    def record(self, actor: str, action: str, resource: str, *, workspace: str | None = None, outcome: str = "success", metadata: dict[str, Any] | None = None) -> AuditEvent:
        return self.log.record("platform", actor, action, resource, workspace=workspace, outcome=outcome, metadata=metadata or {})
