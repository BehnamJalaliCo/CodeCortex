"""Performance and repository-scale routes."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codecortex.evaluation.scale import RepositoryScaleBenchmark
from codecortex.performance import PerformanceBudgets


class ScaleRequest(BaseModel):
    targets: list[int] = Field(default_factory=lambda: [100000, 1000000], min_length=1, max_length=8)


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException

    @app.get(f"{ctx.prefix}/performance/budgets")
    def budgets(_actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        return {"budgets": PerformanceBudgets().to_dict()}

    @app.post(f"{ctx.prefix}/repositories/{{repository_id}}/performance/scale", status_code=202)
    def scale(repository_id: str, payload: ScaleRequest, actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        item = ctx.database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        targets = tuple(sorted({value for value in payload.targets if value > 0}))
        if not targets:
            raise HTTPException(status_code=400, detail="at least one positive target is required")
        def operation() -> dict[str, Any]:
            report = RepositoryScaleBenchmark(targets).run(Path(item.root))
            return {"root": report.root, "observed_files": report.observed_files, "samples": [asdict(sample) for sample in report.samples]}
        job = ctx.jobs.submit("repository.scale", {"repository_id": repository_id, "targets": list(targets)}, operation, actor=actor, workspace=item.workspace, repository_id=repository_id)
        return {"job_id": job.job_id, "status": getattr(job.status, "value", job.status), "targets": list(targets)}
