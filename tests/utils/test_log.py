"""Tests for vibelens.utils.log."""

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

import vibelens.utils.log as log_module
from vibelens.config.settings import LoggingConfig
from vibelens.utils.log import (
    DOMAIN_PREFIXES,
    _resolve_domain,
    clear_analysis_id,
    configure_logging,
    get_logger,
    set_analysis_id,
)


def test_resolve_domain_ingest_covers_parsers():
    assert _resolve_domain("vibelens.ingest.parsers.claude") == "ingest"
    assert _resolve_domain("vibelens.ingest.discovery") == "ingest"


def test_resolve_domain_donation_wins_over_session():
    assert _resolve_domain("vibelens.services.session.donation") == "donation"
    assert _resolve_domain("vibelens.services.session.search") == "session"


def test_resolve_domain_analysis_consolidation():
    assert _resolve_domain("vibelens.services.creation.creation") == "analysis"
    assert _resolve_domain("vibelens.services.evolution.evolution") == "analysis"
    assert _resolve_domain("vibelens.services.recommendation.engine") == "analysis"
    assert _resolve_domain("vibelens.services.personalization.store") == "analysis"
    assert _resolve_domain("vibelens.services.friction.analysis") == "analysis"
    assert _resolve_domain("vibelens.services.inference_shared") == "analysis"
    assert _resolve_domain("vibelens.api.creation") == "analysis"
    assert _resolve_domain("vibelens.api.friction") == "analysis"


def test_resolve_domain_extensions_covers_api_and_storage():
    assert _resolve_domain("vibelens.services.extensions.hook_service") == "extensions"
    assert _resolve_domain("vibelens.storage.extension.skill_store") == "extensions"
    assert _resolve_domain("vibelens.api.hook") == "extensions"
    assert _resolve_domain("vibelens.api.skill") == "extensions"
    assert _resolve_domain("vibelens.api.command") == "extensions"
    assert _resolve_domain("vibelens.api.subagent") == "extensions"
    assert _resolve_domain("vibelens.api.extensions") == "extensions"


def test_resolve_domain_unmatched_returns_none():
    assert _resolve_domain("vibelens.utils.json") is None
    assert _resolve_domain("vibelens.app") is None


def test_domain_prefixes_has_all_expected_domains():
    expected = {
        "ingest",
        "analysis",
        "donation",
        "upload",
        "extensions",
        "dashboard",
        "session",
        "llm",
    }
    assert set(DOMAIN_PREFIXES) == expected


def test_logging_config_defaults():
    config = LoggingConfig()
    assert config.level == "INFO"
    assert config.max_bytes == 10 * 1024 * 1024
    assert config.backup_count == 3
    assert config.per_domain == {}
    assert config.dir.name == "logs"
    assert config.dir.parent.name != "src"


def test_logging_config_rejects_unknown_domain_in_per_domain():
    with pytest.raises(ValidationError) as excinfo:
        LoggingConfig(per_domain={"frition": "DEBUG"})
    assert "frition" in str(excinfo.value)


def test_logging_config_accepts_known_domain_overrides():
    config = LoggingConfig(per_domain={"analysis": "DEBUG", "donation": "WARNING"})
    assert config.per_domain == {"analysis": "DEBUG", "donation": "WARNING"}


@pytest.fixture
def reset_logging():
    """Clear log module state and detach/close handlers before and after each test."""

    def _reset():
        root = logging.getLogger("vibelens")
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for name in list(logging.Logger.manager.loggerDict):
            if name.startswith("vibelens"):
                child = logging.getLogger(name)
                for handler in list(child.handlers):
                    handler.close()
                    child.removeHandler(handler)
                child.setLevel(logging.NOTSET)
                if hasattr(child, "_vl_domain_attached"):
                    delattr(child, "_vl_domain_attached")
        log_module._bootstrapped = False
        log_module._configured = False
        log_module._domain_handlers.clear()
        log_module._pending_loggers.clear()
        log_module._per_domain_levels.clear()

    _reset()
    yield
    _reset()


def _make_config(tmp_path: Path, **overrides):
    defaults = {"dir": tmp_path, "level": "INFO", "max_bytes": 1024, "backup_count": 1}
    defaults.update(overrides)
    return LoggingConfig(**defaults)


def test_bootstrap_before_configure_emits_to_stderr(reset_logging, capsys):
    logger = get_logger("vibelens.ingest.parsers.claude")
    logger.info("hello from bootstrap")
    captured = capsys.readouterr()
    assert "hello from bootstrap" in captured.err


def test_configure_logging_creates_overall_and_errors_log(reset_logging, tmp_path):
    configure_logging(_make_config(tmp_path))
    get_logger("vibelens.ingest.parsers.claude").info("x")
    get_logger("vibelens.ingest.parsers.claude").warning("y")
    assert (tmp_path / "vibelens.log").exists()
    assert (tmp_path / "errors.log").exists()


def test_configure_logging_creates_domain_log_on_first_use(reset_logging, tmp_path):
    configure_logging(_make_config(tmp_path))
    get_logger("vibelens.services.friction.analysis").info("friction event")
    assert (tmp_path / "analysis.log").exists()
    assert "friction event" in (tmp_path / "analysis.log").read_text()


def test_configure_logging_is_idempotent(reset_logging, tmp_path):
    config = _make_config(tmp_path)
    configure_logging(config)
    configure_logging(config)
    root = logging.getLogger("vibelens")
    filenames = [
        Path(getattr(h, "baseFilename", "")).name
        for h in root.handlers
        if hasattr(h, "baseFilename")
    ]
    assert filenames.count("vibelens.log") == 1
    assert filenames.count("errors.log") == 1


def test_errors_log_filters_warning_and_above(reset_logging, tmp_path):
    configure_logging(_make_config(tmp_path))
    logger = get_logger("vibelens.services.friction.analysis")
    logger.info("info line")
    logger.warning("warn line")
    logger.error("error line")
    errors_text = (tmp_path / "errors.log").read_text()
    assert "info line" not in errors_text
    assert "warn line" in errors_text
    assert "error line" in errors_text


def test_per_domain_debug_override(reset_logging, tmp_path):
    configure_logging(_make_config(tmp_path, per_domain={"analysis": "DEBUG"}))
    logger = get_logger("vibelens.services.friction.analysis")
    logger.debug("debug detail")
    analysis_text = (tmp_path / "analysis.log").read_text()
    assert "debug detail" in analysis_text
    # DEBUG must NOT reach stderr / vibelens.log because those handlers stay at INFO
    overall_text = (tmp_path / "vibelens.log").read_text()
    assert "debug detail" not in overall_text


def test_analysis_id_prefix_still_works(reset_logging, tmp_path):
    configure_logging(_make_config(tmp_path))
    logger = get_logger("vibelens.services.friction.analysis")
    set_analysis_id("abc123")
    try:
        logger.info("tagged message")
    finally:
        clear_analysis_id()
    assert "[abc123] tagged message" in (tmp_path / "analysis.log").read_text()


def test_analysis_id_no_duplicate_prefix(reset_logging, tmp_path):
    """Verify the analysis_id prefix appears exactly once per log line.

    The old _AnalysisIdFormatter mutated record.msg, causing duplicate
    prefixes when multiple handlers processed the same record.
    """
    configure_logging(_make_config(tmp_path))
    logger = get_logger("vibelens.services.friction.analysis")
    set_analysis_id("dup-test")
    try:
        logger.info("should not duplicate")
    finally:
        clear_analysis_id()

    for log_file in ("analysis.log", "vibelens.log"):
        text = (tmp_path / log_file).read_text()
        assert "[dup-test] should not duplicate" in text
        assert "[dup-test] [dup-test]" not in text, f"Duplicate prefix in {log_file}"


def test_pending_loggers_retroactively_attached(reset_logging, tmp_path):
    # Grab logger BEFORE configure_logging runs
    logger = get_logger("vibelens.services.donation.sender")
    configure_logging(_make_config(tmp_path))
    logger.info("late log")
    assert (tmp_path / "donation.log").exists()
    assert "late log" in (tmp_path / "donation.log").read_text()


def test_startup_summary_emitted(reset_logging, tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="vibelens"):
        configure_logging(_make_config(tmp_path))
    messages = [r.getMessage() for r in caplog.records]
    assert any("Logging configured" in m for m in messages)
