"""Extension storage backends for agent-specific extension management."""

from vibelens.models.extension import ExtensionInfo
from vibelens.storage.extension.agent import create_agent_extension_stores
from vibelens.storage.extension.base import BaseExtensionStore
from vibelens.storage.extension.catalog import CatalogSnapshot, load_catalog, reset_catalog_cache
from vibelens.storage.extension.central import CentralExtensionStore
from vibelens.storage.extension.disk import DiskExtensionStore
from vibelens.storage.extension.install import (
    install_catalog_item,
    install_from_source_url,
    uninstall_extension,
)

__all__ = [
    "BaseExtensionStore",
    "CatalogSnapshot",
    "CentralExtensionStore",
    "DiskExtensionStore",
    "ExtensionInfo",
    "create_agent_extension_stores",
    "install_catalog_item",
    "install_from_source_url",
    "load_catalog",
    "reset_catalog_cache",
    "uninstall_extension",
]
