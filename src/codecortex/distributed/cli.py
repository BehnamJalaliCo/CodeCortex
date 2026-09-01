"""CLI entrypoint for the hosted distributed CodeCortex service."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from codecortex.distributed.organization import OrganizationPolicyStore
from codecortex.distributed.remote_mcp import BearerTokenAuthenticator, RemoteAccessPolicy, RemoteMCPServer, RemoteMCPSettings
from codecortex.distributed.service import DistributedMCPApplication
from codecortex.runtime import build_runtime

app = typer.Typer(add_completion=False, help="Run the authenticated CodeCortex remote MCP service.")
console = Console()


@app.callback(invoke_without_command=True)
def serve(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
    token: Annotated[str, typer.Option("--token", envvar="CODECORTEX_REMOTE_TOKEN", help="Bearer token")] = "",
    principal: Annotated[str, typer.Option("--principal", help="Authenticated principal name")] = "agent",
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
    node_id: Annotated[str, typer.Option("--node-id")] = "coordinator-1",
    tls_cert: Annotated[Path | None, typer.Option("--tls-cert")] = None,
    tls_key: Annotated[Path | None, typer.Option("--tls-key")] = None,
    quota: Annotated[int, typer.Option("--requests-per-minute")] = 120,
    allow_mutations: Annotated[bool, typer.Option("--allow-mutations")] = False,
    organization: Annotated[str, typer.Option("--organization")] = "",
    workspace: Annotated[str, typer.Option("--workspace")] = "",
    policy_db: Annotated[Path | None, typer.Option("--policy-db")] = None,
) -> None:
    if not token:
        raise typer.BadParameter("--token or CODECORTEX_REMOTE_TOKEN is required")
    if not principal.strip():
        raise typer.BadParameter("--principal is required")
    if bool(organization) != bool(workspace):
        raise typer.BadParameter("--organization and --workspace must be configured together")
    runtime = build_runtime(path.expanduser().resolve())
    application = DistributedMCPApplication(runtime, node_id=node_id)
    tools = frozenset(str(item["name"]) for item in application.tools())
    mutating = frozenset({"cortex_remember", "cortex_sync_push", "cortex_worker_register", "cortex_worker_claim", "cortex_worker_complete"})
    authorizer = None
    if organization and workspace:
        store = OrganizationPolicyStore((policy_db or runtime.config.state_dir / "distributed" / "organization.db").expanduser().resolve())
        authorizer = lambda actor, tool: store.authorize_tool(organization, workspace, actor, tool, remote=True)
    settings = RemoteMCPSettings(host=host, port=port, tls_cert=None if tls_cert is None else str(tls_cert.expanduser().resolve()), tls_key=None if tls_key is None else str(tls_key.expanduser().resolve()), max_requests_per_minute=quota)

    async def dispatch(tool: str, arguments: dict[str, object], actor: str):
        return await application.call_as(actor, tool, dict(arguments))

    server = RemoteMCPServer(
        dispatch,
        BearerTokenAuthenticator({principal: token}),
        RemoteAccessPolicy(allowed_tools={principal: tools}, mutating_tools=mutating, mutation_principals=frozenset({principal}) if allow_mutations else frozenset(), authorizer=authorizer),
        settings,
    )
    scheme = "https" if settings.tls_cert else "http"
    console.print(f"CodeCortex remote MCP listening on {scheme}://{host}:{port}/mcp as node {node_id} for principal {principal}")
    try:
        server.start(background=False)
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.close()
