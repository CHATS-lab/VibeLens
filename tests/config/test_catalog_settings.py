"""Tests for catalog configuration fields."""
from vibelens.config.settings import Settings


def test_catalog_defaults():
    """Settings has catalog fields with correct defaults."""
    s = Settings()
    assert s.catalog_auto_update is True
    assert s.catalog_check_interval_hours == 24
    assert s.catalog_update_url == ""
    assert s.recommendation_dir.name == "recommendations"
