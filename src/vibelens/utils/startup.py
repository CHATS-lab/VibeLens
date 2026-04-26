"""Startup banner and live progress spinner for ``vibelens serve``.

Exposes a ``PROGRESS`` singleton that the FastAPI lifespan updates with the
current startup phase. The CLI calls ``render_banner``, ``start_spinner``,
and ``stop_spinner`` around ``uvicorn.run`` so the user sees a polished
boot screen with a single self-rewriting status line. Full design lives at
``docs/superpowers/specs/2026-04-25-startup-banner-design.md``.
"""

import logging
import threading
import time
from enum import Enum
from time import monotonic

from rich.console import Console
from rich.live import Live
from rich.text import Text

# Polling interval for the spinner thread. ~12 fps is readable, not busy.
_FRAME_INTERVAL_SECONDS = 0.08
# How long stop_spinner waits for the spinner thread to drain.
_JOIN_TIMEOUT_SECONDS = 2.0
# Braille spinner cycle.
_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# Brand colors — match the logo image and the Tailwind accent-violet token.
_VIOLET = "#7c3aed"
_CYAN = "#22d3ee"
_DIM = "grey50"

# ANSI Shadow letters spelling VIBELENS, indented in render_banner.
_LOGO_LINES = (
    "██╗   ██╗██╗██████╗ ███████╗██╗     ███████╗███╗   ██╗███████╗",
    "██║   ██║██║██╔══██╗██╔════╝██║     ██╔════╝████╗  ██║██╔════╝",
    "██║   ██║██║██████╔╝█████╗  ██║     █████╗  ██╔██╗ ██║███████╗",
    "╚██╗ ██╔╝██║██╔══██╗██╔══╝  ██║     ██╔══╝  ██║╚██╗██║╚════██║",
    " ╚████╔╝ ██║██████╔╝███████╗███████╗███████╗██║ ╚████║███████║",
    "  ╚═══╝  ╚═╝╚═════╝ ╚══════╝╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝",
)

_VIBELENS_LOGGER_NAME = "vibelens"


class Status(Enum):
    """Lifecycle of the startup spinner."""

    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class ProgressState:
    """State shared between the lifespan (writer) and the spinner (reader)."""

    def __init__(self) -> None:
        self.phase: str = "Loading config…"
        self.started_at: float | None = None
        self.status: Status = Status.RUNNING
        self.session_count: int | None = None
        self.extension_count: int | None = None
        self.url: str = ""
        self.open_browser: bool = True

    def start(self, *, url: str, open_browser: bool) -> None:
        """Anchor the elapsed timer and record CLI display state."""
        self.started_at = monotonic()
        self.url = url
        self.open_browser = open_browser

    def set(self, phase: str) -> None:
        """Update the current phase string shown by the spinner."""
        self.phase = phase

    def totals(self, sessions: int | None = None, extensions: int | None = None) -> None:
        """Record final counts that appear on the ready line."""
        if sessions is not None:
            self.session_count = sessions
        if extensions is not None:
            self.extension_count = extensions

    def mark_ready(self) -> None:
        """Signal that the awaited critical path has finished."""
        self.status = Status.READY

    def mark_failed(self) -> None:
        """Signal that startup raised before reaching ready."""
        self.status = Status.FAILED


PROGRESS = ProgressState()

# Saved level for the vibelens logger so quiet_vibelens_logger() is reversible.
_saved_vibelens_log_level: int | None = None


def _build_console() -> Console:
    """Console bound to stderr so it doesn't collide with stdout consumers."""
    return Console(stderr=True, highlight=False)


def quiet_vibelens_logger() -> None:
    """Set the vibelens logger to WARNING for the duration of startup.

    Idempotent: only saves the original level on the first call. The lifespan
    calls this a second time after ``configure_logging`` resets the level, and
    we must not overwrite the saved INFO level with the WARNING we just set.
    """
    global _saved_vibelens_log_level
    logger_obj = logging.getLogger(_VIBELENS_LOGGER_NAME)
    if _saved_vibelens_log_level is None:
        _saved_vibelens_log_level = logger_obj.level
    logger_obj.setLevel(logging.WARNING)


def _restore_vibelens_log_level() -> None:
    """Reset the vibelens logger to whatever quiet_vibelens_logger saved."""
    global _saved_vibelens_log_level
    if _saved_vibelens_log_level is not None:
        logging.getLogger(_VIBELENS_LOGGER_NAME).setLevel(_saved_vibelens_log_level)
        _saved_vibelens_log_level = None


def render_banner(*, version: str, url: str) -> None:
    """Print the static banner once.

    Args:
        version: Version string shown next to the tagline.
        url: Server URL shown in the Server line.
    """
    console = _build_console()
    console.print()
    for line in _LOGO_LINES:
        console.print(f"  [bold {_VIOLET}]{line}[/]")
    console.print()
    console.print(
        f"  [bold {_CYAN}]v{version}[/]  [{_CYAN}]·  See what your AI agents are doing.[/]"
    )
    console.print()
    console.print(f"  [bright_white]Server  →  {url}[/]")
    console.print(f"  [{_DIM}]Tip     →  First launch indexes all your sessions. This can take[/]")
    console.print(f"  [{_DIM}]           30 to 60 seconds. Stretch, grab a coffee, we'll[/]")
    console.print(f"  [{_DIM}]           be ready shortly.[/]")
    console.print()


def _phase_line(frame_idx: int) -> Text:
    """Render one frame of the spinner."""
    frame = _SPINNER_FRAMES[frame_idx % len(_SPINNER_FRAMES)]
    return Text.from_markup(f"  [{_CYAN}]{frame}[/]  {PROGRESS.phase}")


def _summary_parts() -> list[str]:
    """Compose the elapsed/sessions/extensions tokens used on the ready line."""
    elapsed = monotonic() - (PROGRESS.started_at or monotonic())
    parts: list[str] = [f"Ready in {elapsed:.0f}s"]
    if PROGRESS.session_count is not None:
        parts.append(f"{PROGRESS.session_count:,} sessions")
    if PROGRESS.extension_count is not None:
        parts.append(f"{PROGRESS.extension_count:,} extensions")
    return parts


def _ready_line() -> Text:
    """Render the green check-mark ready line."""
    summary = " · ".join(_summary_parts())
    return Text.from_markup(f"  [bold green]✓[/]  [bold]{summary}[/]")


def _failure_line() -> Text:
    """Render the red cross failure line."""
    return Text.from_markup("  [bold red]✗[/]  [bold]Startup failed (see logs above).[/]")


def _run_spinner_tty(console: Console) -> None:
    """Drive the rich.Live spinner in a TTY."""
    try:
        with Live(_phase_line(0), console=console, refresh_per_second=12, transient=False) as live:
            frame_idx = 0
            while PROGRESS.status is Status.RUNNING:
                live.update(_phase_line(frame_idx))
                frame_idx += 1
                time.sleep(_FRAME_INTERVAL_SECONDS)
            live.update(_ready_line() if PROGRESS.status is Status.READY else _failure_line())
    finally:
        _restore_vibelens_log_level()


def _run_spinner_plain(console: Console) -> None:
    """Non-TTY fallback: emit one ``[vibelens] {phase}`` line per transition."""
    try:
        last_phase: str | None = None
        while PROGRESS.status is Status.RUNNING:
            if PROGRESS.phase != last_phase:
                console.print(Text(f"[vibelens] {PROGRESS.phase.rstrip('…').lower()}"))
                last_phase = PROGRESS.phase
            time.sleep(_FRAME_INTERVAL_SECONDS * 4)
        if PROGRESS.status is Status.READY:
            tokens = [tok.lower() for tok in _summary_parts()]
            console.print(Text(f"[vibelens] {' · '.join(tokens)}"))
        else:
            console.print(Text("[vibelens] startup failed"))
    finally:
        _restore_vibelens_log_level()


def start_spinner() -> threading.Thread:
    """Spawn the spinner daemon thread and quiet vibelens INFO logs.

    Returns:
        The thread reference. Pass it to ``stop_spinner``.
    """
    quiet_vibelens_logger()
    console = _build_console()
    target = _run_spinner_tty if console.is_terminal else _run_spinner_plain
    thread = threading.Thread(target=target, args=(console,), daemon=True, name="vibelens-spinner")
    thread.start()
    return thread


def stop_spinner(spinner: threading.Thread) -> None:
    """Drain the spinner thread and emit the post-ready hint line.

    Args:
        spinner: Thread returned by ``start_spinner``.
    """
    if PROGRESS.status is Status.RUNNING:
        PROGRESS.mark_failed()
    spinner.join(timeout=_JOIN_TIMEOUT_SECONDS)
    # If the thread never started (test scenarios), restore directly.
    _restore_vibelens_log_level()

    if PROGRESS.status is Status.READY:
        console = _build_console()
        console.print(f"     [bright_white]→  {PROGRESS.url}[/]")
        hint = (
            "Browser opened. Press Ctrl+C to stop."
            if PROGRESS.open_browser
            else "Open the URL above. Press Ctrl+C to stop."
        )
        console.print(f"     [{_DIM}]{hint}[/]")
        console.print()
