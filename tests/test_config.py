"""Unit tests for vibelens.config."""

from pathlib import Path

import pytest

from vibelens.config import Settings, load_settings


class TestSettings:
    """Test Settings model defaults and overrides."""

    def test_defaults(self):
        settings = Settings()
        assert settings.host == "127.0.0.1"
        assert settings.port == 12001
        assert settings.claude_dir == Path.home() / ".claude"
        assert settings.db_path == Path.home() / ".vibelens" / "vibelens.db"
        assert settings.mongodb_uri == ""
        assert settings.mongodb_db == "vibelens"
        assert settings.hf_token == ""

    def test_override_host_and_port(self):
        settings = Settings(host="0.0.0.0", port=8080)
        assert settings.host == "0.0.0.0"
        assert settings.port == 8080

    def test_override_claude_dir(self, tmp_path: Path):
        settings = Settings(claude_dir=tmp_path / "custom")
        assert settings.claude_dir == tmp_path / "custom"

    def test_override_db_path(self, tmp_path: Path):
        settings = Settings(db_path=tmp_path / "test.db")
        assert settings.db_path == tmp_path / "test.db"

    def test_mongodb_uri(self):
        settings = Settings(mongodb_uri="mongodb://localhost:27017")
        assert settings.mongodb_uri == "mongodb://localhost:27017"

    def test_env_prefix(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VIBELENS_HOST", "192.168.1.1")
        monkeypatch.setenv("VIBELENS_PORT", "9999")
        settings = Settings()
        assert settings.host == "192.168.1.1"
        assert settings.port == 9999

    def test_env_claude_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("VIBELENS_CLAUDE_DIR", str(tmp_path / "env-claude"))
        settings = Settings()
        assert settings.claude_dir == tmp_path / "env-claude"


class TestLoadSettings:
    """Test load_settings function."""

    def test_returns_settings_instance(self):
        settings = load_settings()
        assert isinstance(settings, Settings)

    def test_respects_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VIBELENS_PORT", "7777")
        settings = load_settings()
        assert settings.port == 7777
