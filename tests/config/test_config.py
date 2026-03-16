"""Unit tests for vibelens.config."""

from pathlib import Path

import pytest

from vibelens.config import (
    Settings,
    discover_config_path,
    load_settings,
    validate_mongodb_config,
)
from vibelens.config.loader import load_yaml_flat


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

    def test_loads_yaml_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """YAML config values should populate settings."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            "server:\n  host: 10.0.0.1\n  port: 9090\nmongodb:\n  uri: mongodb://yaml-host:27017\n"
        )
        # Clear env vars that would override YAML
        monkeypatch.delenv("VIBELENS_HOST", raising=False)
        monkeypatch.delenv("VIBELENS_PORT", raising=False)
        monkeypatch.delenv("VIBELENS_MONGODB_URI", raising=False)

        settings = load_settings(config_path=config_file)

        assert settings.host == "10.0.0.1"
        assert settings.port == 9090
        assert settings.mongodb_uri == "mongodb://yaml-host:27017"
        print(f"YAML loaded: host={settings.host} port={settings.port}")

    def test_env_vars_override_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Env vars should take priority over YAML values."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("server:\n  host: yaml-host\n  port: 1111\n")
        monkeypatch.setenv("VIBELENS_PORT", "2222")
        monkeypatch.delenv("VIBELENS_HOST", raising=False)

        settings = load_settings(config_path=config_file)

        assert settings.host == "yaml-host"
        assert settings.port == 2222
        print(f"Env override: host={settings.host} port={settings.port}")

    def test_explicit_config_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Explicit config_path should be used even without auto-discovery."""
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("server:\n  host: custom-host\n")
        monkeypatch.delenv("VIBELENS_HOST", raising=False)

        settings = load_settings(config_path=config_file)
        assert settings.host == "custom-host"


class TestLoadYamlFlat:
    """Test YAML flattening logic."""

    def test_full_config(self, tmp_path: Path):
        config_file = tmp_path / "full.yaml"
        config_file.write_text(
            "server:\n"
            "  host: 0.0.0.0\n"
            "  port: 8080\n"
            "database:\n"
            "  path: /tmp/test.db\n"
            "mongodb:\n"
            "  uri: mongodb://localhost\n"
            "  db_name: testdb\n"
            "sources:\n"
            "  claude_dir: /tmp/claude\n"
            "integrations:\n"
            "  hf_token: hf_test_token\n"
        )
        result = load_yaml_flat(config_file)

        assert result["host"] == "0.0.0.0"
        assert result["port"] == "8080"
        assert result["db_path"] == "/tmp/test.db"
        assert result["mongodb_uri"] == "mongodb://localhost"
        assert result["mongodb_db"] == "testdb"
        assert result["claude_dir"] == "/tmp/claude"
        assert result["hf_token"] == "hf_test_token"
        print(f"Flattened: {result}")

    def test_partial_config(self, tmp_path: Path):
        config_file = tmp_path / "partial.yaml"
        config_file.write_text("server:\n  port: 3000\n")
        result = load_yaml_flat(config_file)

        assert result == {"port": "3000"}
        print(f"Partial: {result}")

    def test_empty_config(self, tmp_path: Path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        result = load_yaml_flat(config_file)
        assert result == {}

    def test_invalid_yaml_returns_empty(self, tmp_path: Path):
        config_file = tmp_path / "scalar.yaml"
        config_file.write_text("just a string")
        result = load_yaml_flat(config_file)
        assert result == {}

    def test_null_values_skipped(self, tmp_path: Path):
        config_file = tmp_path / "nulls.yaml"
        config_file.write_text("server:\n  host: null\n  port: 8080\n")
        result = load_yaml_flat(config_file)

        assert "host" not in result
        assert result["port"] == "8080"


class TestDiscoverConfigPath:
    """Test YAML config auto-discovery."""

    def test_no_config_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("VIBELENS_CONFIG", raising=False)
        assert discover_config_path() is None

    def test_discover_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("VIBELENS_CONFIG", raising=False)
        config_file = tmp_path / "vibelens.yaml"
        config_file.write_text("server:\n  port: 1234\n")

        result = discover_config_path()
        assert result is not None
        print(f"Discovered: {result}")

    def test_discover_yml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("VIBELENS_CONFIG", raising=False)
        config_file = tmp_path / "vibelens.yml"
        config_file.write_text("server:\n  port: 5678\n")

        result = discover_config_path()
        assert result is not None

    def test_env_var_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        config_file = tmp_path / "custom-config.yaml"
        config_file.write_text("server:\n  port: 9999\n")
        monkeypatch.setenv("VIBELENS_CONFIG", str(config_file))

        result = discover_config_path()
        assert result == config_file
        print(f"Env var config: {result}")

    def test_env_var_missing_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VIBELENS_CONFIG", str(tmp_path / "nonexistent.yaml"))
        assert discover_config_path() is None


class TestValidateMongodbConfig:
    """Test MongoDB config validation."""

    def test_valid_uri(self):
        settings = Settings(mongodb_uri="mongodb://localhost:27017")
        uri = validate_mongodb_config(settings)
        assert uri == "mongodb://localhost:27017"

    def test_empty_uri_raises(self):
        settings = Settings(mongodb_uri="")
        with pytest.raises(ValueError, match="MongoDB is not configured"):
            validate_mongodb_config(settings)
