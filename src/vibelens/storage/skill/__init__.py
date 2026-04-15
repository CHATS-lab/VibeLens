"""Extension storage backends for agent-specific extension management."""

from vibelens.models.skill import ExtensionInfo
from vibelens.storage.skill.agent import create_agent_extension_stores
from vibelens.storage.skill.base import BaseExtensionStore
from vibelens.storage.skill.central import CentralExtensionStore
from vibelens.storage.skill.disk import DiskExtensionStore

__all__ = [
    "BaseExtensionStore",
    "CentralExtensionStore",
    "DiskExtensionStore",
    "ExtensionInfo",
    "create_agent_extension_stores",
]
