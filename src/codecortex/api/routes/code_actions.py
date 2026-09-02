"""Approval-gated semantic code action routes."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from codecortex.application.safe_edit import SafeEditService
from codecortex.platform_audit import PlatformAudit


class EditRequest(BaseModel):
    operation: Literal["rename", "replace", "insert_before", "insert_after"]
    path: str = Field(min_length=1, max_length=2000)
    name_path: str = Field(min_length=1, max_length=2000)
    new_name: str = Field(default="", max_length=1000)
    body: str = Field(default="", max_length=500000)
    expected_file_sha256: str = Field(default="", max_length=64)
    approved: bool = False


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException
    audit = PlatformAudit(ctx.state_root)

    def service(repository_id: str) -> tuple[Any, SafeEditService]:
        item = ctx.database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return item, SafeEditService(ctx.runtimes.get(item.root))

    @app.post(f"{ctx.prefix}/repositories/{{repository_id}}/code-actions/preview")
    def preview(repository_id: str, payload: EditRequest, actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        item, edits = service(repository_id)
        try:
            result = edits.preview(payload.operation, payload.path, payload.name_path, new_name=payload.new_name, body=payload.body)
        except (ValueError, RuntimeError) as exc:
            audit.record(actor, "code.preview", payload.path, workspace=item.workspace, outcome="failed", metadata={"error": str(exc)[:300]})
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        audit.record(actor, "code.preview", payload.path, workspace=item.workspace, metadata={"operation": payload.operation, "name_path": payload.name_path})
        return result

    @app.post(f"{ctx.prefix}/repositories/{{repository_id}}/code-actions/apply")
    def apply(repository_id: str, payload: EditRequest, actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        item, edits = service(repository_id)
        try:
            result = edits.apply(payload.operation, payload.path, payload.name_path, expected_file_sha256=payload.expected_file_sha256, approved=payload.approved, new_name=payload.new_name, body=payload.body)
        except PermissionError as exc:
            audit.record(actor, "code.edit", payload.path, workspace=item.workspace, outcome="denied", metadata={"operation": payload.operation})
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            audit.record(actor, "code.edit", payload.path, workspace=item.workspace, outcome="failed", metadata={"operation": payload.operation, "error": str(exc)[:300]})
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        audit.record(actor, "code.edit", payload.path, workspace=item.workspace, metadata={"operation": payload.operation, "name_path": payload.name_path})
        ctx.events.publish("code.edited", {"repository_id": repository_id, "path": payload.path, "operation": payload.operation, "actor": actor})
        return result
