from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from codecortex.api.app import create_app
from codecortex.api.auth import ApiSecuritySettings, ApiTokenAuthenticator
from codecortex.jobs import JobManager, JobStatus, JobStore
from codecortex.notifications import NotificationStore
from codecortex.persistence import PlatformDatabase
from codecortex.projects.context import RepositoryContext
from codecortex.projects.runtime_manager import CortexRuntimeManager


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hello {name}'\n\n"
        "def caller() -> str:\n    return greet('world')\n",
        encoding="utf-8",
    )
    (root / "test_app.py").write_text(
        "from app import greet\n\ndef test_greet():\n    assert greet('x') == 'hello x'\n",
        encoding="utf-8",
    )
    return root


def test_api_authenticator_covers_local_and_token_modes() -> None:
    local = ApiTokenAuthenticator()
    assert local.authenticate(None) == "local-admin"
    assert not local.configured

    required = ApiTokenAuthenticator(ApiSecuritySettings(require_auth=True))
    assert required.authenticate(None) is None

    tokens = ApiTokenAuthenticator(
        ApiSecuritySettings(require_auth=True, tokens={"alice": "secret", "ignored": ""})
    )
    assert tokens.configured
    assert tokens.authenticate(None) is None
    assert tokens.authenticate("Basic abc") is None
    assert tokens.authenticate("Bearer wrong") is None
    assert tokens.authenticate("Bearer secret") == "alice"


def test_platform_database_full_local_lifecycle(tmp_path: Path) -> None:
    database = PlatformDatabase(
        tmp_path / "state" / "platform.db", repository_root=tmp_path
    )
    assert database.schema_version == 2
    assert database.workspaces() == ()

    alpha = database.create_workspace(" alpha ", workspace_id="ws-alpha")
    assert alpha.name == "alpha"
    assert database.create_workspace("alpha").workspace_id == "ws-alpha"
    with pytest.raises(ValueError):
        database.create_workspace("   ")

    repo = _repo(tmp_path)
    record = database.register_repository("alpha", "demo", repo, repository_id="repo-1")
    assert record.repository_id == "repo-1"
    assert database.repository("repo-1") == record
    assert database.repositories("alpha") == (record,)
    assert database.repositories() == (record,)

    updated = database.register_repository("alpha", "renamed", repo)
    assert updated.repository_id == "repo-1"
    assert updated.name == "renamed"
    with pytest.raises(ValueError):
        database.register_repository("", "bad", repo)
    with pytest.raises(ValueError):
        database.register_repository("alpha", "missing", tmp_path / "missing")
    with pytest.raises(ValueError):
        database.register_repository("alpha", "outside", tmp_path.parent)
    with pytest.raises(ValueError):
        database.remove_workspace("ws-alpha")

    assert database.remove_repository("repo-1")
    assert not database.remove_repository("repo-1")
    assert database.repository("repo-1") is None
    assert database.remove_workspace("ws-alpha")
    assert not database.remove_workspace("ws-alpha")

    future = tmp_path / "future.db"
    with sqlite3.connect(future) as connection:
        connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_version VALUES (999)")
    with pytest.raises(RuntimeError):
        PlatformDatabase(future)


def test_job_store_and_manager_cover_success_failure_cancel(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    with pytest.raises(ValueError):
        store.create("", {}, actor="actor")

    queued = store.create(
        "demo", {"x": 1}, actor="actor", workspace="alpha", repository_id="repo-1"
    )
    assert queued.status is JobStatus.QUEUED
    assert store.get(queued.job_id) == queued
    running = store.start(queued.job_id)
    assert running.status is JobStatus.RUNNING
    assert store.progress(queued.job_id, 2).progress == 1
    assert store.progress(queued.job_id, -1).progress == 0
    completed = store.complete(queued.job_id, {"ok": True})
    assert completed.status is JobStatus.COMPLETED
    assert completed.result == {"ok": True}
    assert store.cancel(queued.job_id) == completed
    assert store.list(repository_id="repo-1")
    assert store.list(limit=1)
    with pytest.raises(KeyError):
        store.get("missing") or store.progress("missing", 0.5)
    with pytest.raises(KeyError):
        store.cancel("missing")
    with pytest.raises(KeyError):
        store.start("missing")

    failed_job = store.create("fail", {}, actor="actor")
    store.start(failed_job.job_id)
    failed = store.fail(failed_job.job_id, "boom")
    assert failed.status is JobStatus.FAILED
    assert failed.error == "boom"

    cancelled_job = store.create("cancel", {}, actor="actor")
    assert store.cancel(cancelled_job.job_id).status is JobStatus.CANCELLED

    events: list[tuple[str, dict[str, object]]] = []
    manager = JobManager(
        JobStore(tmp_path / "managed.db"), max_workers=1, event_sink=lambda kind, data: events.append((kind, data))
    )
    success = manager.submit("success", {}, lambda: {"value": 7}, actor="actor")
    assert manager._futures[success.job_id].result(timeout=5) == {"value": 7}
    assert manager.store.get(success.job_id).status is JobStatus.COMPLETED  # type: ignore[union-attr]

    failure = manager.submit("failure", {}, lambda: (_ for _ in ()).throw(RuntimeError("x")), actor="actor")
    assert manager._futures[failure.job_id].result(timeout=5) == {}
    assert manager.store.get(failure.job_id).status is JobStatus.FAILED  # type: ignore[union-attr]

    pending = manager.store.create("manual", {}, actor="actor")
    assert manager.cancel(pending.job_id).status is JobStatus.CANCELLED
    assert {kind for kind, _ in events} >= {
        "job.queued",
        "job.started",
        "job.completed",
        "job.failed",
        "job.cancelled",
    }
    manager.close()


def test_notification_store_lifecycle(tmp_path: Path) -> None:
    store = NotificationStore(tmp_path / "notifications.db")
    first = store.emit("job.failed", "critical", "Failure", "boom", "job-1", {"attempt": 1})
    second = store.emit("backend.warning", "warning", "Backend", "slow", "backend-1")
    active = store.list()
    assert {item.notification_id for item in active} == {first.notification_id, second.notification_id}
    assert store.payload(first)["metadata"] == {"attempt": 1}
    assert store.acknowledge(first.notification_id)
    assert not store.acknowledge(first.notification_id)
    assert not store.acknowledge("missing")
    assert [item.notification_id for item in store.list()] == [second.notification_id]
    assert len(store.list(include_acknowledged=True)) == 2


def test_repository_context_and_runtime_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    context = RepositoryContext(repo)
    first = context.refresh()
    assert first.generation == 1
    assert first.graph.nodes
    assert context.snapshot == first
    assert context.graph().nodes
    assert context.symbols()

    built: list[Path] = []

    def fake_build(root: Path):
        built.append(root)
        return SimpleNamespace(root=root)

    monkeypatch.setattr("codecortex.projects.runtime_manager.build_runtime", fake_build)
    manager = CortexRuntimeManager()
    runtime = manager.get(repo)
    assert manager.get(repo) is runtime
    assert built == [repo.resolve()]
    assert manager.roots() == (repo.resolve(),)
    assert manager.remove(repo)
    assert not manager.remove(repo)
    manager.get(repo)
    manager.clear()
    assert manager.roots() == ()
    with pytest.raises(ValueError):
        manager.get(tmp_path / "missing")


def test_platform_http_core_routes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    app = create_app(state_dir=tmp_path / "platform-state", repository_root=tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
        assert client.get("/api/v1/readiness").json()["status"] == "ready"
        assert client.get("/api/v1/version").json()["version"] == "v1"
        assert client.get("/api/v1/session").json() == {"principal": "local-admin"}

        workspace = client.post("/api/v1/workspaces", json={"name": "alpha"})
        assert workspace.status_code == 201
        workspace_id = workspace.json()["workspace_id"]
        assert client.get("/api/v1/workspaces").json()[0]["name"] == "alpha"

        created = client.post(
            "/api/v1/repositories",
            json={"workspace": "alpha", "name": "demo", "root": str(repo)},
        )
        assert created.status_code == 201
        repository_id = created.json()["repository_id"]
        assert client.get(f"/api/v1/repositories/{repository_id}").status_code == 200
        assert client.get("/api/v1/repositories?workspace=alpha").json()[0]["name"] == "demo"
        assert client.get("/api/v1/repositories/missing").status_code == 404

        overview = client.get(f"/api/v1/repositories/{repository_id}/overview")
        assert overview.status_code == 200
        assert overview.json()["graph"]["nodes"] >= 1
        assert client.get(f"/api/v1/repositories/{repository_id}/files").status_code == 200
        assert client.get(f"/api/v1/repositories/{repository_id}/symbols?query=greet").status_code == 200
        assert client.get(f"/api/v1/repositories/{repository_id}/graph?query=greet&depth=2").status_code == 200
        route = client.post(
            f"/api/v1/repositories/{repository_id}/route", json={"query": "find greet"}
        )
        assert route.status_code == 200
        assert "selected" in route.json()

        index = client.post(f"/api/v1/repositories/{repository_id}/index")
        assert index.status_code == 202
        job_id = index.json()["job_id"]
        for _ in range(50):
            job = client.get(f"/api/v1/jobs/{job_id}")
            if job.json()["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert job.json()["status"] == "completed"
        assert client.get(f"/api/v1/jobs?repository_id={repository_id}").json()
        assert client.get("/api/v1/jobs/missing").status_code == 404
        assert client.delete("/api/v1/jobs/missing").status_code == 404

        organization = client.post(
            "/api/v1/organizations", json={"slug": "acme", "display_name": "Acme"}
        )
        assert organization.status_code == 201
        assert client.get("/api/v1/organizations").json()["organizations"]
        assert client.get("/api/v1/organizations/acme/members").status_code == 200
        member = client.put(
            "/api/v1/organizations/acme/members",
            json={"principal": "bob", "role": "member"},
        )
        assert member.status_code == 200
        policy = client.put(
            "/api/v1/organizations/acme/workspaces/alpha/policy",
            json={"allowed_tools": ["search"], "max_context_tokens": 4096, "remote_access": False},
        )
        assert policy.status_code == 200
        assert client.get("/api/v1/organizations/acme/workspaces/alpha/policy").json()[
            "max_context_tokens"
        ] == 4096

        assert client.delete(f"/api/v1/workspaces/{workspace_id}").status_code == 409
        assert client.delete(f"/api/v1/repositories/{repository_id}").status_code == 204
        assert client.delete(f"/api/v1/repositories/{repository_id}").status_code == 404
        assert client.delete(f"/api/v1/workspaces/{workspace_id}").status_code == 204
        assert client.delete(f"/api/v1/workspaces/{workspace_id}").status_code == 404


def test_http_auth_required(tmp_path: Path) -> None:
    app = create_app(
        state_dir=tmp_path / "secure",
        security=ApiSecuritySettings(require_auth=True, tokens={"alice": "secret"}),
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/session").status_code == 401
        assert client.get("/api/v1/session", headers={"Authorization": "Bearer wrong"}).status_code == 401
        response = client.get(
            "/api/v1/session", headers={"Authorization": "Bearer secret"}
        )
        assert response.status_code == 200
        assert response.json()["principal"] == "alice"
