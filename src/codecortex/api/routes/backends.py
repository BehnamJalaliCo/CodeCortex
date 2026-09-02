"""Backend management routes."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from codecortex.backends.spec import BACKENDS


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException

    def manager(repository_id: str):
        item = ctx.database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return ctx.runtimes.get(item.root).backend_manager

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/backends")
    def list_backends(repository_id: str, _actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        mgr = manager(repository_id)
        rows = []
        for key, spec in BACKENDS.items():
            rows.append({
                **asdict(spec),
                "installed": mgr.is_installed(spec),
                "healthy": mgr.probe(spec, provision=False),
                "metadata": mgr.installation_metadata(spec),
            })
        return {"backends": rows}

    @app.post(f"{ctx.prefix}/repositories/{{repository_id}}/backends/{{backend_key}}/install")
    def install_backend(repository_id: str, backend_key: str, actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        spec = BACKENDS.get(backend_key)
        if spec is None:
            raise HTTPException(status_code=404, detail="backend not found")
        if not spec.configured:
            raise HTTPException(status_code=409, detail="backend is not configured")
        command = manager(repository_id).ensure(spec)
        ctx.events.publish("backend.installed", {"repository_id": repository_id, "backend": backend_key, "actor": actor})
        return {"backend": backend_key, "installed": True, "command": str(command)}

    @app.delete(f"{ctx.prefix}/repositories/{{repository_id}}/backends/{{backend_key}}")
    def remove_backend(repository_id: str, backend_key: str, actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        spec = BACKENDS.get(backend_key)
        if spec is None:
            raise HTTPException(status_code=404, detail="backend not found")
        manager(repository_id).remove(spec)
        ctx.events.publish("backend.removed", {"repository_id": repository_id, "backend": backend_key, "actor": actor})
        return {"backend": backend_key, "installed": False}
