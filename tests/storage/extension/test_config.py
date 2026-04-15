"""Tests for ConfigExtensionStore — hooks and MCP configs in JSON files."""

import json
from pathlib import Path

from vibelens.storage.extension.config import ConfigExtensionStore


def test_install_hook(tmp_path: Path):
    """install_hook merges hook entries into settings.json."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")

    store = ConfigExtensionStore()
    hook_data = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo test"}]}
            ]
        }
    }
    store.install_hook(hook_data=hook_data, settings_path=settings_path)

    result = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "hooks" in result
    assert "PreToolUse" in result["hooks"]
    assert len(result["hooks"]["PreToolUse"]) == 1
    print(f"Installed hook config: {json.dumps(result, indent=2)}")


def test_install_hook_appends_to_existing(tmp_path: Path):
    """install_hook appends to existing hook entries, does not overwrite."""
    settings_path = tmp_path / "settings.json"
    existing = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "echo existing"}]}
            ]
        }
    }
    settings_path.write_text(json.dumps(existing), encoding="utf-8")

    store = ConfigExtensionStore()
    new_hook = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo new"}]}
            ]
        }
    }
    store.install_hook(hook_data=new_hook, settings_path=settings_path)

    result = json.loads(settings_path.read_text(encoding="utf-8"))
    assert len(result["hooks"]["PreToolUse"]) == 2
    print(f"Hook entries after append: {len(result['hooks']['PreToolUse'])}")


def test_list_hooks(tmp_path: Path):
    """list_hooks returns all hook event entries from settings.json."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo a"}]}
            ],
            "PostToolUse": [
                {"matcher": "", "hooks": [{"type": "command", "command": "echo b"}]}
            ],
        }
    }), encoding="utf-8")

    store = ConfigExtensionStore()
    hooks = store.list_hooks(settings_path=settings_path)
    assert len(hooks) == 2
    print(f"Listed {len(hooks)} hook groups")


def test_remove_hook(tmp_path: Path):
    """remove_hook removes a hook group by event + matcher."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo a"}]},
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "echo b"}]},
            ]
        }
    }), encoding="utf-8")

    store = ConfigExtensionStore()
    removed = store.remove_hook(
        event_name="PreToolUse", matcher="Bash", settings_path=settings_path
    )
    assert removed is True

    result = json.loads(settings_path.read_text(encoding="utf-8"))
    assert len(result["hooks"]["PreToolUse"]) == 1
    assert result["hooks"]["PreToolUse"][0]["matcher"] == "Edit"
    print(f"Remaining hooks after removal: {result['hooks']['PreToolUse']}")


def test_install_repo(tmp_path: Path):
    """install_repo merges MCP server config into claude.json."""
    claude_json_path = tmp_path / ".claude.json"
    claude_json_path.write_text("{}", encoding="utf-8")

    store = ConfigExtensionStore()
    repo_data = {
        "mcpServers": {
            "my-server": {
                "type": "stdio",
                "command": "/usr/bin/my-server",
                "args": [],
            }
        }
    }
    store.install_repo(repo_data=repo_data, config_path=claude_json_path)

    result = json.loads(claude_json_path.read_text(encoding="utf-8"))
    assert "mcpServers" in result
    assert "my-server" in result["mcpServers"]
    print(f"Installed MCP config: {json.dumps(result, indent=2)}")


def test_list_repos(tmp_path: Path):
    """list_repos returns all MCP server entries from claude.json."""
    claude_json_path = tmp_path / ".claude.json"
    claude_json_path.write_text(json.dumps({
        "mcpServers": {
            "server-a": {"type": "stdio", "command": "a"},
            "server-b": {"type": "http", "url": "https://b.com"},
        }
    }), encoding="utf-8")

    store = ConfigExtensionStore()
    repos = store.list_repos(config_path=claude_json_path)
    assert len(repos) == 2
    print(f"Listed {len(repos)} MCP servers")


def test_remove_repo(tmp_path: Path):
    """remove_repo removes an MCP server entry by name."""
    claude_json_path = tmp_path / ".claude.json"
    claude_json_path.write_text(json.dumps({
        "mcpServers": {
            "server-a": {"type": "stdio", "command": "a"},
            "server-b": {"type": "http", "url": "https://b.com"},
        }
    }), encoding="utf-8")

    store = ConfigExtensionStore()
    removed = store.remove_repo(
        server_name="server-a", config_path=claude_json_path
    )
    assert removed is True

    result = json.loads(claude_json_path.read_text(encoding="utf-8"))
    assert "server-a" not in result["mcpServers"]
    assert "server-b" in result["mcpServers"]
    print(f"Remaining servers: {list(result['mcpServers'].keys())}")
