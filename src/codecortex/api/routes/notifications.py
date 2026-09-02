"""Notification center routes and on-demand health scanner."""
from __future__ import annotations

from typing import Any

from codecortex.notifications import NotificationStore


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException
    store = NotificationStore(ctx.state_root / "notifications.db")

    @app.get(f"{ctx.prefix}/notifications")
    def notifications(include_acknowledged: bool = False, limit: int = 200, _actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        return {"notifications": [store.payload(item) for item in store.list(include_acknowledged=include_acknowledged, limit=max(1, min(limit, 2000)))]}

    @app.post(f"{ctx.prefix}/notifications/scan")
    def scan(actor: str = Depends(ctx.principal)) -> dict[str, int]:
        created = 0
        failed_jobs = [job for job in ctx.jobs.store.list(limit=500) if getattr(job.status, "value", job.status) == "failed"]
        if failed_jobs:
            store.emit("job.failure", "critical", "Background jobs failed", f"{len(failed_jobs)} failed job(s) need attention.", "jobs", {"count": len(failed_jobs)})
            created += 1
        unhealthy = []
        for repository in ctx.database.repositories():
            runtime = ctx.runtimes.get(repository.root)
            for key in runtime.active_backends:
                unhealthy.append((repository.repository_id, key)) if not runtime.backend_manager.probe(__import__('codecortex.backends.spec', fromlist=['BACKENDS']).BACKENDS[key], provision=False) else None
        if unhealthy:
            store.emit("backend.unhealthy", "warning", "Backend health degraded", f"{len(unhealthy)} active backend(s) are unhealthy.", "backends", {"backends": unhealthy})
            created += 1
        ctx.events.publish("notifications.scanned", {"created": created, "actor": actor})
        return {"created": created}

    @app.post(f"{ctx.prefix}/notifications/{{notification_id}}/acknowledge")
    def acknowledge(notification_id: str, actor: str = Depends(ctx.principal)) -> dict[str, bool]:
        if not store.acknowledge(notification_id):
            raise HTTPException(status_code=404, detail="notification not found or already acknowledged")
        ctx.events.publish("notification.acknowledged", {"notification_id": notification_id, "actor": actor})
        return {"acknowledged": True}
