"""Hooks merge JSON, not files — link_type is accepted for API consistency but ignored."""

import json
from pathlib import Path

import pytest

from vibelens.services.extensions.hook_service import HookService
from vibelens.storage.extension.hook_store import HookStore


@pytest.fixture
def hook_service(tmp_path: Path) -> HookService:
    central = HookStore(root=tmp_path / "central", create=True)
    config_paths = {"claude": tmp_path / "claude" / "settings.json"}
    return HookService(central=central, agents=config_paths)


def test_install_accepts_link_type(hook_service, tmp_path: Path) -> None:
    """install accepts link_type without error and still merges JSON normally."""
    hook_config = {
        "PreToolUse": [
            {"matcher": ".*", "hooks": [{"type": "command", "command": "echo"}]}
        ]
    }

    hook_service.install(
        name="logger",
        description="t",
        hook_config=hook_config,
        sync_to=["claude"],
        link_type="symlink",
    )

    settings = json.loads((tmp_path / "claude" / "settings.json").read_text())
    assert "hooks" in settings
    assert settings["hooks"]["PreToolUse"][0]["_vibelens_managed"] == "logger"
