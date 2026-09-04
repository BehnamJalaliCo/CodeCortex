"""Team memory center routes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from codecortex.memory.team_store import RevisionConflict, TeamMemoryStore

if TYPE_CHECKING:
    from fastapi import FastAPI



class MemoryWrite(BaseModel):
    namespace: str = Field(default="project", min_length=1, max_length=200)
    key: str = Field(min_length=1, max_length=500)
    value: str = Field(max_length=200000)
    source: str = Field(default="console", max_length=100)
    tags: list[str] = Field(default_factory=list)
    expected_revision: int | None = Field(default=None, ge=0)


def mount(app: FastAPI, ctx: Any) -> None:
    from fastapi import Depends, HTTPException

    def store(repository_id: str) -> TeamMemoryStore:
        item = ctx.database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return TeamMemoryStore(Path(item.root) / ".codecortex" / "memory" / "team.db")

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/memory")
    def search_memory(
        repository_id: str,
        namespace: str = "project",
        query: str = "",
        limit: int = 50,
        _actor: str = Depends(ctx.principal),
    ) -> dict[str, Any]:
        entries = store(repository_id).search_entries(namespace, query, max(1, min(limit, 200)))
        return {"entries": [asdict(entry) for entry in entries]}

    @app.put(f"{ctx.prefix}/repositories/{{repository_id}}/memory")
    def put_memory(
        repository_id: str, payload: MemoryWrite, actor: str = Depends(ctx.principal)
    ) -> dict[str, Any]:
        try:
            entry = store(repository_id).put_entry(
                payload.namespace,
                payload.key,
                payload.value,
                actor=actor,
                source=payload.source,
                tags=tuple(payload.tags),
                expected_revision=payload.expected_revision,
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        ctx.events.publish(
            "memory.updated",
            {
                "repository_id": repository_id,
                "namespace": payload.namespace,
                "key": payload.key,
                "revision": entry.revision,
                "actor": actor,
            },
        )
        return asdict(entry)

    @app.get(f"{ctx.prefix}/repositories/{{repository_id}}/memory/history")
    def memory_history(
        repository_id: str,
        namespace: str,
        key: str,
        limit: int = 50,
        _actor: str = Depends(ctx.principal),
    ) -> dict[str, Any]:
        return {
            "entries": [
                asdict(entry)
                for entry in store(repository_id).history(namespace, key, max(1, min(limit, 200)))
            ]
        }
