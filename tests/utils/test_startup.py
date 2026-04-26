"""Tests for vibelens.utils.startup."""

import logging
import time

import pytest

from vibelens.utils import startup as startup_module
from vibelens.utils.startup import (
    PROGRESS,
    ProgressState,
    Status,
    quiet_vibelens_logger,
    render_banner,
    start_spinner,
    stop_spinner,
)


@pytest.fixture(autouse=True)
def _reset_progress():
    """Each test starts with a fresh ProgressState and clean log levels."""
    saved_level = logging.getLogger("vibelens").level
    snapshot = (
        PROGRESS.phase,
        PROGRESS.started_at,
        PROGRESS.status,
        PROGRESS.session_count,
        PROGRESS.extension_count,
        PROGRESS.url,
        PROGRESS.open_browser,
    )
    PROGRESS.phase = "Loading config…"
    PROGRESS.started_at = None
    PROGRESS.status = Status.RUNNING
    PROGRESS.session_count = None
    PROGRESS.extension_count = None
    PROGRESS.url = ""
    PROGRESS.open_browser = True
    startup_module._saved_vibelens_log_level = None
    yield
    logging.getLogger("vibelens").setLevel(saved_level)
    startup_module._saved_vibelens_log_level = None
    (
        PROGRESS.phase,
        PROGRESS.started_at,
        PROGRESS.status,
        PROGRESS.session_count,
        PROGRESS.extension_count,
        PROGRESS.url,
        PROGRESS.open_browser,
    ) = snapshot


def test_progress_state_initial_values():
    state = ProgressState()
    assert state.phase == "Loading config…"
    assert state.started_at is None
    assert state.status is Status.RUNNING
    assert state.session_count is None
    assert state.extension_count is None
    assert state.url == ""
    assert state.open_browser is True


def test_progress_start_records_url_and_anchors_timer():
    state = ProgressState()
    state.start(url="http://localhost:9000", open_browser=False)
    assert isinstance(state.started_at, float)
    assert state.url == "http://localhost:9000"
    assert state.open_browser is False


def test_progress_set_updates_phase():
    state = ProgressState()
    state.set("Loading extension catalog…")
    assert state.phase == "Loading extension catalog…"


def test_progress_totals_records_counts():
    state = ProgressState()
    state.totals(sessions=1483, extensions=25650)
    assert state.session_count == 1483
    assert state.extension_count == 25650


def test_progress_totals_partial_update():
    state = ProgressState()
    state.totals(sessions=10)
    state.totals(extensions=20)
    assert state.session_count == 10
    assert state.extension_count == 20


def test_progress_mark_ready_and_failed():
    state = ProgressState()
    state.mark_ready()
    assert state.status is Status.READY
    state.mark_failed()
    assert state.status is Status.FAILED


def test_render_banner_emits_brand_text(capsys):
    render_banner(version="9.9.9", url="http://localhost:42424")
    captured = capsys.readouterr()
    out = captured.err
    assert "v9.9.9" in out
    assert "See what your AI agents are doing." in out
    assert "http://localhost:42424" in out
    assert "Stretch, grab a coffee" in out


def test_render_banner_strips_ansi_in_non_tty(capsys):
    render_banner(version="1.0.7", url="http://x")
    captured = capsys.readouterr()
    assert "\x1b[" not in captured.err


def test_quiet_vibelens_logger_idempotent():
    logging.getLogger("vibelens").setLevel(logging.INFO)
    quiet_vibelens_logger()
    assert startup_module._saved_vibelens_log_level == logging.INFO
    # Second call (e.g. from lifespan after configure_logging resets level)
    # must not overwrite the saved INFO with the WARNING we just installed.
    logging.getLogger("vibelens").setLevel(logging.INFO)
    quiet_vibelens_logger()
    assert startup_module._saved_vibelens_log_level == logging.INFO
    assert logging.getLogger("vibelens").level == logging.WARNING


def test_spinner_thread_exits_on_mark_ready():
    PROGRESS.start(url="http://x", open_browser=False)
    spinner = start_spinner()
    PROGRESS.mark_ready()
    spinner.join(timeout=2.0)
    assert not spinner.is_alive()


def test_spinner_thread_exits_on_mark_failed():
    PROGRESS.start(url="http://x", open_browser=False)
    spinner = start_spinner()
    PROGRESS.mark_failed()
    spinner.join(timeout=2.0)
    assert not spinner.is_alive()


def test_spinner_emits_phase_line_in_non_tty(capsys):
    PROGRESS.start(url="http://x", open_browser=False)
    spinner = start_spinner()
    PROGRESS.set("Loading extension catalog…")
    time.sleep(0.5)
    PROGRESS.mark_ready()
    spinner.join(timeout=2.0)
    captured = capsys.readouterr()
    assert "[vibelens] loading extension catalog" in captured.err


def test_start_spinner_quiets_vibelens_logger():
    logging.getLogger("vibelens").setLevel(logging.INFO)
    PROGRESS.start(url="http://x", open_browser=False)
    spinner = start_spinner()
    try:
        assert logging.getLogger("vibelens").level == logging.WARNING
    finally:
        PROGRESS.mark_ready()
        spinner.join(timeout=2.0)


def test_log_level_restored_after_ready():
    logging.getLogger("vibelens").setLevel(logging.INFO)
    PROGRESS.start(url="http://x", open_browser=False)
    spinner = start_spinner()
    PROGRESS.mark_ready()
    spinner.join(timeout=2.0)
    time.sleep(0.05)
    assert logging.getLogger("vibelens").level == logging.INFO


def test_log_level_restored_after_failure():
    logging.getLogger("vibelens").setLevel(logging.INFO)
    PROGRESS.start(url="http://x", open_browser=False)
    spinner = start_spinner()
    PROGRESS.mark_failed()
    spinner.join(timeout=2.0)
    time.sleep(0.05)
    assert logging.getLogger("vibelens").level == logging.INFO


def test_stop_spinner_marks_failed_when_neither_signal_fired(capsys):
    PROGRESS.start(url="http://x", open_browser=False)
    spinner = start_spinner()
    stop_spinner(spinner)
    assert PROGRESS.status is Status.FAILED
    captured = capsys.readouterr()
    assert "startup failed" in captured.err.lower()


def test_stop_spinner_writes_post_ready_hint_with_open(capsys):
    PROGRESS.start(url="http://localhost:1234", open_browser=True)
    spinner = start_spinner()
    PROGRESS.session_count = 100
    PROGRESS.extension_count = 200
    PROGRESS.mark_ready()
    spinner.join(timeout=2.0)
    capsys.readouterr()
    stop_spinner(spinner)
    captured = capsys.readouterr()
    assert "http://localhost:1234" in captured.err
    assert "Browser opened" in captured.err


def test_stop_spinner_writes_post_ready_hint_without_open(capsys):
    PROGRESS.start(url="http://localhost:1234", open_browser=False)
    spinner = start_spinner()
    PROGRESS.mark_ready()
    spinner.join(timeout=2.0)
    capsys.readouterr()
    stop_spinner(spinner)
    captured = capsys.readouterr()
    assert "Open the URL above" in captured.err


def test_summary_parts_includes_counts_when_present():
    PROGRESS.start(url="http://x", open_browser=False)
    PROGRESS.session_count = 1483
    PROGRESS.extension_count = 25650
    parts = startup_module._summary_parts()
    assert any("1,483 sessions" in p for p in parts)
    assert any("25,650 extensions" in p for p in parts)


def test_summary_parts_omits_counts_when_missing():
    PROGRESS.start(url="http://x", open_browser=False)
    parts = startup_module._summary_parts()
    assert len(parts) == 1
    assert parts[0].startswith("Ready in ")
