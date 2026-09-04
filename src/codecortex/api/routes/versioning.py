"""API compatibility discovery route."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from codecortex.api.versioning import version_manifest

if TYPE_CHECKING:
    from fastapi import FastAPI



def mount(app: FastAPI, ctx: Any) -> None:
    from fastapi import Depends

    @app.get(f"{ctx.prefix}/api-versions")
    def api_versions(_actor: str = Depends(ctx.principal)) -> dict[str, object]:
        return version_manifest()
