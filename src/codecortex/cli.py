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

from codecortex.dashboard import run_dashboard
from codecortex.git_intelligence import GitIntelligence
from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.indexing.incremental import IncrementalIndex
from codecortex.indexing.indexer import ProjectIndexer
from codecortex.mcp.server import run_stdio
from codecortex.memory.knowledge import ProjectKnowledgeExtractor
from codecortex.runtime import build_runtime
from codecortex.setup import ProjectSetup

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _root(path: Path) -> Path:
    return path.expanduser().resolve()


@app.command()
def init(path: Annotated[Path, typer.Argument(help="Project directory")] = Path(".")) -> None:
    """Initialize and index a project."""
    result = ProjectSetup(_root(path)).run()
    console.print("[bold green]CodeCortex ready.[/bold green]")
    console.print(f"Tracked files: {result.index.tracked}")
    console.print(f"Symbols: {result.symbols}")
    console.print(f"Graph: {result.graph_nodes} nodes / {result.graph_edges} edges")
    console.print(f"Languages: {', '.join(result.languages) or 'not detected'}")
    console.print(f"Agents: {', '.join(result.detected_agents) or 'none detected'}")


@app.command("index")
def index_command(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
    """Update the incremental index and knowledge graph."""
    root = _root(path)
    stats = IncrementalIndex(root).refresh()
    graph = ProjectIndexer(root).build()
    graph.save(root / ".codecortex" / "index" / "graph.json")
    console.print(
        f"Tracked {stats.tracked} | +{len(stats.added)} "
        f"~{len(stats.changed)} -{len(stats.removed)} | {stats.duration_ms:.1f}ms"
    )


@app.command()
def impact(
    query: Annotated[str, typer.Argument(help="Symbol or file")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    """Analyze change impact."""
    report = ImpactAnalyzer(ProjectIndexer(_root(path)).build()).analyze(query)
    console.print(report.to_text())


@app.command()
def history(
    target: Annotated[str, typer.Argument(help="Repository path")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    """Show Git history for one path."""
    rows = GitIntelligence(_root(path)).file_history(target)
    console.print_json(data=rows)


@app.command()
def knowledge(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
    """Extract project knowledge."""
    extracted = ProjectKnowledgeExtractor(_root(path)).extract()
    console.print_json(data=extracted.facts())


@app.command()
def mcp(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
    """Run the native MCP server over stdio."""
    run_stdio(_root(path))


@app.command()
def doctor(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
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
    runtime = build_runtime(_root(path))
    plan = runtime.gateway.route(query, str(runtime.config.project_root))
    console.print_json(data=plan.model_dump(mode="json"))


@app.command()
def run(
    query: Annotated[str, typer.Argument(help="Coding request")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
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
    runtime = build_runtime(_root(path))
    asyncio.run(runtime.gateway.remember(key, value))
    console.print("[green]Saved.[/green]")


@app.command()
def stats(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
    root = _root(path)
    runtime = build_runtime(root)
    graph = ProjectIndexer(root).build()
    git = GitIntelligence(root).analyze(300)
    index_stats = IncrementalIndex(root).refresh()
    console.print_json(data={
        "files": index_stats.tracked,
        "graph_nodes": len(graph.nodes),
        "graph_edges": len(graph.edges),
        "graph_counts": graph.counts(),
        "git_commits": git.commits,
        "health": asyncio.run(runtime.gateway.health()),
    })


@app.command()
def dashboard(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 7331,
) -> None:
    runtime = build_runtime(_root(path))
    console.print(f"Dashboard: http://{host}:{port}")
    run_dashboard(runtime, host=host, port=port)


if __name__ == "__main__":
    app()
