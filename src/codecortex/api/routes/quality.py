"""Quality center routes."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from codecortex.evaluation.regression import BenchmarkHistory, RegressionGate


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException

    def history(repository_id: str) -> BenchmarkHistory:
        item = ctx.database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return BenchmarkHistory(Path(item.root) / ".codecortex" / "benchmarks" / "history.json")

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/quality")
    def quality(repository_id: str, _actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        snapshots = history(repository_id).load()
        latest = snapshots[-1] if snapshots else None
        gate = None
        if len(snapshots) >= 2:
            gate = RegressionGate().evaluate(snapshots[-1], snapshots[-2])
        return {
            "snapshots": [asdict(item) for item in snapshots[-30:]],
            "latest": asdict(latest) if latest else None,
            "gate": asdict(gate) if gate else None,
            "metric_state": "measured" if latest else "unavailable",
        }

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/quality/compare")
    def compare(repository_id: str, current: str, baseline: str, _actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        snapshots = {item.id: item for item in history(repository_id).load()}
        if current not in snapshots or baseline not in snapshots:
            raise HTTPException(status_code=404, detail="benchmark snapshot not found")
        return asdict(RegressionGate().evaluate(snapshots[current], snapshots[baseline]))
