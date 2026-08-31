"""Extended public CLI surface for packaging, backends, agent setup, and edits."""

from __future__ import annotations

from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

import codecortex.cli as cli_module
from codecortex.backends import (
    BACKENDS,
    BackendManager,
    ContextBackendAdapter,
    GraphBackendAdapter,
    SymbolBackendAdapter,
)
from codecortex.cli import app
from codecortex.editing import EditService
from codecortex.integrations import AgentConfigurator, AgentTarget
from codecortex.mcp.extended import run_stdio as extended_run_stdio
from codecortex.runtime import build_runtime
from codecortex.setup import ProjectSetup

cli_module.run_stdio = extended_run_stdio

console = Console()
backend_app = typer.Typer(help="Install and inspect isolated intelligence backends.")
agents_app = typer.Typer(help="Detect and configure coding-agent integrations.")
edit_app = typer.Typer(help="Perform guarded language-server semantic edits.")
app.add_typer(backend_app, name="backend")
app.add_typer(agents_app, name="agents")
app.add_typer(edit_app, name="edit")


def _manager() -> BackendManager:
    return BackendManager(timeout_seconds=1200)


def _targets(value: str) -> tuple[str, ...]:
    if value == "all":
        return tuple(BACKENDS)
    if value not in BACKENDS:
        raise typer.BadParameter(f"expected one of: all, {', '.join(BACKENDS)}")
    return (value,)


def _adapter(key: str, root: Path, manager: BackendManager):
    if key == "graph":
        return GraphBackendAdapter(root, manager)
    if key == "symbols":
        return SymbolBackendAdapter(root, manager)
    if key == "context":
        return ContextBackendAdapter(root, manager)
    raise KeyError(key)


def _edit_service(path: Path) -> EditService:
    return EditService(build_runtime(path.expanduser().resolve()))


@app.command("version")
def version_command() -> None:
    try:
        current = version("codecortex-ai")
    except PackageNotFoundError:
        current = "0+unknown"
    console.print(current)


@backend_app.command("list")
def backend_list() -> None:
    manager = _manager()
    table = Table(title="CodeCortex Backends")
    table.add_column("Backend")
    table.add_column("Installed")
    table.add_column("Revision")
    table.add_column("Capabilities")
    for key, spec in BACKENDS.items():
        table.add_row(
            key,
            "yes" if manager.is_installed(spec) else "no",
            spec.revision[:12],
            ", ".join(spec.capabilities),
        )
    console.print(table)


@backend_app.command("install")
def backend_install(
    target: Annotated[str, typer.Argument(help="graph, symbols, context, or all")] = "all",
) -> None:
    manager = _manager()
    failures: list[str] = []
    for key in _targets(target):
        spec = BACKENDS[key]
        console.print(f"Installing [bold]{key}[/bold] at {spec.revision[:12]}…")
        try:
            command = manager.ensure(spec)
            console.print(f"[green]✓[/green] {key}: {command}")
        except Exception as exc:
            failures.append(key)
            console.print(f"[red]✗[/red] {key}: {type(exc).__name__}: {exc}")
    if failures:
        raise typer.Exit(code=2)


@backend_app.command("doctor")
def backend_doctor(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    root = path.expanduser().resolve()
    manager = _manager()
    table = Table(title="Backend Health")
    table.add_column("Backend")
    table.add_column("Installed")
    table.add_column("Healthy")
    table.add_column("Contract")
    failed = False
    for key in BACKENDS:
        adapter = _adapter(key, root, manager)
        status = adapter.status()
        table.add_row(
            key,
            "yes" if status.installed else "no",
            "yes" if status.healthy else "no",
            f"v{status.contract_version}",
        )
        if status.installed and not status.healthy:
            failed = True
    console.print(table)
    if failed:
        raise typer.Exit(code=2)


@backend_app.command("remove")
def backend_remove(
    target: Annotated[str, typer.Argument(help="graph, symbols, context, or all")],
) -> None:
    manager = _manager()
    for key in _targets(target):
        manager.remove(BACKENDS[key])
        console.print(f"[green]Removed[/green] {key}")


@agents_app.command("detect")
def agents_detect(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    found = AgentConfigurator(path).detect()
    if not found:
        console.print("No supported coding agents detected.")
        return
    for target in found:
        console.print(target.value)


@agents_app.command("configure")
def agents_configure(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
    target: Annotated[list[AgentTarget] | None, typer.Option("--target", "-t")] = None,
    all_supported: Annotated[bool, typer.Option("--all")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    configurator = AgentConfigurator(path)
    selected = tuple(AgentTarget) if all_supported else tuple(target or configurator.detect())
    mutations = configurator.configure(selected, dry_run=dry_run)
    for item in mutations:
        state = (
            "would update"
            if dry_run and item.changed
            else "updated"
            if item.changed
            else "unchanged"
        )
        console.print(f"{item.target.value}: {state} {item.path}")
        if item.backup:
            console.print(f"  backup: {item.backup}")


@edit_app.command("rename")
def edit_rename(
    relative_path: Annotated[str, typer.Argument(help="Repository-relative file")],
    name_path: Annotated[str, typer.Argument(help="Semantic symbol name path")],
    new_name: Annotated[str, typer.Argument(help="New symbol name")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    console.print_json(data=_edit_service(path).rename(relative_path, name_path, new_name))


@edit_app.command("replace")
def edit_replace(
    relative_path: Annotated[str, typer.Argument()],
    name_path: Annotated[str, typer.Argument()],
    body_file: Annotated[Path, typer.Option("--body-file")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    body = body_file.read_text(encoding="utf-8")
    console.print_json(data=_edit_service(path).replace(relative_path, name_path, body))


@edit_app.command("insert-before")
def edit_insert_before(
    relative_path: Annotated[str, typer.Argument()],
    name_path: Annotated[str, typer.Argument()],
    body_file: Annotated[Path, typer.Option("--body-file")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    body = body_file.read_text(encoding="utf-8")
    console.print_json(data=_edit_service(path).insert_before(relative_path, name_path, body))


@edit_app.command("insert-after")
def edit_insert_after(
    relative_path: Annotated[str, typer.Argument()],
    name_path: Annotated[str, typer.Argument()],
    body_file: Annotated[Path, typer.Option("--body-file")],
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    body = body_file.read_text(encoding="utf-8")
    console.print_json(data=_edit_service(path).insert_after(relative_path, name_path, body))


@app.command("bootstrap")
def bootstrap(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
    install_backends: Annotated[bool, typer.Option("--backends/--no-backends")] = True,
    configure_agents: Annotated[bool, typer.Option("--agents/--no-agents")] = True,
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    root = path.expanduser().resolve()
    result = ProjectSetup(root).run()
    console.print(
        f"Core ready: {result.index.tracked} files, {result.symbols} symbols, "
        f"{result.graph_nodes} graph nodes."
    )
    failures: list[str] = []
    if install_backends:
        manager = _manager()
        for key, spec in BACKENDS.items():
            try:
                manager.ensure(spec)
                console.print(f"[green]✓[/green] backend {key}")
            except Exception as exc:
                failures.append(key)
                console.print(f"[yellow]![/yellow] backend {key}: {type(exc).__name__}: {exc}")
    if configure_agents:
        configurator = AgentConfigurator(root)
        for mutation in configurator.configure():
            console.print(f"[green]✓[/green] agent {mutation.target.value}: {mutation.path}")
    if strict and failures:
        raise typer.Exit(code=2)


@app.command("backend-status")
def backend_status(
    path: Annotated[Path, typer.Option("--path", "-p")] = Path("."),
) -> None:
    root = path.expanduser().resolve()
    manager = _manager()
    payload = {key: asdict(_adapter(key, root, manager).status()) for key in BACKENDS}
    console.print_json(data=payload)
