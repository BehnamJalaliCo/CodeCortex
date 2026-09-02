"""Coding-agent integration center routes."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from codecortex.integrations.agents import AgentConfigurator, AgentTarget
from codecortex.platform_audit import PlatformAudit


class ConfigureRequest(BaseModel):
    targets: list[AgentTarget] = []
    approved: bool = False


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException
    audit = PlatformAudit(ctx.state_root)

    def config(repository_id: str) -> tuple[Any, AgentConfigurator]:
        item = ctx.database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return item, AgentConfigurator(Path(item.root))

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/integrations")
    def integrations(repository_id: str, _actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        _, configurator = config(repository_id)
        detected = set(configurator.detect())
        return {"integrations": [{"target": target.value, "detected": target in detected} for target in AgentTarget]}

    @app.post(f"{ctx.prefix}/repositories/{{repository_id}}/integrations/preview")
    def preview(repository_id: str, payload: ConfigureRequest, _actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        _, configurator = config(repository_id)
        targets = tuple(payload.targets) if payload.targets else None
        return {"mutations": [asdict(item) | {"target": item.target.value, "path": str(item.path), "backup": str(item.backup) if item.backup else None} for item in configurator.configure(targets, dry_run=True)]}

    @app.post(f"{ctx.prefix}/repositories/{{repository_id}}/integrations/apply")
    def apply(repository_id: str, payload: ConfigureRequest, actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        item, configurator = config(repository_id)
        if not payload.approved:
            raise HTTPException(status_code=403, detail="explicit approval is required")
        targets = tuple(payload.targets) if payload.targets else None
        mutations = configurator.configure(targets, dry_run=False)
        audit.record(actor, "integrations.configure", repository_id, workspace=item.workspace, metadata={"targets": [mutation.target.value for mutation in mutations]})
        ctx.events.publish("integrations.configured", {"repository_id": repository_id, "actor": actor})
        return {"mutations": [asdict(mutation) | {"target": mutation.target.value, "path": str(mutation.path), "backup": str(mutation.backup) if mutation.backup else None} for mutation in mutations]}
