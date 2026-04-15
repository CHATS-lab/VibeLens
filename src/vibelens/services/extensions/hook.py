"""Hook extension handler -- settings.json config entries."""

import json
from pathlib import Path

from vibelens.models.extension import ExtensionItem
from vibelens.storage.extension.config import ConfigExtensionStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class HookHandler:
    """Handler for hook extensions.

    Hooks install as config entries in settings.json under the 'hooks' key.
    """

    def __init__(self) -> None:
        self._config_store = ConfigExtensionStore()

    def install(self, item: ExtensionItem, settings_path: Path, overwrite: bool = False) -> Path:
        """Install hook config to settings.json.

        Args:
            item: ExtensionItem with hook JSON in install_content.
            settings_path: Path to settings.json.
            overwrite: If True, overwrite existing entries.

        Returns:
            Path to the settings file.
        """
        hook_data = json.loads(item.install_content or "{}")
        self._config_store.install_hook(hook_data=hook_data, settings_path=settings_path)
        logger.info("Installed hook %s to %s", item.extension_id, settings_path)
        return settings_path
