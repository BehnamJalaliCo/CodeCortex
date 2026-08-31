"""CLI entrypoint for the hosted distributed CodeCortex service."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from codecortex.distributed.remote_mcp import (
    BearerTokenAuthenticator,
    RemoteAccessPolicy,
    RemoteMCPServer,
    RemoteMCPSettings,
)
from codecortex.distributed.service import DistributedMCPApplication
from codecortex.runtime import build_runtime

app = typer.Typer(add_completion=False, help="Run the authenticated CodeCortex remote MCP service.")
console = Console()


@app.callback(invoke_without_command=True)
def serve(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
    token: Annotated[
        str,
        typer.Option("--token", envvar="CODECORTEX_REMOTE_TOKEN", help="Bearer token"),
    ] = "",
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
    node_id: Annotated[str, typer.Option("--node-id")] = "coordinator-1",
    tls_cert: Annotated[Path | None, typer.Option("--tls-cert")] = None,
    tls_key: Annotated[Path | None, typer.Option("--tls-key")] = None,
    quota: Annotated[int, typer.Option("--requests-per-minute")] = 120,
) -> None:
    """Serve the standard MCP surface plus distributed sync/worker tools."""
    if not token:
        raise typer.BadParameter("--token or CODECORTEX_REMOTE_TOKEN is required")
    runtime = build_runtime(path.expanduser().resolve())
    application = DistributedMCPApplication(runtime, node_id=node_id)
    tools = frozenset(str(item["name"]) for item in application.tools())
    settings = RemoteMCPSettings(
        host=host,
        port=port,
        tls_cert=None if tls_cert is None else str(tls_cert.expanduser().resolve()),
        tls_key=None if tls_key is None else str(tls_key.expanduser().resolve()),
        max_requests_per_minute=quota,
    )
    server = RemoteMCPServer(
        application.call,
        BearerTokenAuthenticator({"agent": token}),
        RemoteAccessPolicy(allowed_tools={"agent": tools}),
        settings,
    )
    scheme = "https" if settings.tls_cert else "http"
    console.print(
        f"CodeCortex remote MCP listening on {scheme}://{host}:{port}/mcp "
        f"as node {node_id} ({len(tools)} tools)"
    )
    try:
        server.start(background=False)
    except KeyboardInterrupt:  # pragma: no cover - interactive service shutdown
        pass
    finally:
        server.close()
