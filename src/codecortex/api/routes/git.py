"""Git intelligence routes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from codecortex.git_intelligence import GitIntelligence


def mount(app: Any, ctx: Any) -> None:
    from fastapi import Depends, HTTPException

    def root(repository_id: str) -> Path:
        item = ctx.database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return Path(item.root)

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/git")
    def git_report(
        repository_id: str, limit: int = 300, _actor: str = Depends(ctx.principal)
    ) -> dict[str, Any]:
        report = GitIntelligence(root(repository_id)).analyze(max(1, min(limit, 2000)))
        return {
            "commits": report.commits,
            "hot_files": [asdict(item) for item in report.hot_files],
            "co_changes": [asdict(item) for item in report.co_changes],
            "authors": [asdict(item) for item in report.authors],
            "recent_files": list(report.recent_files),
        }

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/git/files/history")
    def file_history(
        repository_id: str, path: str, limit: int = 30, _actor: str = Depends(ctx.principal)
    ) -> dict[str, Any]:
        return {
            "path": path,
            "commits": GitIntelligence(root(repository_id)).file_history(
                path, max(1, min(limit, 100))
            ),
        }

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/git/symbol-history")
    def symbol_history(
        repository_id: str, path: str, start: int, end: int, _actor: str = Depends(ctx.principal)
    ) -> dict[str, Any]:
        try:
            report = GitIntelligence(root(repository_id)).symbol_history(path, start, end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "path": report.path,
            "start_line": report.start_line,
            "end_line": report.end_line,
            "commits": [asdict(item) for item in report.commits],
            "blame": [asdict(item) for item in report.blame],
            "owners": [asdict(item) for item in report.owners],
        }
