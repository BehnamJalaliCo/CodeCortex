"""Product capability discovery route."""
from __future__ import annotations
from typing import Any
from codecortex.platform_manifest import product_manifest


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends

    @app.get(f"{ctx.prefix}/platform/manifest")
    def manifest(_actor: str = Depends(ctx.principal)) -> dict[str, object]:
        return product_manifest()
