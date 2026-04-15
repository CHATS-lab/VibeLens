"""Repo extension handler -- MCP server configs in ~/.claude.json."""

import json
from pathlib import Path

from vibelens.models.extension import ExtensionItem
from vibelens.storage.extension.config import ConfigExtensionStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class RepoHandler:
    """Handler for repo extensions (MCP servers, CLI tools).

    MCP server configs are merged into ~/.claude.json under mcpServers.
    """

    def __init__(self) -> None:
        self._config_store = ConfigExtensionStore()

    def install(self, item: ExtensionItem, config_path: Path, overwrite: bool = False) -> Path:
        """Install MCP server config to claude.json.

        Args:
            item: ExtensionItem with MCP JSON in install_content.
            config_path: Path to ~/.claude.json.
            overwrite: If True, overwrite existing entries.

        Returns:
            Path to the config file.
        """
        mcp_data = json.loads(item.install_content or "{}")
        self._config_store.install_repo(repo_data=mcp_data, config_path=config_path)
        logger.info("Installed repo %s to %s", item.extension_id, config_path)
        return config_path
