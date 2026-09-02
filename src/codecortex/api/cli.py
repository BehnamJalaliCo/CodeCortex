"""CLI entry point for the embedded CodeCortex web API."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(add_completion=False, help="Run the CodeCortex web API.")


@app.callback(invoke_without_command=True)
def serve(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 7340,
    state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter(
            "web dependencies are missing; install codecortex-context-engine[web]"
        ) from exc
    from codecortex.api.app import create_app

    uvicorn.run(create_app(state_dir=state_dir), host=host, port=port)
