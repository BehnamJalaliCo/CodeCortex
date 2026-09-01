import asyncio

from codecortex.distributed.remote_mcp import (
    BearerTokenAuthenticator,
    RemoteAccessPolicy,
    RemoteMCPServer,
)
from codecortex.mcp.server import MCPApplication, MCPServer
from codecortex.runtime import build_runtime


def test_native_mcp_rejects_unknown_arguments(tmp_path) -> None:
    server = MCPServer(MCPApplication(build_runtime(tmp_path)))
    response = asyncio.run(
        server.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "cortex_find_symbol",
                    "arguments": {"query": "x", "unexpected": True},
                },
            }
        )
    )
    assert response is not None
    assert response["error"]["code"] == -32602


def test_initialize_negotiates_only_supported_protocols(tmp_path) -> None:
    server = MCPServer(MCPApplication(build_runtime(tmp_path)))
    ok = asyncio.run(
        server.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
    )
    assert ok and ok["result"]["protocolVersion"] == "2025-06-18"
    bad = asyncio.run(
        server.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {"protocolVersion": "1900-01-01"},
            }
        )
    )
    assert bad and bad["error"]["code"] == -32602


def test_remote_mutations_require_explicit_opt_in() -> None:
    async def dispatcher(tool, arguments):
        del tool, arguments
        raise RuntimeError("secret-detail")

    server = RemoteMCPServer(
        dispatcher,
        BearerTokenAuthenticator({"agent": "token"}),
        RemoteAccessPolicy(
            allowed_tools={"agent": frozenset({"read", "write"})},
            mutating_tools=frozenset({"write"}),
        ),
    )
    assert server.handle_call(
        "Bearer token", {"tool": "write", "arguments": {}}
    )[0] == 403
    status, payload = server.handle_call(
        "Bearer token", {"tool": "read", "arguments": {}}
    )
    assert status == 500
    assert "secret-detail" not in str(payload)
    assert "error_id" in payload
