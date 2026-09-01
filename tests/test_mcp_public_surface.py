from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codecortex.architecture import ArchitectureDriftDetector
from codecortex.mcp.server import MCPApplication, MCPServer, PROTOCOL_VERSION
from codecortex.memory import TeamMemoryStore
from codecortex.runtime import build_runtime
from codecortex.workspace import MultiRepositoryWorkspace


def _git_project(tmp_path: Path) -> Path:
    root = tmp_path / "mcp-project"
    root.mkdir()
    (root / "service.py").write_text(
        "class Service:\n"
        "    def run(self, value: int) -> int:\n"
        "        return helper(value)\n\n"
        "def helper(value: int) -> int:\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    (root / "test_service.py").write_text(
        "from service import Service\n\ndef test_service():\n    assert Service().run(1) == 2\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CodeCortex CI"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    return root


@pytest.mark.asyncio
async def test_native_mcp_tools_end_to_end(tmp_path: Path) -> None:
    root = _git_project(tmp_path)
    runtime = build_runtime(root)
    application = MCPApplication(runtime)

    names = {tool["name"] for tool in application.tools()}
    assert {"cortex_repository_map", "cortex_context", "cortex_stats"} <= names

    assert (await application.call("cortex_repository_map", {"query": "Service"}))["counts"]
    assert "symbols" in await application.call("cortex_find_symbol", {"query": "Service"})
    assert "nodes" in await application.call("cortex_find_references", {"query": "Service"})
    assert "edges" in await application.call("cortex_dependency_graph", {"query": "Service"})
    impact = await application.call("cortex_impact", {"query": "Service"})
    assert "risk_score" in impact
    semantic = await application.call("cortex_semantic_search", {"query": "helper", "limit": 5})
    assert "hits" in semantic

    context = await application.call("cortex_context", {"query": "understand Service", "budget": 1024})
    assert "metrics" in context
    architecture = await application.call("cortex_architecture", {})
    assert architecture
    missing_drift = await application.call("cortex_architecture_drift", {})
    assert missing_drift["baseline"] == "missing"
    baseline = root / ".codecortex" / "architecture" / "baseline.json"
    ArchitectureDriftDetector().fingerprint(application._graph()).save(baseline)
    drift = await application.call("cortex_architecture_drift", {})
    assert "drift" in drift

    history = await application.call(
        "cortex_symbol_history", {"path": "service.py", "start": 1, "end": 3}
    )
    assert history
    pr = await application.call(
        "cortex_pr_intelligence", {"base_ref": "HEAD", "head_ref": "HEAD"}
    )
    assert pr["base_ref"] == "HEAD"

    assert (await application.call("cortex_remember", {"key": "decision", "value": "stable"}))["saved"]
    memory = await application.call("cortex_memory_search", {"query": "stable"})
    assert "results" in memory

    team = TeamMemoryStore(root / ".codecortex" / "memory" / "team.sqlite3")
    team.put_entry("project", "rule", "keep interfaces stable", actor="test")
    team_results = await application.call(
        "cortex_team_memory_search", {"query": "stable", "namespace": "project"}
    )
    assert team_results["results"]

    workspace = MultiRepositoryWorkspace(root / ".codecortex" / "workspace.json")
    workspace.add_repository("self", root)
    workspace_hits = await application.call("cortex_workspace_search", {"query": "Service", "limit": 10})
    assert "hits" in workspace_hits

    validation = await application.call("cortex_validate", {"query": "validate Service"})
    assert "validation" in validation
    stats = await application.call("cortex_stats", {})
    assert stats["index"]["tracked"] >= 2

    trace_id = context.get("trace_id") or validation.get("trace_id")
    if trace_id:
        summary = await application.call("cortex_trace_summary", {"trace_id": trace_id})
        assert summary

    with pytest.raises(KeyError):
        await application.call("unknown", {})


@pytest.mark.asyncio
async def test_mcp_dispatch_protocol(tmp_path: Path) -> None:
    root = _git_project(tmp_path)
    server = MCPServer(MCPApplication(build_runtime(root)))

    assert await server.dispatch({"method": "ping"}) is None
    discovered = await server.dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        }
    )
    assert discovered and discovered["result"]["protocolVersion"] == PROTOCOL_VERSION
    pong = await server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert pong == {"jsonrpc": "2.0", "id": 2, "result": {}}
    listed = await server.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert listed and listed["result"]["tools"]
    called = await server.dispatch(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "cortex_repository_map", "arguments": {"query": "Service"}},
        }
    )
    assert called and called["result"]["structuredContent"]
    bad_method = await server.dispatch({"jsonrpc": "2.0", "id": 5, "method": "nope"})
    assert bad_method and bad_method["error"]["code"] == -32601
    bad_tool = await server.dispatch(
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "nope"}}
    )
    assert bad_tool and bad_tool["error"]["code"] == -32602
