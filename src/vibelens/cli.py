"""CLI entry point for VibeLens."""

import threading
import webbrowser
from pathlib import Path

import typer
import uvicorn

from vibelens import __version__
from vibelens.config import load_settings

# Wait for the server to bind before opening the browser
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


@app.command()
def update_catalog(
    check: bool = typer.Option(False, "--check", help="Check version without downloading"),
) -> None:
    """Download the latest catalog from the update URL."""
    settings = load_settings()
    if not settings.catalog_update_url:
        typer.echo("No catalog_update_url configured. Set it in your vibelens.yaml or environment.")
        raise typer.Exit(code=1)

    if check:
        typer.echo(f"Catalog update URL: {settings.catalog_update_url}")
        typer.echo("Version check not yet implemented (requires catalog loader).")
        raise typer.Exit()

    typer.echo("Catalog download not yet implemented (requires HTTP client).")
    raise typer.Exit(code=1)


@app.command()
def build_catalog(
    github_token: str = typer.Option("", "--github-token", help="GitHub personal access token"),
    output: str = typer.Option("catalog.json", "--output", help="Output file path"),
) -> None:
    """Build catalog.json by crawling GitHub (requires --github-token)."""
    if not github_token:
        typer.echo("Error: --github-token is required for catalog builds.")
        typer.echo("Usage: vibelens build-catalog --github-token $GITHUB_TOKEN")
        raise typer.Exit(code=1)

    typer.echo("Catalog build not yet implemented (planned for crawler subpackage).")
    typer.echo(f"Would output to: {output}")
    raise typer.Exit(code=1)
