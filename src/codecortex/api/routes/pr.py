"""Pull-request intelligence routes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.pr_intelligence import PRIntelligence


class PRAnalysisRequest(BaseModel):
    base_ref: str = Field(min_length=1, max_length=200)
    head_ref: str = Field(default="HEAD", min_length=1, max_length=200)


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException

    @app.post(f"{ctx.prefix}/repositories/{{repository_id}}/pr-analysis")
    def analyze_pr(
        repository_id: str, payload: PRAnalysisRequest, _actor: str = Depends(ctx.principal)
    ) -> dict[str, Any]:
        item = ctx.database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        root = Path(item.root)
        graph, _ = IncrementalGraphIndex(root).refresh()
        report = PRIntelligence(root, graph).analyze(payload.base_ref, payload.head_ref)
        return {
            "base_ref": report.base_ref,
            "head_ref": report.head_ref,
            "risk_score": report.risk_score,
            "risk_level": report.risk_level,
            "files": [asdict(file) for file in report.files],
            "symbols": [
                {
                    "node": symbol.node.model_dump(mode="json"),
                    "direct_change": symbol.direct_change,
                    "impact_risk": symbol.impact_risk,
                    "affected_nodes": symbol.affected_nodes,
                    "affected_tests": symbol.affected_tests,
                }
                for symbol in report.symbols
            ],
            "affected_tests": list(report.affected_tests),
        }
