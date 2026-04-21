"""Tests for the version service."""

from unittest.mock import patch

import httpx
import pytest

from vibelens.services import version as version_mod
from vibelens.services.version import compare_versions


def test_compare_newer_latest_is_update_available():
    result = compare_versions(current="1.0.4", latest="1.0.5")
    assert result.update_available is True
    assert result.is_dev_build is False


def test_compare_equal_versions():
    result = compare_versions(current="1.0.4", latest="1.0.4")
    assert result.update_available is False
    assert result.is_dev_build is False


def test_compare_current_ahead_is_dev_build():
    result = compare_versions(current="1.1.0", latest="1.0.5")
    assert result.update_available is False
    assert result.is_dev_build is True


def test_compare_null_latest():
    result = compare_versions(current="1.0.4", latest=None)
    assert result.update_available is False
    assert result.is_dev_build is False


def test_compare_handles_pep440_dev_suffix():
    result = compare_versions(current="1.1.0.dev0", latest="1.0.5")
    assert result.is_dev_build is True


PYPI_PAYLOAD_OK = {
    "info": {"version": "1.0.5"},
    "releases": {
        "1.0.3": [{"yanked": False}],
        "1.0.4": [{"yanked": False}],
        "1.0.5": [{"yanked": False}],
    },
}

PYPI_PAYLOAD_WITH_PRERELEASE = {
    "info": {"version": "1.1.0rc1"},
    "releases": {
        "1.0.4": [{"yanked": False}],
        "1.0.5": [{"yanked": False}],
        "1.1.0rc1": [{"yanked": False}],
    },
}

PYPI_PAYLOAD_WITH_YANKED_LATEST = {
    "info": {"version": "1.0.5"},
    "releases": {
        "1.0.4": [{"yanked": False}],
        "1.0.5": [{"yanked": True}],
    },
}


def _mock_httpx_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json=payload,
        request=httpx.Request("GET", "https://pypi.org/pypi/vibelens/json"),
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    version_mod._LATEST_CACHE.clear()
    yield
    version_mod._LATEST_CACHE.clear()


def test_fetch_latest_returns_highest_stable():
    with patch.object(
        version_mod.httpx, "get", return_value=_mock_httpx_response(PYPI_PAYLOAD_OK)
    ):
        assert version_mod.fetch_latest_version() == "1.0.5"


def test_fetch_latest_skips_prereleases():
    with patch.object(
        version_mod.httpx,
        "get",
        return_value=_mock_httpx_response(PYPI_PAYLOAD_WITH_PRERELEASE),
    ):
        assert version_mod.fetch_latest_version() == "1.0.5"


def test_fetch_latest_skips_yanked():
    with patch.object(
        version_mod.httpx,
        "get",
        return_value=_mock_httpx_response(PYPI_PAYLOAD_WITH_YANKED_LATEST),
    ):
        assert version_mod.fetch_latest_version() == "1.0.4"


def test_fetch_latest_returns_none_on_http_error():
    err = httpx.RequestError("boom", request=httpx.Request("GET", "https://pypi.org/"))
    with patch.object(version_mod.httpx, "get", side_effect=err):
        assert version_mod.fetch_latest_version() is None


def test_fetch_latest_is_cached():
    mock = _mock_httpx_response(PYPI_PAYLOAD_OK)
    with patch.object(version_mod.httpx, "get", return_value=mock) as get_spy:
        version_mod.fetch_latest_version()
        version_mod.fetch_latest_version()
        assert get_spy.call_count == 1


def test_fetch_latest_respects_disable_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VIBELENS_DISABLE_UPDATE_CHECK", "1")
    with patch.object(version_mod.httpx, "get") as get_spy:
        assert version_mod.fetch_latest_version() is None
        get_spy.assert_not_called()


def test_install_commands_has_three_methods():
    cmds = version_mod.INSTALL_COMMANDS
    assert cmds.uv == "uv tool upgrade vibelens"
    assert cmds.pip == "pip install -U vibelens"
    assert cmds.npx == "npm install -g @chats-lab/vibelens@latest"


def test_detect_install_method_uv_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UV_TOOL_BIN_DIR", "/tmp/uv-tools/bin")
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    monkeypatch.delenv("npm_config_user_agent", raising=False)
    monkeypatch.setattr(version_mod, "_is_editable_install", lambda: False)
    assert version_mod.detect_install_method() == "uv"


def test_detect_install_method_uv_via_prefix(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        version_mod.sys, "prefix", "/home/u/.local/share/uv/tools/vibelens/venv"
    )
    monkeypatch.delenv("UV_TOOL_BIN_DIR", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    monkeypatch.delenv("npm_config_user_agent", raising=False)
    monkeypatch.setattr(version_mod, "_is_editable_install", lambda: False)
    assert version_mod.detect_install_method() == "uv"


def test_detect_install_method_npx(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UV_TOOL_BIN_DIR", raising=False)
    monkeypatch.setattr(version_mod.sys, "prefix", "/usr/local")
    monkeypatch.setenv("npm_config_user_agent", "npm/10.0.0 node/v22.0.0")
    monkeypatch.setattr(version_mod, "_is_editable_install", lambda: False)
    assert version_mod.detect_install_method() == "npx"


def test_detect_install_method_fallback_pip(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UV_TOOL_BIN_DIR", raising=False)
    monkeypatch.delenv("NPM_CONFIG_PREFIX", raising=False)
    monkeypatch.delenv("npm_config_user_agent", raising=False)
    monkeypatch.setattr(version_mod.sys, "prefix", "/usr/local")
    monkeypatch.setattr(version_mod, "_is_editable_install", lambda: False)
    monkeypatch.setattr(version_mod, "_has_distribution", lambda: True)
    assert version_mod.detect_install_method() == "pip"


def test_detect_install_method_source(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(version_mod, "_is_editable_install", lambda: True)
    assert version_mod.detect_install_method() == "source"


def test_get_version_info_happy_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(version_mod, "fetch_latest_version", lambda: "1.0.5")
    monkeypatch.setattr(version_mod, "detect_install_method", lambda: "uv")
    info = version_mod.get_version_info(current="1.0.4")
    assert info.current == "1.0.4"
    assert info.latest == "1.0.5"
    assert info.update_available is True
    assert info.is_dev_build is False
    assert info.install_method == "uv"
    assert info.install_commands.uv == "uv tool upgrade vibelens"


def test_get_version_info_offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(version_mod, "fetch_latest_version", lambda: None)
    monkeypatch.setattr(version_mod, "detect_install_method", lambda: "pip")
    info = version_mod.get_version_info(current="1.0.4")
    assert info.latest is None
    assert info.update_available is False
    assert info.is_dev_build is False
    assert info.install_method == "pip"
