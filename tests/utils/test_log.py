"""Tests for vibelens.utils.log."""

import pytest
from pydantic import ValidationError

from vibelens.config.settings import LoggingConfig
from vibelens.utils.log import DOMAIN_PREFIXES, _resolve_domain


def test_resolve_domain_parsers_wins_over_ingest():
    assert _resolve_domain("vibelens.ingest.parsers.claude_code") == "parsers"
    assert _resolve_domain("vibelens.ingest.discovery") == "ingest"


def test_resolve_domain_donation_wins_over_session():
    assert _resolve_domain("vibelens.services.session.donation") == "donation"
    assert _resolve_domain("vibelens.services.session.search") == "session"


def test_resolve_domain_specific_personalization_subdomains():
    assert _resolve_domain("vibelens.services.creation.creation") == "creation"
    assert _resolve_domain("vibelens.services.evolution.evolution") == "evolution"
    assert _resolve_domain("vibelens.services.recommendation.engine") == "recommendation"
    assert _resolve_domain("vibelens.services.personalization.store") == "personalization"


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
        "parsers", "ingest", "creation", "evolution", "recommendation",
        "personalization", "friction", "donation", "upload", "extensions",
        "dashboard", "session", "llm",
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
    config = LoggingConfig(per_domain={"friction": "DEBUG", "donation": "WARNING"})
    assert config.per_domain == {"friction": "DEBUG", "donation": "WARNING"}
