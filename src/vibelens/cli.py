"""CLI entry point for VibeLens."""

from pathlib import Path

import typer
import uvicorn

from vibelens import __version__
from vibelens.config import load_settings
from vibelens.utils.log import setup_file_logging

app = typer.Typer(name="vibelens", help="Agent Trajectory analysis and visualization platform.")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind host"),
    port: int | None = typer.Option(None, help="Bind port"),
    config: Path | None = typer.Option(None, help="Path to YAML config file"),  # noqa: B008
) -> None:
    """Start the VibeLens server."""
    settings = load_settings(config_path=config)
    bind_host = host or settings.host
    bind_port = port or settings.port

    log_file = setup_file_logging()
    typer.echo(f"VibeLens v{__version__}")
    typer.echo(f"Log file: {log_file}")
    typer.echo(f"VibeLens running at http://{bind_host}:{bind_port}")

    uvicorn.run(
        "vibelens.app:create_app", factory=True, host=bind_host, port=bind_port, reload=False
    )


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(f"vibelens {__version__}")
