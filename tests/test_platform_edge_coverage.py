from __future__ import annotations

import json
import queue
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from codecortex.api.app import create_app
from codecortex.application.safe_edit import SafeEditService
from codecortex.evaluation.baseline import PlatformBaselineStore
from codecortex.evaluation.regression import BenchmarkHistory
from codecortex.observability import PlatformMetrics, StructuredRequestLog, clock_ms, request_id
from codecortex.realtime import PlatformEventBus


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "module.py").write_text(
        "def greet(name: str) -> str:\n"
        "    return f'hello {name}'\n\n"
        "def caller() -> str:\n"
        "    return greet('world')\n",
        encoding="utf-8",
    )
    (root / "test_module.py").write_text(
        "from module import greet\n\n"
        "def test_greet() -> None:\n"
        "    assert greet('world') == 'hello world'\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def platform(tmp_path: Path):
    root = _repository(tmp_path)
    state_root = tmp_path / "platform-state"
    app = create_app(state_dir=state_root)
    with TestClient(app) as client:
        assert client.post("/api/v1/workspaces", json={"name": "alpha"}).status_code == 201
        repository = client.post(
            "/api/v1/repositories",
            json={"workspace": "alpha", "name": "demo", "root": str(root)},
        )
        assert repository.status_code == 201
        yield SimpleNamespace(
            app=app,
            client=client,
            repository_id=repository.json()["repository_id"],
            root=root,
            state_root=state_root,
        )


def test_event_bus_and_observability_primitives(tmp_path: Path) -> None:
    bus = PlatformEventBus(subscriber_queue_size=1)
    subscriber = bus.subscribe()
    first = bus.publish("workspace.created", {"workspace_id": "alpha"})
    assert first.to_dict()["type"] == "workspace.created"
    assert subscriber.get_nowait() == first

    for number in range(12):
        bus.publish("progress", {"number": number})
    buffered = []
    while True:
        try:
            buffered.append(subscriber.get_nowait())
        except queue.Empty:
            break
    assert len(buffered) == 10
    assert buffered[-1].payload == {"number": 11}
    bus.unsubscribe(subscriber)
    bus.publish("ignored", {})

    metrics = PlatformMetrics()
    metrics.begin()
    metrics.begin()
    metrics.finish("/health", 200, 5.0)
    metrics.finish("/broken", 503, 7.0)
    snapshot = metrics.snapshot()
    assert snapshot["requests"] == 2
    assert snapshot["errors"] == 1
    assert snapshot["in_flight"] == 0
    assert snapshot["statuses"] == {200: 1, 503: 1}
    exported = metrics.prometheus()
    assert "codecortex_api_errors_total 1" in exported
    assert 'codecortex_api_responses_total{status="503"} 1' in exported

    log_path = tmp_path / "runtime" / "api.jsonl"
    log = StructuredRequestLog(log_path)
    log.write(
        request_id="request-1",
        trace_id="trace-1",
        method="GET",
        path="/health",
        status=200,
        duration_ms=1.2349,
    )
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["request_id"] == "request-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["duration_ms"] == 1.235
    assert len(request_id()) == 32
    assert clock_ms() > 0


def test_platform_baseline_store_handles_valid_and_invalid_payloads(tmp_path: Path) -> None:
    path = tmp_path / "baselines" / "current.json"
    store = PlatformBaselineStore(path)
    recorded = store.record(
        {"requests": 12, "latency_ms": 4.5, "unavailable": None},
        revision="abc123",
        metadata={"runner": "ci", "attempt": "2"},
        recorded_at="2026-09-02T00:00:00+00:00",
    )
    assert recorded.metrics["unavailable"] is None
    assert store.load() == recorded

    with pytest.raises(TypeError, match="numeric or null"):
        store.record({"invalid": True})
    with pytest.raises(TypeError, match="numeric or null"):
        store.record({"invalid": "slow"})  # type: ignore[dict-item]

    path.write_text("not-json", encoding="utf-8")
    assert store.load() is None
    path.write_text('{"version": 9, "baseline": {}}', encoding="utf-8")
    assert store.load() is None
    path.write_text('{"version": 1, "baseline": {"metrics": []}}', encoding="utf-8")
    assert store.load() is None


def test_safe_edit_service_enforces_guards_and_dispatches_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codecortex.application import safe_edit as safe_edit_module

    root = _repository(tmp_path)
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeBackend:
        def preflight_symbol(self, name_path: str, path: str) -> dict[str, object]:
            return {"name_path": name_path, "path": path}

    class FakeEditor:
        def __init__(self, runtime: object) -> None:
            self.runtime = runtime

        def backend(self) -> FakeBackend:
            return FakeBackend()

        def rename(self, *args: object) -> dict[str, object]:
            calls.append(("rename", args))
            return {"operation": "rename"}

        def replace(self, *args: object) -> dict[str, object]:
            calls.append(("replace", args))
            return {"operation": "replace"}

        def insert_before(self, *args: object) -> dict[str, object]:
            calls.append(("insert_before", args))
            return {"operation": "insert_before"}

        def insert_after(self, *args: object) -> dict[str, object]:
            calls.append(("insert_after", args))
            return {"operation": "insert_after"}

    class FakeIndex:
        def __init__(self, path: Path) -> None:
            self.path = path

        def refresh(self) -> tuple[object, object]:
            return object(), object()

    @dataclass
    class Node:
        path: str | None
        name: str

    @dataclass
    class Impact:
        risk_score: float
        direct: list[object]
        indirect: list[object]
        affected_tests: list[object]

    class FakeImpactAnalyzer:
        def __init__(self, graph: object) -> None:
            self.graph = graph

        def analyze(self, target: str) -> Impact:
            item = SimpleNamespace(node=Node("test_module.py", "test_greet"))
            return Impact(0.7, [item], [item], [item])

    monkeypatch.setattr(safe_edit_module, "EditService", FakeEditor)
    monkeypatch.setattr(safe_edit_module, "IncrementalGraphIndex", FakeIndex)
    monkeypatch.setattr(safe_edit_module, "ImpactAnalyzer", FakeImpactAnalyzer)
    runtime = SimpleNamespace(config=SimpleNamespace(project_root=root))
    service = SafeEditService(runtime)

    preview = service.preview("rename", "module.py", "greet", new_name="welcome")
    assert preview["impact"] == {
        "risk_score": 0.7,
        "direct": 1,
        "indirect": 1,
        "affected_tests": ["test_module.py"],
    }
    assert preview["requires_approval"] is True
    digest = str(preview["file_sha256"])

    class MissingImpactAnalyzer:
        def __init__(self, graph: object) -> None:
            self.graph = graph

        def analyze(self, target: str) -> Impact:
            raise ValueError(target)

    monkeypatch.setattr(safe_edit_module, "ImpactAnalyzer", MissingImpactAnalyzer)
    assert service.preview("replace", "module.py", "greet", body="return 'fallback'")["impact"] == {
        "risk_score": 0.0,
        "direct": 0,
        "indirect": 0,
        "affected_tests": [],
    }

    with pytest.raises(ValueError, match="escapes project root"):
        service.preview("rename", "../outside.py", "greet")
    with pytest.raises(ValueError, match="not a file"):
        service.preview("rename", "missing.py", "greet")
    with pytest.raises(PermissionError, match="explicit approval"):
        service.apply("rename", "module.py", "greet", expected_file_sha256=digest, approved=False)
    with pytest.raises(RuntimeError, match="file changed"):
        service.apply("rename", "module.py", "greet", expected_file_sha256="bad", approved=True)

    for operation in ("rename", "replace", "insert_before", "insert_after"):
        result = service.apply(
            operation,  # type: ignore[arg-type]
            "module.py",
            "greet",
            expected_file_sha256=digest,
            approved=True,
            new_name="welcome",
            body="return 'updated'",
        )
        assert result["operation"] == operation
    with pytest.raises(ValueError, match="unknown edit operation"):
        service.apply(  # type: ignore[arg-type]
            "unknown",
            "module.py",
            "greet",
            expected_file_sha256=digest,
            approved=True,
        )
    assert [name for name, _ in calls] == ["rename", "replace", "insert_before", "insert_after"]


def test_platform_management_surfaces_are_operational(platform) -> None:
    app = platform.app
    client = platform.client
    repository_id = platform.repository_id

    assert client.get("/api/v1/platform/manifest").json()["product"] == "CodeCortex Platform"
    assert client.get("/api/v1/api-versions").json()["current"] == "v1"
    assert client.get("/api/v1/cluster").status_code == 200
    assert client.get("/api/v1/workers?active_within_seconds=60").status_code == 200
    assert client.get("/api/v1/cluster/tasks?status=unknown").status_code == 400
    assert client.get("/api/v1/cluster/tasks?status=queued&limit=1").json() == {"tasks": []}
    assert client.post("/api/v1/cluster/requeue-expired").json() == {"requeued": 0}

    prune = client.post("/api/v1/audit/prune")
    assert prune.status_code == 200
    audit = client.get("/api/v1/audit?action=audit.prune&outcome=success")
    assert audit.status_code == 200
    assert audit.json()["events"]

    job = app.state.job_manager.store.create("coverage", {}, actor="local-admin")
    app.state.job_manager.store.start(job.job_id)
    app.state.job_manager.store.fail(job.job_id, "expected for notification scan")
    scan = client.post("/api/v1/notifications/scan")
    assert scan.json()["created"] == 1
    notifications = client.get("/api/v1/notifications?limit=1").json()["notifications"]
    notification_id = notifications[0]["notification_id"]
    assert client.post(f"/api/v1/notifications/{notification_id}/acknowledge").json() == {
        "acknowledged": True
    }
    assert client.post(f"/api/v1/notifications/{notification_id}/acknowledge").status_code == 404
    assert client.get("/api/v1/notifications?include_acknowledged=true").json()["notifications"]

    memory = client.put(
        f"/api/v1/repositories/{repository_id}/memory",
        json={"key": "architecture", "value": "layered", "tags": ["design"]},
    )
    assert memory.status_code == 200
    assert memory.json()["revision"] == 1
    updated = client.put(
        f"/api/v1/repositories/{repository_id}/memory",
        json={"key": "architecture", "value": "layered-v2", "expected_revision": 1},
    )
    assert updated.json()["revision"] == 2
    conflict = client.put(
        f"/api/v1/repositories/{repository_id}/memory",
        json={"key": "architecture", "value": "stale", "expected_revision": 1},
    )
    assert conflict.status_code == 409
    assert client.get(
        f"/api/v1/repositories/{repository_id}/memory?query=layered&limit=1"
    ).json()["entries"]
    assert client.get(
        f"/api/v1/repositories/{repository_id}/memory/history?namespace=project&key=architecture"
    ).json()["entries"]

    integrations = client.get(f"/api/v1/repositories/{repository_id}/integrations")
    assert integrations.status_code == 200
    preview = client.post(
        f"/api/v1/repositories/{repository_id}/integrations/preview", json={"targets": ["codex"]}
    )
    assert preview.status_code == 200
    assert preview.json()["mutations"][0]["target"] == "codex"
    assert client.post(
        f"/api/v1/repositories/{repository_id}/integrations/apply", json={"targets": ["codex"]}
    ).status_code == 403
    applied = client.post(
        f"/api/v1/repositories/{repository_id}/integrations/apply",
        json={"targets": ["codex"], "approved": True},
    )
    assert applied.status_code == 200
    assert (platform.root / ".codex" / "config.toml").exists()

    assert client.get("/api/v1/performance/budgets").json()["budgets"]["api_p95_ms"] == 500.0
    scale = client.post(
        f"/api/v1/repositories/{repository_id}/performance/scale", json={"targets": [-1, 2, 1, 2]}
    )
    assert scale.status_code == 202
    assert scale.json()["targets"] == [1, 2]
    assert client.post(
        f"/api/v1/repositories/{repository_id}/performance/scale", json={"targets": [-1]}
    ).status_code == 400

    assert client.get(f"/api/v1/repositories/{repository_id}/backends").status_code == 200
    assert client.post(f"/api/v1/repositories/{repository_id}/backends/missing/install").status_code == 404
    assert client.delete(f"/api/v1/repositories/{repository_id}/backends/missing").status_code == 404

    history = BenchmarkHistory(platform.root / ".codecortex" / "benchmarks" / "history.json")
    first = history.append({"default": {"success_rate": 1.0, "avg_duration_ms": 10.0}})
    second = history.append({"default": {"success_rate": 0.99, "avg_duration_ms": 11.0}})
    quality = client.get(f"/api/v1/repositories/{repository_id}/quality")
    assert quality.json()["metric_state"] == "measured"
    assert client.get(
        f"/api/v1/repositories/{repository_id}/quality/compare?current={second.id}&baseline={first.id}"
    ).status_code == 200
    assert client.get(
        f"/api/v1/repositories/{repository_id}/quality/compare?current=missing&baseline={first.id}"
    ).status_code == 404

    observability = client.get(
        "/api/v1/observability", headers={"x-request-id": "coverage-request", "x-trace-id": "trace"}
    )
    assert observability.headers["x-request-id"] == "coverage-request"
    assert observability.json()["repositories"] == 1
    assert "codecortex_api_requests_total" in client.get("/api/v1/metrics").text


def test_code_action_routes_preserve_approval_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codecortex.api.routes import code_actions

    class FakeSafeEdits:
        def __init__(self, runtime: object) -> None:
            self.runtime = runtime

        def preview(self, operation: str, path: str, name_path: str, **kwargs: object) -> dict[str, object]:
            if path == "invalid.py":
                raise ValueError("invalid target")
            return {"operation": operation, "path": path, "name_path": name_path}

        def apply(self, operation: str, path: str, name_path: str, **kwargs: object) -> dict[str, object]:
            if not kwargs["approved"]:
                raise PermissionError("explicit approval is required")
            if path == "stale.py":
                raise RuntimeError("file changed after preview")
            return {"operation": operation, "path": path, "name_path": name_path}

    monkeypatch.setattr(code_actions, "SafeEditService", FakeSafeEdits)
    root = _repository(tmp_path)
    app = create_app(state_dir=tmp_path / "state")
    with TestClient(app) as client:
        client.post("/api/v1/workspaces", json={"name": "alpha"})
        created = client.post(
            "/api/v1/repositories",
            json={"workspace": "alpha", "name": "demo", "root": str(root)},
        )
        repository_id = created.json()["repository_id"]
        payload = {"operation": "rename", "path": "module.py", "name_path": "greet"}
        assert client.post(
            f"/api/v1/repositories/{repository_id}/code-actions/preview", json=payload
        ).status_code == 200
        assert client.post(
            f"/api/v1/repositories/{repository_id}/code-actions/preview",
            json=payload | {"path": "invalid.py"},
        ).status_code == 409
        assert client.post(
            f"/api/v1/repositories/{repository_id}/code-actions/apply", json=payload
        ).status_code == 403
        assert client.post(
            f"/api/v1/repositories/{repository_id}/code-actions/apply",
            json=payload | {"path": "stale.py", "approved": True},
        ).status_code == 409
        assert client.post(
            f"/api/v1/repositories/{repository_id}/code-actions/apply",
            json=payload | {"approved": True},
        ).json()["operation"] == "rename"


def test_repository_intelligence_routes_expose_live_analysis(platform) -> None:
    client = platform.client
    repository_id = platform.repository_id

    assert client.post(
        f"/api/v1/repositories/{repository_id}/search", json={"query": "greet", "limit": 1}
    ).status_code == 200
    assert client.post(
        f"/api/v1/repositories/{repository_id}/impact", json={"query": "greet"}
    ).status_code == 200
    assert client.get(f"/api/v1/repositories/{repository_id}/traces?limit=1").json() == {
        "traces": []
    }
    assert client.get(f"/api/v1/repositories/{repository_id}/traces/missing").status_code == 404

    analysis = client.get(f"/api/v1/repositories/{repository_id}/architecture")
    assert analysis.status_code == 200
    before = client.get(f"/api/v1/repositories/{repository_id}/architecture/drift")
    assert before.json()["baseline"] is None
    assert client.post(
        f"/api/v1/repositories/{repository_id}/architecture/baseline"
    ).status_code == 200
    after = client.get(f"/api/v1/repositories/{repository_id}/architecture/drift")
    assert after.json()["baseline"] is not None

    assert client.get(f"/api/v1/repositories/{repository_id}/git").status_code == 200
    assert client.get(
        f"/api/v1/repositories/{repository_id}/git/files/history?path=module.py"
    ).status_code == 200
    assert client.get(
        f"/api/v1/repositories/{repository_id}/git/symbol-history?path=module.py&start=0&end=1"
    ).status_code == 400
    assert client.post(
        f"/api/v1/repositories/{repository_id}/pr-analysis",
        json={"base_ref": "main", "head_ref": "HEAD"},
    ).status_code == 200


def test_organization_admin_routes_cover_roles_and_workspace_policy(platform) -> None:
    client = platform.client
    assert client.get("/api/v1/organizations").json() == {"organizations": []}
    created = client.post(
        "/api/v1/organizations", json={"slug": "acme", "display_name": "Acme Corp"}
    )
    assert created.status_code == 201
    assert client.post(
        "/api/v1/organizations", json={"slug": "acme", "display_name": "Acme Corp"}
    ).status_code == 201
    members = client.get("/api/v1/organizations/acme/members")
    assert members.status_code == 200
    assert members.json()["members"] == [{"principal": "local-admin", "role": "owner"}]
    assert client.put(
        "/api/v1/organizations/acme/members", json={"principal": "reader", "role": "viewer"}
    ).json() == {"principal": "reader", "role": "viewer"}
    assert client.get("/api/v1/organizations/acme/workspaces/alpha/policy").status_code == 404
    saved = client.put(
        "/api/v1/organizations/acme/workspaces/alpha/policy",
        json={
            "allowed_tools": ["search", "graph"],
            "max_context_tokens": 4096,
            "remote_access": True,
            "metadata": {"tier": "test"},
        },
    )
    assert saved.status_code == 200
    assert client.get("/api/v1/organizations/acme/workspaces/alpha/policy").json()[
        "max_context_tokens"
    ] == 4096


@pytest.mark.asyncio
async def test_context_and_trace_application_services_cover_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codecortex.application import context_lab as context_lab_module
    from codecortex.application.context_lab import ContextLabService
    from codecortex.application.traces import TraceExplorerService

    root = _repository(tmp_path)

    @dataclass
    class Metrics:
        tokens: int

    class Chunk:
        def model_dump(self, *, mode: str) -> dict[str, str]:
            assert mode == "json"
            return {"text": "context"}

    class FakePipeline:
        def __init__(self, path: Path, graph: object) -> None:
            assert path == root
            self.graph = graph

        async def prepare(self, query: str, chunks: list[Chunk], budget: int) -> SimpleNamespace:
            assert query == "greet"
            assert chunks
            assert budget == 512
            return SimpleNamespace(metrics=Metrics(tokens=12), chunks=chunks)

    class FakeIndex:
        def __init__(self, path: Path) -> None:
            assert path == root

        def refresh(self) -> tuple[object, object]:
            return object(), object()

    class Gateway:
        async def query(self, query: str, project_root: str) -> SimpleNamespace:
            assert query == "greet"
            assert project_root == str(root)
            return SimpleNamespace(
                results=[SimpleNamespace(chunks=[Chunk()])], metadata={"trace_id": "trace-1"}
            )

    runtime = SimpleNamespace(
        config=SimpleNamespace(project_root=root, validate_budget=lambda budget: min(budget, 512)),
        gateway=Gateway(),
    )
    monkeypatch.setattr(context_lab_module, "IncrementalGraphIndex", FakeIndex)
    monkeypatch.setattr(context_lab_module, "ContextPipeline", FakePipeline)
    context = await ContextLabService(runtime).build("greet", 2048)
    assert context == {
        "query": "greet",
        "budget": 512,
        "metrics": {"tokens": 12},
        "trace_id": "trace-1",
        "chunks": [{"text": "context"}],
    }
    with pytest.raises(ValueError, match="context query"):
        await ContextLabService(runtime).build("   ")

    @dataclass
    class Span:
        trace_id: str
        started_at: str

    @dataclass
    class Summary:
        trace_id: str
        spans: int

    class Tracer:
        def read(self, key: str | None = None, *, limit: int | None = None) -> list[Span]:
            if limit is not None:
                return [Span("older", "2026-01-01"), Span("newer", "2026-02-01"), Span("older", "2026-03-01")]
            if key == "newer":
                return [Span("newer", "2026-02-01")]
            return []

        def summarize(self, trace_id: str) -> Summary:
            return Summary(trace_id, 1)

    traces = TraceExplorerService(SimpleNamespace(tracer=Tracer()))
    assert [item["trace_id"] for item in traces.recent(900)["traces"]] == ["older", "newer"]
    assert traces.detail("newer")["summary"] == {"trace_id": "newer", "spans": 1}
    with pytest.raises(KeyError):
        traces.detail("missing")


def test_repository_context_routes_and_missing_resource_guards(
    platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codecortex.api.routes import repository as repository_routes

    class FakeContextLab:
        def __init__(self, runtime: object) -> None:
            self.runtime = runtime

        async def build(self, query: str, budget: int) -> dict[str, object]:
            if query == "invalid":
                raise ValueError("context rejected")
            return {"query": query, "budget": budget}

    class FakeSearch:
        def __init__(self, root: Path) -> None:
            self.root = root

        def search(self, query: str, limit: int) -> dict[str, object]:
            if query == "invalid":
                raise ValueError("search rejected")
            return {"query": query, "limit": limit}

    class FakeImpact:
        def __init__(self, root: Path) -> None:
            self.root = root

        def analyze(self, query: str) -> dict[str, object]:
            if query == "invalid":
                raise ValueError("impact rejected")
            return {"target": query}

    monkeypatch.setattr(repository_routes, "ContextLabService", FakeContextLab)
    monkeypatch.setattr(repository_routes, "RepositorySearchService", FakeSearch)
    monkeypatch.setattr(repository_routes, "ImpactService", FakeImpact)
    client = platform.client
    repository_id = platform.repository_id
    assert client.post(
        f"/api/v1/repositories/{repository_id}/context", json={"query": "context", "budget": 256}
    ).json() == {"query": "context", "budget": 256}
    assert client.post(
        f"/api/v1/repositories/{repository_id}/context", json={"query": "invalid"}
    ).status_code == 400
    assert client.post(
        f"/api/v1/repositories/{repository_id}/search", json={"query": "invalid"}
    ).status_code == 400
    assert client.post(
        f"/api/v1/repositories/{repository_id}/impact", json={"query": "invalid"}
    ).status_code == 404
    for suffix in ("files", "memory", "integrations", "backends", "git"):
        assert client.get(f"/api/v1/repositories/missing/{suffix}").status_code == 404
    assert client.post(
        "/api/v1/repositories/missing/pr-analysis", json={"base_ref": "main"}
    ).status_code == 404


def test_active_backend_notifications_and_backend_removal(
    platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codecortex.api.routes import backends as backend_routes
    from codecortex.backends.spec import BackendSpec

    client = platform.client
    runtime = platform.app.state.runtime_manager.get(platform.root)
    runtime.active_backends = ("graph",)
    monkeypatch.setattr(runtime.backend_manager, "probe", lambda *args, **kwargs: False)
    scanned = client.post("/api/v1/notifications/scan")
    assert scanned.json()["created"] == 1
    assert client.post(
        f"/api/v1/repositories/{platform.repository_id}/backends/graph/install"
    ).status_code == 409
    assert client.delete(
        f"/api/v1/repositories/{platform.repository_id}/backends/graph"
    ).json() == {"backend": "graph", "installed": False}
    configured = BackendSpec(
        "fake",
        ("test",),
        package="fake-package",
        source_url="https://example.invalid/fake.git",
        revision="a" * 40,
        command="fake-backend",
    )
    monkeypatch.setattr(backend_routes, "BACKENDS", {"fake": configured})
    monkeypatch.setattr(runtime.backend_manager, "ensure", lambda spec: Path("/tmp/fake-backend"))
    installed = client.post(
        f"/api/v1/repositories/{platform.repository_id}/backends/fake/install"
    )
    assert installed.json()["installed"] is True


def test_cluster_tasks_route_hides_lease_tokens(platform) -> None:
    from codecortex.distributed.cluster import ClusterCoordinator

    cluster = ClusterCoordinator(platform.state_root / "distributed")
    cluster.workers.enqueue("coverage", {"source": "test"})
    payload = platform.client.get("/api/v1/cluster/tasks?status=queued").json()
    assert payload["tasks"]
    assert "lease_token" not in payload["tasks"][0]


def test_public_api_cli_contracts_and_feature_loading(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import builtins

    import typer
    import uvicorn

    from codecortex.api import app as api_app
    from codecortex.api import cli as api_cli
    from codecortex.api import feature_loader, versioning
    from codecortex.application.contracts import MeasurementValue, Page
    from codecortex.core.errors import (
        CodeCortexError,
        ContextBudgetExceededError,
        EngineUnavailableError,
    )
    from codecortex.platform import CAPABILITIES

    captured: dict[str, object] = {}
    service = object()
    monkeypatch.setattr(api_app, "create_app", lambda *, state_dir: service)
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, *, host, port: captured.update(app=app, host=host, port=port),
    )
    api_cli.serve(host="0.0.0.0", port=8123, state_dir=tmp_path)
    assert captured == {"app": service, "host": "0.0.0.0", "port": 8123}

    original_import = builtins.__import__

    def import_without_uvicorn(name: str, *args: object, **kwargs: object) -> object:
        if name == "uvicorn":
            raise ImportError("uvicorn unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_uvicorn)
    with pytest.raises(typer.BadParameter, match="web dependencies"):
        api_cli.serve()

    assert MeasurementValue.measured(3, "ms").kind == "measured"
    assert MeasurementValue.estimated(3).kind == "estimated"
    assert MeasurementValue.unavailable("bytes").value is None
    assert Page[str](items=("one",), total=1, limit=1, offset=0).items == ("one",)
    assert isinstance(ContextBudgetExceededError(), CodeCortexError)
    assert isinstance(EngineUnavailableError(), CodeCortexError)
    assert "repository" in CAPABILITIES.all()
    monkeypatch.setattr(versioning, "SUPPORTED_API_VERSIONS", ())
    with pytest.raises(RuntimeError, match="no stable API version"):
        versioning.current_api_version()

    mounted: list[str] = []

    class Feature:
        @staticmethod
        def mount(app: object, context: object) -> None:
            assert app is service
            assert context is not None
            mounted.append("present")

    def import_feature(name: str) -> object:
        if name == "missing":
            raise ModuleNotFoundError("missing", name="missing")
        if name == "broken":
            raise ModuleNotFoundError("nested", name="nested")
        return Feature

    monkeypatch.setattr(feature_loader, "_FEATURE_MODULES", ("present", "missing"))
    monkeypatch.setattr(feature_loader, "import_module", import_feature)
    feature_loader.mount_optional_features(service, object())
    assert mounted == ["present"]
    monkeypatch.setattr(feature_loader, "_FEATURE_MODULES", ("broken",))
    with pytest.raises(ModuleNotFoundError, match="nested"):
        feature_loader.mount_optional_features(service, object())
