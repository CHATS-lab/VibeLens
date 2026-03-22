"""CLI entry point for VibeLens."""

import threading
import webbrowser
from pathlib import Path

import typer
import uvicorn

from vibelens import __version__
from vibelens.config import load_settings

BROWSER_OPEN_DELAY_SECONDS = 1.5

app = typer.Typer(name="vibelens", help="Agent Trajectory analysis and visualization platform.")


def _open_browser(url: str) -> None:
    """Open the given URL in the default browser."""
    webbrowser.open(url)


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind host"),
    port: int | None = typer.Option(None, help="Bind port"),
    config: Path | None = typer.Option(None, help="Path to YAML config file"),  # noqa: B008
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open browser on startup"),
) -> None:
    """Start the VibeLens server."""
    settings = load_settings(config_path=config)
    bind_host = host or settings.host
    bind_port = port or settings.port

    typer.echo(f"VibeLens v{__version__}")
    typer.echo(f"VibeLens running at http://{bind_host}:{bind_port}")

    if open_browser:
        url = f"http://{bind_host}:{bind_port}"
        timer = threading.Timer(BROWSER_OPEN_DELAY_SECONDS, _open_browser, args=[url])
        timer.daemon = True
        timer.start()

    uvicorn.run(
        "vibelens.app:create_app", factory=True, host=bind_host, port=bind_port, reload=False
    )


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(f"vibelens {__version__}")
