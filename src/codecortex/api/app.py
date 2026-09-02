"""Versioned REST API for CodeCortex."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codecortex.persistence import PlatformDatabase
from codecortex.platform import PLATFORM_API_VERSION
from codecortex.projects import CortexRuntimeManager


def create_app(
    *,
    state_dir: Path | None = None,
    runtime_manager: CortexRuntimeManager | None = None,
) -> Any:
    """Create the ASGI application.

    FastAPI is an optional web dependency so the core package remains local-first and
    dependency-light. Importing ``codecortex.api`` does not start a server.
    """

    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("CodeCortex web API requires `pip install codecortex-context-engine[web]`") from exc

    from codecortex.api.schemas import HealthResponse, RepositoryCreate, RepositoryResponse

    root = (state_dir or Path.cwd() / ".codecortex" / "platform").expanduser().resolve()
    database = PlatformDatabase(root / "platform.db")
    runtimes = runtime_manager or CortexRuntimeManager()
    app = FastAPI(title="CodeCortex API", version=PLATFORM_API_VERSION)
    app.state.database = database
    app.state.runtime_manager = runtimes

    prefix = f"/api/{PLATFORM_API_VERSION}"

    @app.get(f"{prefix}/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=PLATFORM_API_VERSION)

    @app.get(f"{prefix}/readiness", response_model=HealthResponse)
    def readiness() -> HealthResponse:
        _ = database.schema_version
        return HealthResponse(status="ready", version=PLATFORM_API_VERSION)

    @app.get(f"{prefix}/version", response_model=HealthResponse)
    def version() -> HealthResponse:
        return HealthResponse(status="ok", version=PLATFORM_API_VERSION)

    @app.get(f"{prefix}/repositories", response_model=list[RepositoryResponse])
    def repositories(workspace: str | None = None) -> list[RepositoryResponse]:
        return [RepositoryResponse(**item.__dict__) for item in database.repositories(workspace)]

    @app.post(f"{prefix}/repositories", response_model=RepositoryResponse, status_code=201)
    def add_repository(payload: RepositoryCreate) -> RepositoryResponse:
        try:
            item = database.register_repository(payload.workspace, payload.name, payload.root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RepositoryResponse(**item.__dict__)

    @app.get(f"{prefix}/repositories/{{repository_id}}", response_model=RepositoryResponse)
    def repository(repository_id: str) -> RepositoryResponse:
        item = database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return RepositoryResponse(**item.__dict__)

    return app
