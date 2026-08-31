import pytest

from codecortex.mcp.server import MCPApplication, MCPServer, PROTOCOL_VERSION
from codecortex.runtime import build_runtime


@pytest.mark.asyncio
async def test_mcp_lists_tools_and_supports_discovery(tmp_path):
    server = MCPServer(MCPApplication(build_runtime(tmp_path)))
    discovery = await server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "server/discover"})
    assert discovery["result"]["protocolVersion"] == PROTOCOL_VERSION

    listed = await server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "cortex_impact" in names
    assert "cortex_context" in names
    assert "cortex_stats" in names


@pytest.mark.asyncio
async def test_mcp_can_call_repository_map(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    server = MCPServer(MCPApplication(build_runtime(tmp_path)))
    result = await server.dispatch(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "cortex_repository_map", "arguments": {"query": "run"}},
        }
    )
    assert result["result"]["isError"] is False
    assert result["result"]["structuredContent"]["matches"]
