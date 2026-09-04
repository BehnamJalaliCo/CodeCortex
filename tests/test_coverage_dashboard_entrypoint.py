from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import typer

import codecortex.dashboard as dashboard
import codecortex.entrypoint as entrypoint
from codecortex.backends.contracts import BackendStatus


def _runtime(tmp_path: Path) -> SimpleNamespace:
    from codecortex.config import CortexConfig

    return SimpleNamespace(
        config=CortexConfig(project_root=tmp_path),
        active_backends=("graph",),
        gateway=SimpleNamespace(health=lambda: None),
    )


def test_dashboard_event_helpers_and_html(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    assert dashboard._read_events(runtime) == []
    path = runtime.config.state_dir / "runtime" / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "bad-json\n"
        '{"name":"route.created","attributes":{"kind":"debug"}}\n'
        '{"name":"context.fitted","attributes":{"saved":12}}\n'
        '{"name":"engine.executed","attributes":{"capability":"symbols","duration_ms":20}}\n'
        '{"name":"engine.executed","attributes":{"capability":"symbols","duration_ms":10}}\n'
        "[]\n",
        encoding="utf-8",
    )
    events = dashboard._read_events(runtime, limit=10)
    assert len(events) == 4
    stats = dashboard._event_stats(events)
    assert stats["routes"] == {"debug": 1}
    assert stats["context_tokens_saved"] == 12
    assert stats["engine_avg_latency_ms"] == {"symbols": 15.0}
    assert "&lt;repo&gt;&amp;" in dashboard._html("<repo>&")


def test_dashboard_trace_history_and_architecture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path)

    @dataclass
    class _Span:
        trace_id: str

    @dataclass
    class _Summary:
        trace_id: str
        spans: int = 1
        duration_ms: float = 1.0
        context_tokens: int = 2
        errors: int = 0

    class _Recorder:
        def __init__(self, path: Path) -> None:
            self.path = path

        def read(self, limit: int) -> list[_Span]:
            return [_Span("a"), _Span("b"), _Span("a")]

        def summarize(self, trace_id: str) -> _Summary:
            if trace_id == "b":
                raise KeyError(trace_id)
            return _Summary(trace_id)

    monkeypatch.setattr(dashboard, "TaskTraceRecorder", _Recorder)
    traces = dashboard._recent_traces(runtime, 2)
    assert traces == [
        {"trace_id": "a", "spans": 1, "duration_ms": 1.0, "context_tokens": 2, "errors": 0}
    ]

    @dataclass
    class _HistoryItem:
        created_at: str
        commit: str
        metrics: dict[str, Any]

    class _History:
        def __init__(self, path: Path) -> None:
            self.path = path

        def load(self) -> list[_HistoryItem]:
            return [_HistoryItem("now", "abc", {"full": 1})]

    monkeypatch.setattr(dashboard, "BenchmarkHistory", _History)
    assert dashboard._benchmark_history(runtime) == [
        {"created_at": "now", "commit": "abc", "metrics": {"full": 1}}
    ]

    @dataclass
    class _Fingerprint:
        value: int

    @dataclass
    class _Report:
        changed: bool

    class _Detector:
        def fingerprint(self, graph: Any) -> _Fingerprint:
            return _Fingerprint(1)

        def compare(self, baseline: Any, current: Any) -> _Report:
            return _Report(True)

    monkeypatch.setattr(dashboard, "ArchitectureDriftDetector", _Detector)
    monkeypatch.setattr(dashboard.ArchitectureFingerprint, "load", lambda path: None)
    assert dashboard._architecture_drift(runtime, object())["status"] == "no-baseline"
    monkeypatch.setattr(dashboard.ArchitectureFingerprint, "load", lambda path: object())
    compared = dashboard._architecture_drift(runtime, object())
    assert compared == {"status": "compared", "report": {"changed": True}}


@pytest.mark.asyncio
async def test_dashboard_overview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(tmp_path)

    @dataclass
    class _Node:
        id: str
        name: str
        path: str

    @dataclass
    class _Edge:
        source: str
        target: str

    graph = SimpleNamespace(
        nodes=[_Node("a", "A", "a.py"), _Node("b", "B", "b.py")],
        edges=[_Edge("a", "b")],
        counts=lambda: {"file": 2},
    )
    index_stats = SimpleNamespace(
        index=SimpleNamespace(tracked=2, duration_ms=3.5),
        files_reparsed=1,
        full_rebuild=False,
    )

    class _Index:
        def __init__(self, root: Path) -> None:
            self.root = root

        def refresh(self) -> tuple[Any, Any]:
            return graph, index_stats

    class _Gateway:
        async def health(self) -> dict[str, bool]:
            return {"repository": True}

    runtime.gateway = _Gateway()
    monkeypatch.setattr(dashboard, "IncrementalGraphIndex", _Index)
    monkeypatch.setattr(dashboard, "_read_events", lambda runtime: [])
    monkeypatch.setattr(dashboard, "_recent_traces", lambda runtime: [])
    monkeypatch.setattr(dashboard, "_benchmark_history", lambda runtime: [])
    monkeypatch.setattr(
        dashboard,
        "_architecture_drift",
        lambda runtime, graph: {"status": "no-baseline"},
    )
    result = await dashboard._overview(runtime)
    assert result["index"]["tracked"] == 2
    assert result["graph"]["hot_nodes"][0]["degree"] == 1
    assert result["health"] == {"repository": True}


def test_dashboard_http_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(tmp_path)

    class _Gateway:
        async def health(self) -> dict[str, bool]:
            return {"ok": True}

    runtime.gateway = _Gateway()
    captured: dict[str, Any] = {}

    class _Server:
        def __init__(self, address: tuple[str, int], handler: type) -> None:
            captured["address"] = address
            captured["handler"] = handler
            self.closed = False

        def serve_forever(self) -> None:
            captured["served"] = True

        def server_close(self) -> None:
            self.closed = True
            captured["closed"] = True

    monkeypatch.setattr(dashboard, "ThreadingHTTPServer", _Server)
    monkeypatch.setattr(dashboard, "_overview", lambda runtime: _async_value({"overview": True}))
    monkeypatch.setattr(dashboard, "_recent_traces", lambda runtime, limit: [{"trace": 1}])
    monkeypatch.setattr(dashboard, "_benchmark_history", lambda runtime, limit: [{"bench": 1}])
    dashboard.run_dashboard(runtime, host="127.0.0.1", port=9000)
    assert captured["address"] == ("127.0.0.1", 9000)
    assert captured["served"] and captured["closed"]

    handler_type = captured["handler"]
    handler = object.__new__(handler_type)
    sent: list[tuple[int, Any]] = []
    handler._json = lambda status, payload: sent.append((status, payload))
    handler._send = lambda status, content_type, body: sent.append((status, body))

    for path, status in [
        ("/", 200),
        ("/api/overview", 200),
        ("/api/health", 200),
        ("/api/traces", 200),
        ("/api/benchmarks", 200),
        ("/missing", 404),
        ("/api/pr-risk?base=bad%20ref&head=HEAD", 400),
    ]:
        handler.path = path
        handler.do_GET()
        assert sent[-1][0] == status

    @dataclass
    class _RiskReport:
        risk: str

    monkeypatch.setattr(
        dashboard,
        "IncrementalGraphIndex",
        lambda root: SimpleNamespace(refresh=lambda: (object(), object())),
    )
    monkeypatch.setattr(
        dashboard,
        "PRIntelligence",
        lambda root, graph: SimpleNamespace(analyze=lambda base, head: _RiskReport(risk="low")),
    )
    handler.path = "/api/pr-risk?base=main&head=HEAD"
    handler.do_GET()
    assert sent[-1] == (200, {"risk": "low"})

    monkeypatch.setattr(
        dashboard,
        "PRIntelligence",
        lambda root, graph: SimpleNamespace(
            analyze=lambda base, head: (_ for _ in ()).throw(RuntimeError("boom"))
        ),
    )
    handler.do_GET()
    assert sent[-1][0] == 422

    handler.log_message("ignored", 1)


async def _async_value(value: Any) -> Any:
    return value


class _FakeManager:
    def __init__(self) -> None:
        self.installed = False
        self.fail_ensure = False
        self.removed: list[str] = []

    def is_installed(self, spec: Any) -> bool:
        return self.installed

    def ensure(self, spec: Any) -> Path:
        if self.fail_ensure:
            raise RuntimeError("install failed")
        return Path("/tmp/backend")

    def remove(self, spec: Any) -> None:
        self.removed.append(spec.key)


def test_entrypoint_helpers_and_backend_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert set(entrypoint._targets("all")) == set(entrypoint.BACKENDS)
    assert entrypoint._targets("graph") == ("graph",)
    with pytest.raises(typer.BadParameter):
        entrypoint._targets("missing")

    manager = _FakeManager()
    monkeypatch.setattr(entrypoint, "_manager", lambda: manager)
    monkeypatch.setattr(entrypoint.console, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(entrypoint.console, "print_json", lambda *args, **kwargs: None)
    entrypoint.backend_list()
    entrypoint.backend_install("graph")
    manager.fail_ensure = True
    with pytest.raises(typer.Exit):
        entrypoint.backend_install("graph")
    manager.fail_ensure = False
    entrypoint.backend_remove("graph")
    assert manager.removed == ["graph"]

    unhealthy = BackendStatus(
        key="graph",
        installed=True,
        healthy=False,
        revision="r",
        contract_version=1,
        capabilities=("repository",),
    )
    healthy = BackendStatus(
        key="graph",
        installed=True,
        healthy=True,
        revision="r",
        contract_version=1,
        capabilities=("repository",),
    )
    current = {"status": unhealthy}
    monkeypatch.setattr(
        entrypoint,
        "_adapter",
        lambda key, root, manager: SimpleNamespace(status=lambda: current["status"]),
    )
    with pytest.raises(typer.Exit):
        entrypoint.backend_doctor(tmp_path)
    current["status"] = healthy
    entrypoint.backend_doctor(tmp_path)
    entrypoint.backend_status(tmp_path)


def test_entrypoint_version_adapters_agents_edits_and_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    printed: list[Any] = []
    monkeypatch.setattr(entrypoint.console, "print", lambda value, *a, **k: printed.append(value))
    monkeypatch.setattr(entrypoint.console, "print_json", lambda *a, **k: None)
    monkeypatch.setattr(entrypoint, "version", lambda name: "1.2.3")
    entrypoint.version_command()
    assert printed[-1] == "1.2.3"

    def _missing_version(name: str) -> str:
        raise entrypoint.PackageNotFoundError

    monkeypatch.setattr(entrypoint, "version", _missing_version)
    entrypoint.version_command()
    assert printed[-1] == "0+unknown"

    manager = _FakeManager()
    assert entrypoint._adapter("graph", tmp_path, manager).__class__.__name__.startswith("Graph")
    assert entrypoint._adapter("symbols", tmp_path, manager).__class__.__name__.startswith("Symbol")
    assert entrypoint._adapter("context", tmp_path, manager).__class__.__name__.startswith(
        "Context"
    )
    with pytest.raises(KeyError):
        entrypoint._adapter("missing", tmp_path, manager)

    class _Configurator:
        def __init__(self, path: Path) -> None:
            self.path = path

        def detect(self) -> list[Any]:
            return []

        def configure(self, selected: Any = (), dry_run: bool = False) -> list[Any]:
            return []

    monkeypatch.setattr(entrypoint, "AgentConfigurator", _Configurator)
    entrypoint.agents_detect(tmp_path)
    entrypoint.agents_configure(tmp_path, target=None, all_supported=False, dry_run=True)

    target = next(iter(entrypoint.AgentTarget))
    mutation = SimpleNamespace(
        target=target, changed=True, path=tmp_path / "config", backup=tmp_path / "backup"
    )

    class _ConfiguratorWithData(_Configurator):
        def detect(self) -> list[Any]:
            return [target]

        def configure(self, selected: Any = (), dry_run: bool = False) -> list[Any]:
            return [mutation]

    monkeypatch.setattr(entrypoint, "AgentConfigurator", _ConfiguratorWithData)
    entrypoint.agents_detect(tmp_path)
    entrypoint.agents_configure(tmp_path, target=[target], all_supported=False, dry_run=True)
    mutation.changed = False
    mutation.backup = None
    entrypoint.agents_configure(tmp_path, target=[target], all_supported=False, dry_run=False)

    class _Edit:
        def rename(self, *args: Any) -> dict[str, bool]:
            return {"ok": True}

        def replace(self, *args: Any) -> dict[str, bool]:
            return {"ok": True}

        def insert_before(self, *args: Any) -> dict[str, bool]:
            return {"ok": True}

        def insert_after(self, *args: Any) -> dict[str, bool]:
            return {"ok": True}

    monkeypatch.setattr(entrypoint, "_edit_service", lambda path: _Edit())
    body = tmp_path / "body.txt"
    body.write_text("replacement", encoding="utf-8")
    entrypoint.edit_rename("a.py", "A", "B", tmp_path)
    entrypoint.edit_replace("a.py", "A", body, tmp_path)
    entrypoint.edit_insert_before("a.py", "A", body, tmp_path)
    entrypoint.edit_insert_after("a.py", "A", body, tmp_path)

    setup_result = SimpleNamespace(index=SimpleNamespace(tracked=2), symbols=3, graph_nodes=4)
    monkeypatch.setattr(
        entrypoint,
        "ProjectSetup",
        lambda root: SimpleNamespace(run=lambda: setup_result),
    )
    monkeypatch.setattr(entrypoint, "_manager", lambda: manager)
    monkeypatch.setattr(entrypoint, "AgentConfigurator", _Configurator)
    entrypoint.bootstrap(tmp_path, install_backends=False, configure_agents=False, strict=False)
    entrypoint.bootstrap(tmp_path, install_backends=True, configure_agents=True, strict=False)
    manager.fail_ensure = True
    with pytest.raises(typer.Exit):
        entrypoint.bootstrap(tmp_path, install_backends=True, configure_agents=False, strict=True)
