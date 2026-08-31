from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from codecortex.backends.base import ManagedAdapterMixin
from codecortex.backends.context import ContextBackendAdapter
from codecortex.backends.contracts import BackendCompatibilityError
from codecortex.backends.graph import GraphBackendAdapter
from codecortex.backends.pool import BackendSessionPool
from codecortex.backends.symbols import SymbolBackendAdapter
from codecortex.context.integrated import IntegratedContextProcessor
from codecortex.core.models import AgentRequest, ContextChunk, RequestKind
from codecortex.engines.builtin.validation import ValidationEngine
from codecortex.interfaces.mcp_bridge import MCPBridge


class _Dump:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


class _Gateway:
    def route(self, query: str) -> _Dump:
        return _Dump({"route": query})

    async def query(self, query: str) -> _Dump:
        return _Dump({"query": query})

    async def remember(self, key: str, value: str) -> None:
        self.remembered = (key, value)

    async def health(self) -> dict[str, Any]:
        return {"healthy": True}


@pytest.mark.asyncio
async def test_protocol_bridge_definitions_and_calls() -> None:
    gateway = _Gateway()
    bridge = MCPBridge(gateway)  # type: ignore[arg-type]
    assert {item["name"] for item in bridge.tool_definitions()} == {
        "cortex_route",
        "cortex_query",
        "cortex_remember",
        "cortex_health",
    }
    assert await bridge.call("cortex_route", {"query": "map"}) == {"route": "map"}
    assert await bridge.call("cortex_query", {"query": "find"}) == {"query": "find"}
    assert await bridge.call("cortex_remember", {"key": "k", "value": "v"}) == {
        "saved": True
    }
    assert gateway.remembered == ("k", "v")
    assert await bridge.call("cortex_health", {}) == {"healthy": True}
    with pytest.raises(KeyError, match="Unknown tool"):
        await bridge.call("missing", {})


@pytest.mark.asyncio
async def test_validation_engine_reports_syntax_and_limits(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    hidden = tmp_path / ".venv"
    hidden.mkdir()
    (hidden / "ignored.py").write_text("def broken(:\n", encoding="utf-8")

    engine = ValidationEngine(tmp_path)
    assert await engine.health()
    result = await engine.execute(AgentRequest(query="validate"))
    assert "bad.py" in result.content
    assert result.metadata == {"checked": 2, "issues": 1}

    limited = ValidationEngine(tmp_path, max_files=0)
    assert (await limited.execute(AgentRequest(query="validate"))).content == (
        "Python syntax validation passed."
    )
    assert not await ValidationEngine(tmp_path / "missing").health()


class _CompressionBackend:
    def __init__(
        self,
        *,
        healthy: bool = True,
        payloads: list[dict[str, Any]] | None = None,
    ) -> None:
        self.healthy = healthy
        self.payloads = payloads or []
        self.spec = SimpleNamespace(key="compressor", revision="rev")

    async def health(self) -> bool:
        return self.healthy

    def compress_batch(self, contents: list[str]) -> list[dict[str, Any]]:
        assert contents
        return self.payloads


@pytest.mark.asyncio
async def test_integrated_context_fallbacks_and_compression() -> None:
    chunks = [ContextChunk(source="a", content="A" * 800, tokens=800, relevance=1.0)]
    assert (await IntegratedContextProcessor(None).fit(chunks, 1000))[0].content == chunks[0].content

    unhealthy = IntegratedContextProcessor(
        _CompressionBackend(healthy=False), compression_threshold=100  # type: ignore[arg-type]
    )
    assert (await unhealthy.fit(chunks, 1000))[0].content == chunks[0].content

    short = [ContextChunk(source="s", content="small", tokens=5, relevance=1.0)]
    healthy = IntegratedContextProcessor(
        _CompressionBackend(), compression_threshold=100  # type: ignore[arg-type]
    )
    assert (await healthy.fit(short, 1000))[0].content == "small"

    backend = _CompressionBackend(
        payloads=[{"content": [{"type": "text", "text": "tiny"}]}]
    )
    compressed = await IntegratedContextProcessor(
        backend, compression_threshold=100  # type: ignore[arg-type]
    ).fit(chunks, 1000)
    assert compressed[0].content == "tiny"
    assert compressed[0].metadata["compressed"] is True
    assert compressed[0].metadata["original_tokens"] == 800

    no_gain = _CompressionBackend(
        payloads=[{"content": [{"type": "text", "text": "B" * 4000}]}]
    )
    unchanged = await IntegratedContextProcessor(
        no_gain, compression_threshold=100  # type: ignore[arg-type]
    ).fit(chunks, 1000)
    assert unchanged[0].content == chunks[0].content

    empty = _CompressionBackend(payloads=[{"content": []}])
    unchanged = await IntegratedContextProcessor(
        empty, compression_threshold=100  # type: ignore[arg-type]
    ).fit(chunks, 1000)
    assert unchanged[0].content == chunks[0].content

    class _Broken(_CompressionBackend):
        def compress_batch(self, contents: list[str]) -> list[dict[str, Any]]:
            raise RuntimeError("boom")

    fallback = await IntegratedContextProcessor(
        _Broken(), compression_threshold=100  # type: ignore[arg-type]
    ).fit(chunks, 1000)
    assert fallback[0].content == chunks[0].content


class _Manager:
    def __init__(self) -> None:
        self.installed = True
        self.healthy = True
        self.calls: list[tuple[Any, ...]] = []

    def is_installed(self, spec: Any) -> bool:
        return self.installed

    def probe(self, spec: Any, provision: bool = False) -> bool:
        self.calls.append(("probe", spec.key, provision))
        return self.healthy

    def run(self, spec: Any, args: tuple[str, ...], **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("run", spec.key, args, kwargs))
        return SimpleNamespace(stdout=" result \n")


class _Managed(ManagedAdapterMixin):
    def __init__(self, manager: _Manager) -> None:
        self.manager = manager  # type: ignore[assignment]
        self.spec = SimpleNamespace(key="x", revision="r", capabilities=("a",))  # type: ignore[assignment]


def test_managed_adapter_status_and_contract() -> None:
    manager = _Manager()
    adapter = _Managed(manager)
    status = adapter.status()
    assert status.installed and status.healthy and status.key == "x"
    manager.installed = False
    status = adapter.status()
    assert not status.installed and not status.healthy
    ManagedAdapterMixin.require_tools([{"name": "a"}, {"name": 3}], {"a"})
    with pytest.raises(BackendCompatibilityError, match="missing: b"):
        ManagedAdapterMixin.require_tools([{"name": "a"}], {"a", "b"})


@pytest.mark.asyncio
async def test_graph_adapter_build_queries_paths_and_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _Manager()
    adapter = GraphBackendAdapter(tmp_path, manager)  # type: ignore[arg-type]
    assert await adapter.health()
    graph_path = tmp_path / ".codecortex" / "backends" / "graph.json"
    graph_path.parent.mkdir(parents=True)
    graph_path.write_text('{"nodes": [1]}', encoding="utf-8")
    assert adapter.build() == {"nodes": [1]}
    assert adapter.query("q") == "result"
    assert adapter.explain("n") == "result"
    assert adapter.path("a", "b") == "result"

    monkeypatch.setenv("CODECORTEX_GRAPH_BACKEND_OUTPUT", "../outside.json")
    with pytest.raises(ValueError, match="inside the project root"):
        adapter._graph_path()
    monkeypatch.delenv("CODECORTEX_GRAPH_BACKEND_OUTPUT")

    graph_path.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid graph payload"):
        adapter.build()
    graph_path.unlink()
    with pytest.raises(RuntimeError, match="without its configured graph payload"):
        adapter.build()

    monkeypatch.setattr(adapter, "query", lambda query: f"query:{query}")
    monkeypatch.setattr(adapter, "explain", lambda node: f"explain:{node}")
    monkeypatch.setattr(adapter, "path", lambda source, target: f"path:{source}:{target}")
    monkeypatch.setattr(adapter, "build", lambda: {"ok": True})
    cases = [
        (AgentRequest(query="q"), "query:q"),
        (AgentRequest(query="x", metadata={"graph_mode": "explain"}), "explain:x"),
        (
            AgentRequest(query="a", metadata={"graph_mode": "path", "target": "b"}),
            "path:a:b",
        ),
        (AgentRequest(query="x", metadata={"graph_mode": "build"}), '{"ok": true}'),
    ]
    for request, expected in cases:
        assert (await adapter.execute(request)).content == expected
    with pytest.raises(ValueError, match="metadata.target"):
        await adapter.execute(AgentRequest(query="a", metadata={"graph_mode": "path"}))


class _Pool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.catalog: list[dict[str, Any]] = []

    def tools(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return self.catalog

    def call_tool(
        self,
        spec: Any,
        args: Any,
        name: str,
        arguments: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = dict(arguments or {})
        self.calls.append((name, payload))
        return {
            "content": [{"type": "text", "text": f"{name}-ok"}],
            "structuredContent": {"ratio": 0.5},
        }


def test_context_backend_surface_and_execute(tmp_path: Path) -> None:
    manager = _Manager()
    adapter = ContextBackendAdapter(tmp_path, manager)  # type: ignore[arg-type]
    pool = _Pool()
    pool.catalog = [{"name": name} for name in adapter.required_tools]
    adapter.pool = pool  # type: ignore[assignment]
    assert adapter.server_args() == ("mcp", "serve", "--transport", "stdio")
    assert Path(adapter._env()["CODECORTEX_CONTEXT_WORKSPACE_DIR"]).is_dir()
    assert len(adapter.tools()) == 3
    assert adapter.compress("hello")["structuredContent"]["ratio"] == 0.5
    assert len(adapter.compress_batch(["a", "b"])) == 2
    adapter.retrieve("hash")
    adapter.stats()
    result = adapter._execute_sync(AgentRequest(query="hello"))
    assert result.content == "context_compress-ok"
    assert result.metadata["compression"] == {"ratio": 0.5}
    explicit = adapter._execute_sync(
        AgentRequest(
            query="x",
            metadata={"context_tool": "context_stats", "context_arguments": {"a": 1}},
        )
    )
    assert explicit.metadata["tool"] == "context_stats"
    pool.catalog = []
    with pytest.raises(BackendCompatibilityError):
        adapter.tools()


@pytest.mark.asyncio
async def test_context_backend_health_and_async_execute(tmp_path: Path) -> None:
    manager = _Manager()
    adapter = ContextBackendAdapter(tmp_path, manager)  # type: ignore[arg-type]
    adapter.pool = _Pool()  # type: ignore[assignment]
    assert await adapter.health()
    assert (await adapter.execute(AgentRequest(query="hello"))).content == "context_compress-ok"


def test_symbol_backend_planning_edits_and_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "a.py"
    source.write_text("def f():\n    pass\n", encoding="utf-8")
    manager = _Manager()
    adapter = SymbolBackendAdapter(tmp_path, manager)  # type: ignore[arg-type]
    pool = _Pool()
    pool.catalog = [
        {"name": name} for name in adapter.required_tools | adapter.editing_tools
    ]
    adapter.pool = pool  # type: ignore[assignment]
    assert "start-mcp-server" in adapter.server_args()
    assert adapter._relative_path("a.py") == "a.py"
    with pytest.raises(ValueError, match="does not exist"):
        adapter._relative_path("missing.py")
    folder = tmp_path / "folder"
    folder.mkdir()
    with pytest.raises(ValueError, match="expected a file"):
        adapter._relative_path("folder")
    with pytest.raises(ValueError, match="inside the project root"):
        adapter._relative_path("../escape.py")

    adapter.preflight_symbol("f", "a.py")
    adapter.rename_symbol("f", "a.py", "g")
    adapter.replace_symbol_body("f", "a.py", "def f():\n    return 1")
    adapter.insert_before_symbol("f", "a.py", "# before")
    adapter.insert_after_symbol("f", "a.py", "# after")
    assert {name for name, _ in pool.calls} >= adapter.editing_tools
    with pytest.raises(ValueError, match="new_name"):
        adapter.rename_symbol("f", "a.py", " ")
    with pytest.raises(ValueError, match="replacement body"):
        adapter.replace_symbol_body("f", "a.py", " ")

    pool.catalog = [{"name": "find_symbol"}, {"name": "find_referencing_symbols"}]
    with pytest.raises(RuntimeError, match="required edit tool"):
        adapter.rename_symbol("f", "a.py", "g")

    tool, args = adapter._plan(
        AgentRequest(
            query="f", kind=RequestKind.REFACTOR, metadata={"relative_path": "a.py"}
        )
    )
    assert tool == "find_symbol" and args["include_body"] is True
    tool, args = adapter._plan(
        AgentRequest(query="f", metadata={"references": True, "relative_path": "a.py"})
    )
    assert tool == "find_referencing_symbols" and args["relative_path"] == "a.py"
    tool, args = adapter._plan(AgentRequest(query="f", kind=RequestKind.DEBUG))
    assert tool == "find_symbol" and args["include_body"] is True

    pool.catalog = [{"name": name} for name in adapter.required_tools]
    assert adapter._execute_sync(AgentRequest(query="f")).content == "find_symbol-ok"
    explicit = adapter._execute_sync(
        AgentRequest(
            query="f",
            metadata={"symbol_tool": "find_symbol", "symbol_arguments": {"depth": 2}},
        )
    )
    assert explicit.metadata["tool"] == "find_symbol"
    monkeypatch.setattr(adapter, "call", lambda tool, arguments: {})
    fallback = adapter._execute_sync(AgentRequest(query="f"))
    assert fallback.content == "{}"
    assert len(fallback.chunks) == 1


@pytest.mark.asyncio
async def test_symbol_backend_health_and_async_execute(tmp_path: Path) -> None:
    manager = _Manager()
    adapter = SymbolBackendAdapter(tmp_path, manager)  # type: ignore[arg-type]
    adapter.pool = _Pool()  # type: ignore[assignment]
    assert await adapter.health()
    assert (await adapter.execute(AgentRequest(query="f"))).content == "find_symbol-ok"


class _FakeClient:
    instances: list[_FakeClient] = []
    fail_calls = 0
    fail_tools = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.closed = False
        self.started = False
        _FakeClient.instances.append(self)

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True

    def call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        if _FakeClient.fail_calls:
            _FakeClient.fail_calls -= 1
            raise RuntimeError("retry")
        return {"name": name, "arguments": arguments}

    def tools(self) -> list[dict[str, Any]]:
        if _FakeClient.fail_tools:
            _FakeClient.fail_tools -= 1
            raise RuntimeError("retry tools")
        return [{"name": "ok"}]


def test_backend_session_pool_reuse_retry_tools_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import codecortex.backends.pool as pool_module

    _FakeClient.instances.clear()
    _FakeClient.fail_calls = 0
    _FakeClient.fail_tools = 0
    monkeypatch.setattr(pool_module, "MCPStdioClient", _FakeClient)
    pool = BackendSessionPool(object())  # type: ignore[arg-type]
    spec = SimpleNamespace(key="x", revision="r")

    key1 = pool._key(spec, ("serve",), tmp_path, {"B": "2", "A": "1"})  # type: ignore[arg-type]
    key2 = pool._key(spec, ("serve",), tmp_path, {"A": "1", "B": "2"})  # type: ignore[arg-type]
    assert key1 == key2
    assert pool.call_tool(  # type: ignore[arg-type]
        spec, ("serve",), "ping", {"x": 1}, cwd=tmp_path
    ) == {"name": "ping", "arguments": {"x": 1}}
    assert len(_FakeClient.instances) == 1
    pool.call_tool(spec, ("serve",), "ping", {}, cwd=tmp_path)  # type: ignore[arg-type]
    assert len(_FakeClient.instances) == 1

    _FakeClient.fail_calls = 1
    result = pool.call_tool(spec, ("serve2",), "retry", {}, cwd=tmp_path)  # type: ignore[arg-type]
    assert result["name"] == "retry"
    assert _FakeClient.instances[-2].closed

    _FakeClient.fail_calls = 2
    with pytest.raises(RuntimeError, match="retry"):
        pool.call_tool(spec, ("serve3",), "fail", {}, cwd=tmp_path)  # type: ignore[arg-type]

    _FakeClient.fail_tools = 1
    assert pool.tools(spec, ("tools",), cwd=tmp_path) == [{"name": "ok"}]  # type: ignore[arg-type]
    pool.close_all()
    assert not pool._sessions
    assert all(client.closed for client in _FakeClient.instances)
