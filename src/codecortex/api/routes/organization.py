"""Organization, membership and workspace-policy administration routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from codecortex.distributed.organization import OrganizationPolicyStore

if TYPE_CHECKING:
    from fastapi import FastAPI



class OrganizationCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=200)


class MemberWrite(BaseModel):
    principal: str = Field(min_length=1, max_length=300)
    role: Literal["owner", "admin", "member", "viewer"]


class PolicyWrite(BaseModel):
    allowed_tools: list[str] = Field(default_factory=lambda: ["*"])
    max_context_tokens: int = Field(default=262144, ge=1, le=2_000_000)
    remote_access: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


def mount(app: FastAPI, ctx: Any) -> None:
    from fastapi import Depends, HTTPException

    store = OrganizationPolicyStore(ctx.state_root / "distributed" / "organization.db")

    def permission(exc: Exception) -> HTTPException:
        return HTTPException(status_code=403, detail=str(exc))

    @app.get(f"{ctx.prefix}/organizations")
    def organizations(_actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        with store.db.connect() as connection:
            rows = connection.execute(
                "SELECT slug, display_name, created_at FROM organizations ORDER BY slug"
            ).fetchall()
        return {"organizations": [dict(row) for row in rows]}

    @app.post(f"{ctx.prefix}/organizations", status_code=201)
    def create_organization(
        payload: OrganizationCreate, actor: str = Depends(ctx.principal)
    ) -> dict[str, str]:
        try:
            store.create_organization(payload.slug, payload.display_name, owner=actor)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"slug": payload.slug, "display_name": payload.display_name, "owner": actor}

    @app.get(f"{ctx.prefix}/organizations/{{organization}}/members")
    def members(organization: str, actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        try:
            store.require_role(organization, actor, "viewer")
        except PermissionError as exc:
            raise permission(exc) from exc
        with store.db.connect() as connection:
            rows = connection.execute(
                "SELECT principal, role FROM organization_members WHERE organization = ? ORDER BY principal",
                (organization,),
            ).fetchall()
        return {"members": [dict(row) for row in rows]}

    @app.put(f"{ctx.prefix}/organizations/{{organization}}/members")
    def set_member(
        organization: str, payload: MemberWrite, actor: str = Depends(ctx.principal)
    ) -> dict[str, str]:
        try:
            store.set_member(organization, actor, payload.principal, payload.role)
        except PermissionError as exc:
            raise permission(exc) from exc
        return {"principal": payload.principal, "role": payload.role}

    @app.get(f"{ctx.prefix}/organizations/{{organization}}/workspaces/{{workspace}}/policy")
    def get_policy(
        organization: str, workspace: str, actor: str = Depends(ctx.principal)
    ) -> dict[str, Any]:
        try:
            store.require_role(organization, actor, "viewer")
        except PermissionError as exc:
            raise permission(exc) from exc
        policy = store.policy(organization, workspace)
        if policy is None:
            raise HTTPException(status_code=404, detail="workspace policy not found")
        return asdict(policy)

    @app.put(f"{ctx.prefix}/organizations/{{organization}}/workspaces/{{workspace}}/policy")
    def set_policy(
        organization: str, workspace: str, payload: PolicyWrite, actor: str = Depends(ctx.principal)
    ) -> dict[str, Any]:
        try:
            policy = store.set_policy(
                organization,
                actor,
                workspace,
                allowed_tools=tuple(payload.allowed_tools),
                max_context_tokens=payload.max_context_tokens,
                remote_access=payload.remote_access,
                metadata=payload.metadata,
            )
        except PermissionError as exc:
            raise permission(exc) from exc
        return asdict(policy)
