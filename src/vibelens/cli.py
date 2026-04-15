"""CLI entry point for VibeLens."""

import asyncio
import importlib
import shutil
import socket
import threading
import time
import webbrowser
from pathlib import Path

import typer
import uvicorn

from vibelens import __version__
from vibelens.config import load_settings

# Polling interval when waiting for the server to accept connections
POLL_INTERVAL_SECONDS = 0.3
# Maximum time to wait for the server before giving up
POLL_TIMEOUT_SECONDS = 30

app = typer.Typer(name="vibelens", help="Agent Trajectory analysis and visualization platform.")


def _open_browser_when_ready(host: str, port: int, url: str) -> None:
    """Poll the server until it accepts connections, then open the browser.

    Args:
        host: Server bind host.
        port: Server bind port.
        url: Full URL to open in the browser.
    """
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(POLL_INTERVAL_SECONDS)


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind host"),
    port: int | None = typer.Option(None, help="Bind port"),
    config: Path | None = typer.Option(None, help="Path to YAML config file"),  # noqa: B008
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open browser on startup"),
) -> None:
    """Start the VibeLens server."""
    settings = load_settings(config_path=config)
    bind_host = host or settings.server.host
    bind_port = port or settings.server.port

    typer.echo(f"VibeLens v{__version__}")
    typer.echo(f"VibeLens running at http://{bind_host}:{bind_port}")

    if open_browser:
        url = f"http://{bind_host}:{bind_port}"
        thread = threading.Thread(
            target=_open_browser_when_ready, args=[bind_host, bind_port, url], daemon=True
        )
        thread.start()

    uvicorn.run(
        "vibelens.app:create_app", factory=True, host=bind_host, port=bind_port, reload=False
    )


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(f"vibelens {__version__}")


def discover_and_select_backend():
    """Scan system for available CLI backends and let user pick one.

    Checks each registered CLI backend's executable via shutil.which().
    Presents an interactive numbered list with default models and pricing.

    Returns:
        InferenceConfig for the selected backend, or None if user cancels or none found.
    """
    from vibelens.config import InferenceConfig
    from vibelens.llm.backends import _CLI_BACKEND_REGISTRY
    from vibelens.llm.pricing import lookup_pricing
    from vibelens.models.llm.inference import BackendType

    available: list[tuple[BackendType, str, str, str]] = []

    for backend_type, (module_path, class_name) in _CLI_BACKEND_REGISTRY.items():
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        instance = cls()
        if shutil.which(instance.cli_executable) is None:
            continue
        default_model = instance.default_model or "default"
        pricing = lookup_pricing(default_model)
        if pricing:
            est_input = 50_000 * pricing.input_per_mtok / 1_000_000
            est_output = 8_000 * pricing.output_per_mtok / 1_000_000
            cost_str = f"~${est_input + est_output:.2f}/run"
        else:
            cost_str = "free" if "gemini" in default_model.lower() else "unknown"
        available.append((backend_type, instance.cli_executable, default_model, cost_str))

    if not available:
        return None

    typer.echo("\nNo LLM backend configured. Found available backends:\n")
    for idx, (bt, exe, model, cost) in enumerate(available, 1):
        typer.echo(f"  {idx}. {bt.value:<14} ({exe:<10}) → {model:<25} {cost}")
    typer.echo()

    choice = typer.prompt(f"Pick a backend [1-{len(available)}]", type=int)
    if choice < 1 or choice > len(available):
        typer.echo("Invalid choice.")
        return None

    selected_bt, _, selected_model, _ = available[choice - 1]
    typer.echo(f"\nUsing {selected_bt.value} with {selected_model}")

    return InferenceConfig(backend=selected_bt, model=selected_model)


@app.command()
def recommend(
    top_n: int = typer.Option(15, "--top-n", min=1, max=50, help="Maximum recommendations (1-50)"),
    config: Path | None = typer.Option(None, help="Path to YAML config file"),  # noqa: B008
    no_open: bool = typer.Option(False, "--no-open", help="Skip launching browser"),
) -> None:
    """Run the recommendation pipeline on all local sessions."""
    from vibelens.deps import get_inference_config, get_settings, set_inference_config
    from vibelens.llm.backend import InferenceError
    from vibelens.models.llm.inference import BackendType
    from vibelens.services.recommendation.engine import analyze_recommendation

    typer.echo(f"VibeLens v{__version__}\n")

    settings = load_settings(config_path=config)

    # Check if backend is configured; if not, run auto-discovery
    inference_config = get_inference_config()
    if inference_config.backend == BackendType.DISABLED:
        discovered = discover_and_select_backend()
        if discovered is None:
            typer.echo(
                "No LLM backend available. Install a supported agent CLI "
                "(claude, gemini, codex, etc.) or configure an API key."
            )
            raise typer.Exit(code=1)
        set_inference_config(discovered)
        typer.echo(f"Saved to {get_settings().settings_path or '~/.vibelens/settings.json'}\n")

    # Run pipeline
    typer.echo("Loading sessions...", nl=False)
    from vibelens.services.session.store_resolver import list_all_metadata

    all_metadata = list_all_metadata(session_token=None)
    if not all_metadata:
        typer.echo(
            "\nNo sessions found. VibeLens looks in ~/.claude/, ~/.codex/, ~/.gemini/, ~/.openclaw/"
        )
        raise typer.Exit(code=1)

    typer.echo(f" {len(all_metadata)} found")

    typer.echo("Running recommendation pipeline...")
    try:
        result = asyncio.run(
            analyze_recommendation(session_ids=None, session_token=None, top_n=top_n)
        )
    except (ValueError, OSError, InferenceError) as exc:
        typer.echo(f"\nError: {exc}")
        raise typer.Exit(code=1) from None

    if result.user_profile:
        typer.echo(f"  Profile: {', '.join(result.user_profile.domains[:3])}")
        typer.echo(f"  Languages: {', '.join(result.user_profile.languages[:3])}")
    typer.echo(f"  Recommendations: {len(result.recommendations)}")

    cost_str = (
        f"${result.final_metrics.total_cost_usd:.2f}"
        if result.final_metrics.total_cost_usd
        else "n/a"
    )
    typer.echo(f"\nSaved: {result.id} ({cost_str})")

    if not no_open:
        bind_host = settings.server.host
        bind_port = settings.server.port
        url = f"http://{bind_host}:{bind_port}?recommendation={result.id}"
        typer.echo(f"Opening {url}")

        thread = threading.Thread(
            target=_open_browser_when_ready, args=[bind_host, bind_port, url], daemon=True
        )
        thread.start()

        uvicorn.run(
            "vibelens.app:create_app", factory=True, host=bind_host, port=bind_port, reload=False
        )
