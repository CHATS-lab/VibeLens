"""Config-based extension store for hooks and MCP servers.

Manages extensions stored in JSON config files rather than on-disk
directories. Hooks live in settings.json; MCP servers live in ~/.claude.json.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class InstalledHook(BaseModel):
    """A hook group installed in settings.json."""

    event_name: str = Field(description="Hook event (e.g. PreToolUse, SessionStart).")
    matcher: str = Field(default="", description="Matcher pattern for filtering.")
    hooks: list[dict] = Field(description="Hook handler entries.")


class InstalledRepo(BaseModel):
    """An MCP server installed in claude.json."""

    server_name: str = Field(description="MCP server name.")
    config: dict = Field(description="Server config (type, command/url, args, env, etc.).")


class ConfigExtensionStore:
    """Manages config entries in Claude Code JSON config files.

    Hooks are stored in settings.json under the 'hooks' key.
    MCP servers are stored in ~/.claude.json under the 'mcpServers' key.
    """

    def list_hooks(self, settings_path: Path) -> list[InstalledHook]:
        """List all hook groups from settings.json.

        Args:
            settings_path: Path to settings.json.

        Returns:
            List of installed hook groups.
        """
        settings = _read_json(settings_path)
        hooks_config = settings.get("hooks", {})
        result: list[InstalledHook] = []
        for event_name, groups in hooks_config.items():
            if not isinstance(groups, list):
                continue
            for group in groups:
                result.append(
                    InstalledHook(
                        event_name=event_name,
                        matcher=group.get("matcher", ""),
                        hooks=group.get("hooks", []),
                    )
                )
        return result

    def install_hook(self, hook_data: dict, settings_path: Path) -> None:
        """Merge hook entries into settings.json.

        Args:
            hook_data: Dict with 'hooks' key mapping event names to hook groups.
            settings_path: Path to settings.json.
        """
        settings = _read_json(settings_path)
        hooks_to_add = hook_data.get("hooks", {})
        existing_hooks = settings.setdefault("hooks", {})

        for event_name, entries in hooks_to_add.items():
            existing_entries = existing_hooks.setdefault(event_name, [])
            existing_entries.extend(entries)

        _write_json(settings_path, settings)
        logger.info("Installed hook config to %s", settings_path)

    def remove_hook(self, event_name: str, matcher: str, settings_path: Path) -> bool:
        """Remove a hook group by event name and matcher.

        Args:
            event_name: Hook event (e.g. PreToolUse).
            matcher: Matcher pattern to identify the hook group.
            settings_path: Path to settings.json.

        Returns:
            True if a hook group was removed.
        """
        settings = _read_json(settings_path)
        hooks_config = settings.get("hooks", {})
        groups = hooks_config.get(event_name, [])

        original_count = len(groups)
        groups = [g for g in groups if g.get("matcher", "") != matcher]

        if len(groups) == original_count:
            return False

        hooks_config[event_name] = groups
        _write_json(settings_path, settings)
        logger.info("Removed hook %s/%s from %s", event_name, matcher, settings_path)
        return True

    def list_repos(self, config_path: Path) -> list[InstalledRepo]:
        """List all MCP server entries from claude.json.

        Args:
            config_path: Path to ~/.claude.json.

        Returns:
            List of installed MCP servers.
        """
        config = _read_json(config_path)
        servers = config.get("mcpServers", {})
        return [
            InstalledRepo(server_name=name, config=cfg)
            for name, cfg in servers.items()
            if isinstance(cfg, dict)
        ]

    def install_repo(self, repo_data: dict, config_path: Path) -> None:
        """Merge MCP server config into claude.json.

        Args:
            repo_data: Dict with 'mcpServers' key mapping names to configs.
            config_path: Path to ~/.claude.json.
        """
        config = _read_json(config_path)
        servers = repo_data.get("mcpServers", {})
        existing_servers = config.setdefault("mcpServers", {})
        existing_servers.update(servers)

        _write_json(config_path, config)
        logger.info("Installed MCP config to %s", config_path)

    def remove_repo(self, server_name: str, config_path: Path) -> bool:
        """Remove an MCP server entry by name.

        Args:
            server_name: Server name to remove.
            config_path: Path to ~/.claude.json.

        Returns:
            True if a server was removed.
        """
        config = _read_json(config_path)
        servers = config.get("mcpServers", {})
        if server_name not in servers:
            return False

        del servers[server_name]
        _write_json(config_path, config)
        logger.info("Removed MCP server %s from %s", server_name, config_path)
        return True


def _read_json(path: Path) -> dict:
    """Read a JSON file, returning empty dict if missing or invalid.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dict, or empty dict on missing/invalid file.
    """
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_json(path: Path, data: dict) -> None:
    """Write a dict to a JSON file.

    Args:
        path: Path to the JSON file.
        data: Dict to serialize.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
