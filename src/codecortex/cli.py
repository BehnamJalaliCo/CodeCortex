"""CodeCortex command-line interface."""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from codecortex.architecture import (
    ArchitectureDriftDetector,
    ArchitectureFingerprint,
    ArchitectureInferenceEngine,
)
from codecortex.benchmark import BenchmarkSuite, CodeCortexGraphStrategy, FullTextBaseline
from codecortex.dashboard import run_dashboard
from codecortex.evaluation import (
    BenchmarkHistory,
    ExternalEvaluationSuite,
    RegressionGate,
    SubprocessEvaluationTarget,
)
from codecortex.git_intelligence import GitIntelligence
from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.mcp.server import run_stdio
from codecortex.memory import TeamMemoryStore
from codecortex.memory.knowledge import ProjectKnowledgeExtractor
from codecortex.pr_intelligence import PRIntelligence
from codecortex.retrieval import RepositorySemanticIndex
from codecortex.runtime import build_runtime
from codecortex.setup import ProjectSetup
from codecortex.tracing import TaskTraceRecorder
from codecortex.workspace import MultiRepositoryWorkspace

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _root(path: Path) -> Path:
    return path.expanduser().resolve()


def _graph(root: Path):
    return IncrementalGraphIndex(root).refresh()[0]


@app.command()
def init(path: Annotated[Path, typer.Argument(help="Project directory")] = Path(".")) -> None:
    result = ProjectSetup(_root(path)).run()
    console.print("[bold green]CodeCortex ready.[/bold green]")
    console.print_json(
        data={
            "tracked_files": result.index.tracked,
            "symbols": result.symbols,
            "graph_nodes": result.graph_nodes,
            "graph_edges": result.graph_edges,
            "languages": list(result.languages),
            "detected_agents": list(result.detected_agents),
        }
    )


@app.command("index")
def index_command(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
    graph, stats = IncrementalGraphIndex(_root(path)).refresh()
    console.print_json(
        data={
            "tracked": stats.index.tracked,
            "added": len(stats.index.added),
            "changed": len(stats.index.changed),
            "removed": len(stats.index.removed),
            "files_reparsed": stats.files_reparsed,
            "full_rebuild": stats.full_rebuild,
            "graph_nodes": len(graph.nodes),
            "graph_edges": len(graph.edges),
        }
    )


@app.command()
def semantic(
    query: Annotated[str, typer.Argument(help="Semantic repository query")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
) -> None:
    semantic_index = RepositorySemanticIndex(_root(path))
    semantic_index.refresh()
    console.print_json(
        data={
            "hits": [
                {
                    "id": hit.document.id,
                    "score": hit.score,
                    "vector_score": hit.vector_score,
                    "lexical_score": hit.lexical_score,
                    "structural_score": hit.structural_score,
                    "metadata": hit.document.metadata,
                }
                for hit in semantic_index.search(query, limit)
            ]
        }
    )


@app.command()
def architecture(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
    report = ArchitectureInferenceEngine().analyze(_graph(_root(path)))
    console.print_json(data=asdict(report))


@app.command("architecture-baseline")
def architecture_baseline(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    root = _root(path)
    target = root / ".codecortex" / "architecture" / "baseline.json"
    ArchitectureDriftDetector().fingerprint(_graph(root)).save(target)
    console.print(f"Saved: {target}")


@app.command("architecture-drift")
def architecture_drift(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    root = _root(path)
    target = root / ".codecortex" / "architecture" / "baseline.json"
    baseline = ArchitectureFingerprint.load(target)
    detector = ArchitectureDriftDetector()
    current = detector.fingerprint(_graph(root))
    if baseline is None:
        current.save(target)
        console.print("Baseline created; no prior baseline existed.")
        return
    report = detector.compare(baseline, current)
    console.print_json(data=asdict(report))
    if report.drifted and report.score >= 0.70:
        raise typer.Exit(code=2)


@app.command("symbol-history")
def symbol_history(
    target: Annotated[str, typer.Argument(help="Repository-relative path")],
    start: Annotated[int, typer.Argument(help="Start line")],
    end: Annotated[int, typer.Argument(help="End line")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    report = GitIntelligence(_root(path)).symbol_history(target, start, end)
    console.print_json(data=asdict(report))


@app.command("pr")
def pr_command(
    base: Annotated[str, typer.Argument(help="Base Git ref")],
    head: Annotated[str, typer.Option("--head")] = "HEAD",
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    root = _root(path)
    report = PRIntelligence(root, _graph(root)).analyze(base, head)
    console.print_json(
        data={
            "base_ref": report.base_ref,
            "head_ref": report.head_ref,
            "risk_score": report.risk_score,
            "risk_level": report.risk_level,
            "affected_tests": list(report.affected_tests),
            "files": [asdict(item) for item in report.files],
            "symbols": [
                {
                    "node": item.node.model_dump(mode="json"),
                    "impact_risk": item.impact_risk,
                    "affected_nodes": item.affected_nodes,
                    "affected_tests": item.affected_tests,
                }
                for item in report.symbols
            ],
        }
    )


@app.command("team-remember")
def team_remember(
    key: Annotated[str, typer.Argument()],
    value: Annotated[str, typer.Argument()],
    actor: Annotated[str, typer.Option("--actor")] = "user",
    namespace: Annotated[str, typer.Option("--namespace")] = "project",
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    store = TeamMemoryStore(_root(path) / ".codecortex" / "memory" / "team.sqlite3")
    entry = store.put_entry(namespace, key, value, actor=actor)
    console.print_json(data=asdict(entry))


@app.command("team-search")
def team_search(
    query: Annotated[str, typer.Argument()],
    namespace: Annotated[str, typer.Option("--namespace")] = "project",
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    store = TeamMemoryStore(_root(path) / ".codecortex" / "memory" / "team.sqlite3")
    console.print_json(data=[asdict(item) for item in store.search_entries(namespace, query, 20)])


@app.command("workspace-add")
def workspace_add(
    name: Annotated[str, typer.Argument()],
    repository: Annotated[Path, typer.Argument()],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    workspace = MultiRepositoryWorkspace(_root(path) / ".codecortex" / "workspace.json")
    workspace.add_repository(name, repository)
    console.print(f"Added {name}: {_root(repository)}")


@app.command("workspace-search")
def workspace_search(
    query: Annotated[str, typer.Argument()],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    workspace = MultiRepositoryWorkspace(_root(path) / ".codecortex" / "workspace.json")
    console.print_json(
        data=[
            {
                "repository": hit.repository,
                "score": hit.score,
                "node": hit.node.model_dump(mode="json"),
            }
            for hit in workspace.search(query)
        ]
    )


@app.command("trace-summary")
def trace_summary(
    trace_id: Annotated[str, typer.Argument()],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    recorder = TaskTraceRecorder(_root(path) / ".codecortex" / "runtime" / "traces.jsonl")
    console.print_json(data=asdict(recorder.summarize(trace_id)))


@app.command()
def impact(
    query: Annotated[str, typer.Argument(help="Symbol or file")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    console.print(ImpactAnalyzer(_graph(_root(path))).analyze(query).to_text())


@app.command()
def history(
    target: Annotated[str, typer.Argument(help="Repository path")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    console.print_json(data=GitIntelligence(_root(path)).file_history(target))


@app.command()
def knowledge(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
    console.print_json(data=ProjectKnowledgeExtractor(_root(path)).extract().facts())


@app.command()
def mcp(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
    run_stdio(_root(path))


@app.command()
def benchmark(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
    cases: Annotated[Path, typer.Option("--cases")] = Path("benchmarks/cases.json"),
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("benchmarks/results.json"),
) -> None:
    root = _root(path)
    case_path = cases if cases.is_absolute() else root / cases
    output_path = output if output.is_absolute() else root / output
    suite = BenchmarkSuite.load(
        case_path,
        [FullTextBaseline(root), CodeCortexGraphStrategy(root)],
    )
    report = suite.run()
    report.save(output_path)
    history_store = BenchmarkHistory(root / ".codecortex" / "benchmarks" / "history.json")
    history_store.append(report.summary())
    console.print_json(data=report.summary())
    console.print(f"Saved: {output_path}")


@app.command("benchmark-gate")
def benchmark_gate(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    snapshots = BenchmarkHistory(_root(path) / ".codecortex" / "benchmarks" / "history.json").load()
    if len(snapshots) < 2:
        console.print("At least two benchmark snapshots are required.")
        return
    report = RegressionGate().evaluate(snapshots[-1], snapshots[-2])
    console.print_json(data=asdict(report))
    if not report.passed:
        raise typer.Exit(code=2)


@app.command("evaluate")
def evaluate_command(
    suite: Annotated[Path, typer.Argument(help="Evaluation suite JSON")],
    command: Annotated[str, typer.Argument(help="Quoted external target command")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
    output: Annotated[Path, typer.Option("--output", "-o")] = Path(
        "benchmarks/external/results.json"
    ),
) -> None:
    root = _root(path)
    suite_path = suite if suite.is_absolute() else root / suite
    output_path = output if output.is_absolute() else root / output
    target = SubprocessEvaluationTarget("external", tuple(shlex.split(command)), cwd=root)
    report = asyncio.run(ExternalEvaluationSuite.load(suite_path).run(target))
    report.save(output_path)
    console.print_json(data=report.summary())


@app.command()
def doctor(path: Annotated[Path, typer.Option("--path", "-p")] = Path(".")) -> None:
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
    console.print(
        f"[bold]Context:[/bold] {result.context_tokens}/{result.plan.context_budget} tokens"
    )
    if trace_id := result.metadata.get("trace_id"):
        console.print(f"[bold]Trace:[/bold] {trace_id}")
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
    graph, graph_stats = IncrementalGraphIndex(root).refresh()
    git = GitIntelligence(root).analyze(300)
    console.print_json(
        data={
            "files": graph_stats.index.tracked,
            "graph_nodes": len(graph.nodes),
            "graph_edges": len(graph.edges),
            "graph_counts": graph.counts(),
            "git_commits": git.commits,
            "health": asyncio.run(runtime.gateway.health()),
        }
    )


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
