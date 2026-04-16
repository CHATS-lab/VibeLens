"""Tests for vibelens.utils.log."""

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
