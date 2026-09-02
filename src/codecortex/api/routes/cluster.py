"""Distributed cluster control routes."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from codecortex.distributed.cluster import ClusterCoordinator


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException

    cluster = ClusterCoordinator(ctx.state_root / "distributed")

    @app.get(f"{ctx.prefix}/cluster")
    def cluster_status(_actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        return asdict(cluster.status())

    @app.get(f"{ctx.prefix}/workers")
    def workers(active_within_seconds: float | None = None, _actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        items = cluster.workers.workers(active_within_seconds=active_within_seconds)
        return {"workers": [asdict(item) for item in items]}

    @app.get(f"{ctx.prefix}/cluster/tasks")
    def tasks(status: str | None = None, limit: int = 200, _actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        if status is not None and status not in {"queued", "leased", "completed", "failed"}:
            raise HTTPException(status_code=400, detail="invalid task status")
        items = cluster.workers.list_tasks(status, max(1, min(limit, 2000)))
        payload = []
        for item in items:
            row = asdict(item)
            row.pop("lease_token", None)
            payload.append(row)
        return {"tasks": payload}

    @app.post(f"{ctx.prefix}/cluster/requeue-expired")
    def requeue_expired(actor: str = Depends(ctx.principal)) -> dict[str, int]:
        count = cluster.workers.requeue_expired()
        ctx.events.publish("cluster.leases.requeued", {"count": count, "actor": actor})
        return {"requeued": count}
