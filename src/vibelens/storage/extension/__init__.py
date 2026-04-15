"""Extension storage backends for agent-specific extension management."""

from vibelens.models.skill import ExtensionInfo
from vibelens.storage.extension.agent import create_agent_extension_stores
from vibelens.storage.extension.base import BaseExtensionStore
from vibelens.storage.extension.central import CentralExtensionStore
from vibelens.storage.extension.disk import DiskExtensionStore

__all__ = [
    "BaseExtensionStore",
    "CentralExtensionStore",
    "DiskExtensionStore",
    "ExtensionInfo",
    "create_agent_extension_stores",
]
