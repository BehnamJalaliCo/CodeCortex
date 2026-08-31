"""CodeCortex command-line interface."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from codecortex.interfaces.mcp_bridge import MCPBridge
from codecortex.runtime import build_runtime

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _root(path: Path) -> Path:
    return path.expanduser().resolve()


@app.command()
def init(
    path: Annotated[Path, typer.Argument(help="Project directory")] = Path("."),
) -> None:
    """Initialize CodeCortex state for a project."""
    runtime = build_runtime(_root(path))
    config_path = runtime.config.state_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "context_budget": runtime.config.default_context_budget,
                "hard_context_limit": runtime.config.hard_context_limit,
                "telemetry": runtime.config.telemetry_enabled,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    console.print(f"[bold green]CodeCortex initialized[/bold green] at {runtime.config.project_root}")


@app.command()
def doctor(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    """Check engine health."""
    runtime = build_runtime(_root(path))
    health = asyncio.run(runtime.gateway.health())
    table = Table(title="CodeCortex Health")
    table.add_column("Capability")
    table.add_column("Status")
    for capability, status in health.items():
        table.add_row(capability, "OK" if status else "Unavailable")
    console.print(table)


@app.command()
def route(
    query: Annotated[str, typer.Argument(help="Coding request")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    """Show the route selected for a request."""
    runtime = build_runtime(_root(path))
    plan = runtime.gateway.route(query, str(runtime.config.project_root))
    console.print_json(data=plan.model_dump(mode="json"))


@app.command()
def run(
    query: Annotated[str, typer.Argument(help="Coding request")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    """Execute one CodeCortex intelligence request."""
    runtime = build_runtime(_root(path))
    result = asyncio.run(runtime.gateway.query(query, str(runtime.config.project_root)))
    console.print(f"[bold]Route:[/bold] {', '.join(item.value for item in result.plan.selected)}")
    console.print(f"[bold]Context:[/bold] {result.context_tokens}/{result.plan.context_budget} tokens")
    for engine_result in result.results:
        console.rule(engine_result.capability.value)
        console.print(engine_result.content)


@app.command()
def remember(
    key: Annotated[str, typer.Argument()],
    value: Annotated[str, typer.Argument()],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    """Store one project-scoped memory value."""
    runtime = build_runtime(_root(path))
    asyncio.run(runtime.gateway.remember(key, value))
    console.print("[green]Saved.[/green]")


@app.command()
def stats(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    """Show local routing and engine activity."""
    runtime = build_runtime(_root(path))
    event_path = runtime.config.state_dir / "runtime" / "events.jsonl"
    if not event_path.exists():
        console.print("No runtime activity recorded yet.")
        return
    counts: Counter[str] = Counter()
    for line in event_path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        counts[str(payload.get("name", "unknown"))] += 1
    table = Table(title="CodeCortex Stats")
    table.add_column("Event")
    table.add_column("Count", justify="right")
    for name, count in counts.most_common():
        table.add_row(name, str(count))
    console.print(table)


@app.command("mcp-spec")
def mcp_spec(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    """Print the tool contract exposed to MCP-compatible transports."""
    runtime = build_runtime(_root(path))
    bridge = MCPBridge(runtime.gateway)
    console.print_json(data=bridge.tool_definitions())


if __name__ == "__main__":
    app()
