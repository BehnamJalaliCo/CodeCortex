"""Versioned REST API for CodeCortex."""

import asyncio
import json
import queue
from dataclasses import asdict
from pathlib import Path
from typing import Any

from codecortex.api.auth import ApiSecuritySettings, ApiTokenAuthenticator
from codecortex.application.service import CortexApplicationService
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.jobs import JobManager, JobStore
from codecortex.persistence import PlatformDatabase
from codecortex.platform import PLATFORM_API_VERSION
from codecortex.projects import CortexRuntimeManager
from codecortex.realtime import PlatformEventBus


def create_app(
    *,
    state_dir: Path | None = None,
    runtime_manager: CortexRuntimeManager | None = None,
    security: ApiSecuritySettings | None = None,
) -> Any:
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
        from fastapi.responses import StreamingResponse
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "CodeCortex web API requires `pip install codecortex-context-engine[web]`"
        ) from exc

    from codecortex.api.schemas import (
        HealthResponse,
        JobResponse,
        RepositoryCreate,
        RepositoryResponse,
        WorkspaceCreate,
        WorkspaceResponse,
    )

    root = (state_dir or Path.cwd() / ".codecortex" / "platform").expanduser().resolve()
    database = PlatformDatabase(root / "platform.db")
    events = PlatformEventBus()
    jobs = JobManager(JobStore(root / "jobs.db"), event_sink=events.publish)
    runtimes = runtime_manager or CortexRuntimeManager()
    authenticator = ApiTokenAuthenticator(security)
    app = FastAPI(title="CodeCortex API", version=PLATFORM_API_VERSION)
    from codecortex.api.hardening import install_api_hardening

    install_api_hardening(app)
    app.state.database = database
    app.state.events = events
    app.state.job_manager = jobs
    app.state.runtime_manager = runtimes
    app.state.authenticator = authenticator
    prefix = f"/api/{PLATFORM_API_VERSION}"

    def principal(authorization: str | None = Header(default=None)) -> str:
        actor = authenticator.authenticate(authorization)
        if actor is None:
            raise HTTPException(
                status_code=401, detail="unauthorized", headers={"WWW-Authenticate": "Bearer"}
            )
        return actor

    def job_response(job: Any) -> JobResponse:
        payload = asdict(job)
        payload["status"] = job.status.value
        return JobResponse(**payload)

    def registered_repository(repository_id: str):
        item = database.repository(repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return item

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

    @app.get(f"{prefix}/events")
    async def event_stream(_actor: str = Depends(principal)) -> StreamingResponse:
        subscriber = events.subscribe()

        async def stream():
            try:
                while True:
                    try:
                        event = await asyncio.to_thread(subscriber.get, True, 15.0)
                    except queue.Empty:
                        yield ": heartbeat\n\n"
                        continue
                    body = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {event.event_id}\nevent: {event.type}\ndata: {body}\n\n"
            finally:
                events.unsubscribe(subscriber)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.get(f"{prefix}/workspaces", response_model=list[WorkspaceResponse])
    def workspaces(_actor: str = Depends(principal)) -> list[WorkspaceResponse]:
        return [WorkspaceResponse(**item.__dict__) for item in database.workspaces()]

    @app.post(f"{prefix}/workspaces", response_model=WorkspaceResponse, status_code=201)
    def create_workspace(
        payload: WorkspaceCreate, _actor: str = Depends(principal)
    ) -> WorkspaceResponse:
        item = database.create_workspace(payload.name)
        events.publish("workspace.created", {"workspace_id": item.workspace_id, "name": item.name})
        return WorkspaceResponse(**item.__dict__)

    @app.delete(f"{prefix}/workspaces/{{workspace_id}}", status_code=204)
    def delete_workspace(workspace_id: str, _actor: str = Depends(principal)) -> None:
        try:
            removed = database.remove_workspace(workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not removed:
            raise HTTPException(status_code=404, detail="workspace not found")
        events.publish("workspace.removed", {"workspace_id": workspace_id})

    @app.get(f"{prefix}/repositories", response_model=list[RepositoryResponse])
    def repositories(
        workspace: str | None = None, _actor: str = Depends(principal)
    ) -> list[RepositoryResponse]:
        return [RepositoryResponse(**item.__dict__) for item in database.repositories(workspace)]

    @app.post(f"{prefix}/repositories", response_model=RepositoryResponse, status_code=201)
    def add_repository(
        payload: RepositoryCreate, _actor: str = Depends(principal)
    ) -> RepositoryResponse:
        try:
            item = database.register_repository(payload.workspace, payload.name, payload.root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        events.publish(
            "repository.registered",
            {"repository_id": item.repository_id, "workspace": item.workspace},
        )
        return RepositoryResponse(**item.__dict__)

    @app.get(f"{prefix}/repositories/{{repository_id}}", response_model=RepositoryResponse)
    def repository(repository_id: str, _actor: str = Depends(principal)) -> RepositoryResponse:
        return RepositoryResponse(**registered_repository(repository_id).__dict__)

    @app.delete(f"{prefix}/repositories/{{repository_id}}", status_code=204)
    def delete_repository(repository_id: str, _actor: str = Depends(principal)) -> None:
        item = registered_repository(repository_id)
        runtimes.remove(item.root)
        if not database.remove_repository(repository_id):
            raise HTTPException(status_code=404, detail="repository not found")
        events.publish(
            "repository.removed", {"repository_id": repository_id, "workspace": item.workspace}
        )

    @app.get(f"{prefix}/repositories/{{repository_id}}/overview")
    async def repository_overview(
        repository_id: str, _actor: str = Depends(principal)
    ) -> dict[str, Any]:
        item = registered_repository(repository_id)
        return await CortexApplicationService(runtimes.get(item.root)).repository_dashboard()

    @app.post(
        f"{prefix}/repositories/{{repository_id}}/index",
        response_model=JobResponse,
        status_code=202,
    )
    def index_repository(repository_id: str, actor: str = Depends(principal)) -> JobResponse:
        item = registered_repository(repository_id)

        def operation() -> dict[str, Any]:
            graph, stats = IncrementalGraphIndex(Path(item.root)).refresh()
            return {
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "tracked": stats.index.tracked,
                "files_reparsed": stats.files_reparsed,
                "full_rebuild": stats.full_rebuild,
            }

        return job_response(
            jobs.submit(
                "repository.index",
                {"repository_id": repository_id},
                operation,
                actor=actor,
                workspace=item.workspace,
                repository_id=repository_id,
            )
        )

    @app.get(f"{prefix}/jobs", response_model=list[JobResponse])
    def list_jobs(
        repository_id: str | None = None, limit: int = 100, _actor: str = Depends(principal)
    ) -> list[JobResponse]:
        return [
            job_response(item) for item in jobs.store.list(repository_id=repository_id, limit=limit)
        ]

    @app.get(f"{prefix}/jobs/{{job_id}}", response_model=JobResponse)
    def get_job(job_id: str, _actor: str = Depends(principal)) -> JobResponse:
        item = jobs.store.get(job_id)
        if item is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job_response(item)

    @app.delete(f"{prefix}/jobs/{{job_id}}", response_model=JobResponse)
    def cancel_job(job_id: str, _actor: str = Depends(principal)) -> JobResponse:
        try:
            return job_response(jobs.cancel(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    from codecortex.api.routes.repository import mount_repository_routes

    mount_repository_routes(app, prefix, database, runtimes, principal)
    from codecortex.api.feature_loader import ApiRouteContext, mount_optional_features

    mount_optional_features(
        app, ApiRouteContext(prefix, database, runtimes, principal, events, jobs, root)
    )
    return app
