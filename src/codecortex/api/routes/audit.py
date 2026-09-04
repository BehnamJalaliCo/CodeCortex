"""Audit center routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from codecortex.distributed.organization import AuditLog

if TYPE_CHECKING:
    from fastapi import FastAPI



def mount(app: FastAPI, ctx: Any) -> None:
    from fastapi import Depends

    log = AuditLog(ctx.state_root / "distributed" / "organization.db")

    @app.get(f"{ctx.prefix}/audit")
    def audit_events(
        organization: str = "platform",
        workspace: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        limit: int = 200,
        _principal: str = Depends(ctx.principal),
    ) -> dict[str, Any]:
        rows = log.query(
            organization, workspace=workspace, actor=actor, limit=max(1, min(limit, 2000))
        )
        if action:
            rows = [row for row in rows if row.action == action]
        if outcome:
            rows = [row for row in rows if row.outcome == outcome]
        return {"events": [asdict(row) for row in rows]}

    @app.post(f"{ctx.prefix}/audit/prune")
    def prune_audit(actor: str = Depends(ctx.principal)) -> dict[str, int]:
        removed = log.prune()
        log.record("platform", actor, "audit.prune", "audit-log", metadata={"removed": removed})
        return {"removed": removed}
