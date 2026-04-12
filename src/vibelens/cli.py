"""CLI entry point for VibeLens."""

import asyncio
import importlib
import shutil
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


def discover_and_select_backend():
    """Scan system for available CLI backends and let user pick one.

    Checks each registered CLI backend's executable via shutil.which().
    Presents an interactive numbered list with default models and pricing.

    Returns:
        LLMConfig for the selected backend, or None if user cancels or none found.
    """
    from vibelens.config.llm_config import LLMConfig
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

    return LLMConfig(backend=selected_bt, model=selected_model)


@app.command()
def recommend(
    top_n: int = typer.Option(15, "--top-n", help="Maximum recommendations to show"),
    config: Path | None = typer.Option(None, help="Path to YAML config file"),  # noqa: B008
    no_open: bool = typer.Option(False, "--no-open", help="Skip launching browser"),
) -> None:
    """Run the recommendation pipeline on all local sessions."""
    from vibelens.deps import get_llm_config, get_settings, set_llm_config
    from vibelens.llm.backend import InferenceError
    from vibelens.models.llm.inference import BackendType
    from vibelens.services.recommendation.engine import analyze_recommendation

    typer.echo(f"VibeLens v{__version__}\n")

    settings = load_settings(config_path=config)

    # Check if backend is configured; if not, run auto-discovery
    llm_config = get_llm_config()
    if llm_config.backend == BackendType.DISABLED:
        discovered = discover_and_select_backend()
        if discovered is None:
            typer.echo(
                "No LLM backend available. Install a supported agent CLI "
                "(claude, gemini, codex, etc.) or configure an API key."
            )
            raise typer.Exit(code=1)
        set_llm_config(discovered)
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

    from vibelens.services.recommendation.extraction import find_compaction_files

    compaction_count = sum(
        1 for m in all_metadata if find_compaction_files(m.get("filepath") or "")
    )
    typer.echo(f" {len(all_metadata)} found ({compaction_count} with summaries)")

    typer.echo("Running recommendation pipeline...")
    try:
        result = asyncio.run(analyze_recommendation(session_ids=None, session_token=None))
    except (ValueError, OSError, InferenceError) as exc:
        typer.echo(f"\nError: {exc}")
        raise typer.Exit(code=1) from None

    typer.echo(f"  Profile: {', '.join(result.user_profile.domains[:3])}")
    typer.echo(f"  Languages: {', '.join(result.user_profile.languages[:3])}")
    typer.echo(f"  Recommendations: {len(result.recommendations)}")

    cost_str = f"${result.metrics.cost_usd:.2f}" if result.metrics.cost_usd else "n/a"
    typer.echo(
        f"\nSaved: {result.analysis_id} "
        f"({result.duration_seconds}s, {cost_str})"
    )

    if not no_open:
        bind_host = settings.host
        bind_port = settings.port
        url = f"http://{bind_host}:{bind_port}?recommendation={result.analysis_id}"
        typer.echo(f"Opening {url}")

        timer = threading.Timer(
            BROWSER_OPEN_DELAY_SECONDS, _open_browser, args=[url]
        )
        timer.daemon = True
        timer.start()

        uvicorn.run(
            "vibelens.app:create_app",
            factory=True,
            host=bind_host,
            port=bind_port,
            reload=False,
        )
