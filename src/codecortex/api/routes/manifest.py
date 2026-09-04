"""Product capability discovery route."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from codecortex.platform_manifest import product_manifest

if TYPE_CHECKING:
    from fastapi import FastAPI



def mount(app: FastAPI, ctx: Any) -> None:
    from fastapi import Depends

    @app.get(f"{ctx.prefix}/platform/manifest")
    def manifest(_actor: str = Depends(ctx.principal)) -> dict[str, object]:
        return product_manifest()
