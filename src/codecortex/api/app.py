"""Versioned REST API for CodeCortex."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codecortex.api.auth import ApiSecuritySettings, ApiTokenAuthenticator
from codecortex.persistence import PlatformDatabase
from codecortex.platform import PLATFORM_API_VERSION
from codecortex.projects import CortexRuntimeManager


def create_app(
    *,
    state_dir: Path | None = None,
    runtime_manager: CortexRuntimeManager | None = None,
    security: ApiSecuritySettings | None = None,
) -> Any:
    """Create the ASGI application with optional local or bearer-token authentication."""

    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("CodeCortex web API requires `pip install codecortex-context-engine[web]`") from exc

    from codecortex.api.schemas import HealthResponse, RepositoryCreate, RepositoryResponse

    root = (state_dir or Path.cwd() / ".codecortex" / "platform").expanduser().resolve()
    database = PlatformDatabase(root / "platform.db")
    runtimes = runtime_manager or CortexRuntimeManager()
    authenticator = ApiTokenAuthenticator(security)
    app = FastAPI(title="CodeCortex API", version=PLATFORM_API_VERSION)
    app.state.database = database
    app.state.runtime_manager = runtimes
    app.state.authenticator = authenticator

    prefix = f"/api/{PLATFORM_API_VERSION}"

    def principal(authorization: str | None = Header(default=None)) -> str:
        actor = authenticator.authenticate(authorization)
        if actor is None:
            raise HTTPException(status_code=401, detail="unauthorized", headers={"WWW-Authenticate": "Bearer"})
        return actor

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

    @app.get(f"{prefix}/session")
    def session(actor: str = Depends(principal)) -> dict[str, str]:
        return {"principal": actor}

    @app.get(f"{prefix}/repositories", response_model=list[RepositoryResponse])
    def repositories(
        workspace: str | None = None,
        _actor: str = Depends(principal),
    ) -> list[RepositoryResponse]:
        return [RepositoryResponse(**item.__dict__) for item in database.repositories(workspace)]

    @app.post(f"{prefix}/repositories", response_model=RepositoryResponse, status_code=201)
    def add_repository(
        payload: RepositoryCreate,
        _actor: str = Depends(principal),
    ) -> RepositoryResponse:
        try:
            item = database.register_repository(payload.workspace, payload.name, payload.root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RepositoryResponse(**item.__dict__)

    @app.get(f"{prefix}/repositories/{{repository_id}}", response_model=RepositoryResponse)
    def repository(
        repository_id: str,
        _actor: str = Depends(principal),
    ) -> RepositoryResponse:
        item = database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return RepositoryResponse(**item.__dict__)

    return app
