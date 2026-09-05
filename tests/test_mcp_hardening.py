import asyncio

from codecortex.distributed.remote_mcp import (
    BearerTokenAuthenticator,
    RemoteAccessPolicy,
    RemoteMCPServer,
)
from codecortex.mcp.server import MCPApplication, MCPServer, PROTOCOL_VERSION, SUPPORTED_PROTOCOLS
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


def test_initialize_echoes_supported_protocols(tmp_path) -> None:
    server = MCPServer(MCPApplication(build_runtime(tmp_path)))
    for request_id, version in enumerate(sorted(SUPPORTED_PROTOCOLS), start=1):
        response = asyncio.run(
            server.dispatch(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": {"protocolVersion": version},
                }
            )
        )
        assert response is not None
        assert "error" not in response
        assert response["result"]["protocolVersion"] == version


def test_initialize_negotiates_unknown_and_missing_protocols(tmp_path) -> None:
    server = MCPServer(MCPApplication(build_runtime(tmp_path)))
    requests = (
        {"protocolVersion": "2025-11-25"},
        {"protocolVersion": ""},
        {},
    )
    for request_id, params in enumerate(requests, start=100):
        response = asyncio.run(
            server.dispatch(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": params,
                }
            )
        )
        assert response is not None
        assert "error" not in response
        assert response["result"]["protocolVersion"] == PROTOCOL_VERSION


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
    assert server.handle_call("Bearer token", {"tool": "write", "arguments": {}})[0] == 403
    status, payload = server.handle_call("Bearer token", {"tool": "read", "arguments": {}})
    assert status == 500
    assert "secret-detail" not in str(payload)
    assert "error_id" in payload
