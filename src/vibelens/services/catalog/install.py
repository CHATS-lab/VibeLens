"""Install catalog items to agent platform directories."""

import json
from pathlib import Path

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import ExtensionItem
from vibelens.services.skill.download import GITHUB_TREE_PATTERN, download_skill_directory
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

PLATFORM_DIRS: dict[str, dict[str, Path]] = {
    "claude_code": {
        "commands": Path.home() / ".claude" / "commands",
        "settings": Path.home() / ".claude" / "settings.json",
    },
}

FILE_INSTALL_TYPES = {
    AgentExtensionType.SKILL,
    AgentExtensionType.SUBAGENT,
    AgentExtensionType.COMMAND,
}


def install_catalog_item(
    item: ExtensionItem,
    target_platform: str = "claude_code",
    overwrite: bool = False,
) -> Path:
    """Install a catalog item to the target agent platform.

    Args:
        item: ExtensionItem with install_content populated.
        target_platform: Target platform key (e.g. 'claude_code').
        overwrite: If True, overwrite existing files.

    Returns:
        Path where the item was installed.

    Raises:
        ValueError: If platform is unknown or item has no install_content.
        FileExistsError: If target file exists and overwrite is False.
    """
    if target_platform not in PLATFORM_DIRS:
        raise ValueError(
            f"Unknown platform: {target_platform}. Available: {list(PLATFORM_DIRS.keys())}"
        )

    dirs = PLATFORM_DIRS[target_platform]

    if item.extension_type in FILE_INSTALL_TYPES:
        return _install_file(item=item, commands_dir=dirs["commands"], overwrite=overwrite)
    elif item.extension_type == AgentExtensionType.HOOK:
        return _install_hook(item=item, settings_path=dirs["settings"])
    elif item.install_method == "mcp_config":
        return _install_mcp(item=item, settings_path=dirs["settings"])
    else:
        raise ValueError(
            f"Cannot auto-install item type {item.extension_type} with method {item.install_method}"
        )


def install_from_source_url(
    item: ExtensionItem,
    target_platform: str = "claude_code",
    overwrite: bool = False,
) -> Path:
    """Install a catalog item by downloading its skill directory from GitHub.

    Used when install_content is None but source_url points to a GitHub tree URL.

    Args:
        item: ExtensionItem with a GitHub tree source_url.
        target_platform: Target platform key (e.g. 'claude_code').
        overwrite: If True, overwrite existing directory.

    Returns:
        Path where the skill directory was installed.

    Raises:
        ValueError: If platform is unknown, source_url is missing, or download fails.
        FileExistsError: If target directory exists and overwrite is False.
    """
    if target_platform not in PLATFORM_DIRS:
        raise ValueError(
            f"Unknown platform: {target_platform}. Available: {list(PLATFORM_DIRS.keys())}"
        )
    if not item.source_url or not GITHUB_TREE_PATTERN.match(item.source_url):
        raise ValueError(f"Item {item.extension_id} has no installable content or valid source URL")

    commands_dir = PLATFORM_DIRS[target_platform]["commands"]
    target_dir = commands_dir / item.name
    if target_dir.exists() and not overwrite:
        raise FileExistsError(
            f"Directory already exists: {target_dir}. Use overwrite=true to replace."
        )

    success = download_skill_directory(source_url=item.source_url, target_dir=target_dir)
    if not success:
        raise ValueError(f"Failed to download skill from {item.source_url}")

    logger.info("Installed %s from source URL to %s", item.extension_id, target_dir)
    return target_dir


def _install_file(item: ExtensionItem, commands_dir: Path, overwrite: bool) -> Path:
    """Write install_content to commands directory as {name}.md.

    Args:
        item: ExtensionItem with install_content.
        commands_dir: Target directory for skill files.
        overwrite: If True, replace existing file.

    Returns:
        Path to the written file.

    Raises:
        FileExistsError: If file exists and overwrite is False.
    """
    commands_dir.mkdir(parents=True, exist_ok=True)
    target = commands_dir / f"{item.name}.md"

    if target.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {target}. Use overwrite=true to replace.")

    target.write_text(item.install_content or "", encoding="utf-8")
    logger.info("Installed %s to %s", item.extension_id, target)
    return target


def _install_hook(item: ExtensionItem, settings_path: Path) -> Path:
    """Append hook entries to settings.json hooks object.

    Args:
        item: ExtensionItem with hook JSON in install_content.
        settings_path: Path to settings.json.

    Returns:
        Path to the settings file.
    """
    settings = _read_settings(settings_path=settings_path)
    hook_data = json.loads(item.install_content or "{}")
    hooks_to_add = hook_data.get("hooks") or {}

    existing_hooks = settings.setdefault("hooks", {})
    for event_type, entries in hooks_to_add.items():
        existing_entries = existing_hooks.setdefault(event_type, [])
        existing_entries.extend(entries)

    _write_settings(settings_path=settings_path, settings=settings)
    logger.info("Installed hook %s to %s", item.extension_id, settings_path)
    return settings_path


def _install_mcp(item: ExtensionItem, settings_path: Path) -> Path:
    """Merge MCP server config into settings.json mcpServers.

    Args:
        item: ExtensionItem with MCP JSON in install_content.
        settings_path: Path to settings.json.

    Returns:
        Path to the settings file.
    """
    settings = _read_settings(settings_path=settings_path)
    mcp_data = json.loads(item.install_content or "{}")
    servers = mcp_data.get("mcpServers") or {}

    existing_servers = settings.setdefault("mcpServers", {})
    existing_servers.update(servers)

    _write_settings(settings_path=settings_path, settings=settings)
    logger.info("Installed MCP %s to %s", item.extension_id, settings_path)
    return settings_path


def _read_settings(settings_path: Path) -> dict:
    """Read settings.json, returning empty dict if missing or invalid.

    Args:
        settings_path: Path to the settings JSON file.

    Returns:
        Parsed settings dict, or empty dict on missing/invalid file.
    """
    if settings_path.is_file():
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_settings(settings_path: Path, settings: dict) -> None:
    """Write settings dict back to settings.json.

    Args:
        settings_path: Path to write the settings JSON file.
        settings: Settings dict to serialize.
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
