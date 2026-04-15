"""Registry of agent extension directories.

Builds DiskExtensionStore instances for all agents whose skill
directories exist on disk.  Platform paths come from the central
registry in services/extensions/platforms.py.
"""

from vibelens.models.enums import ExtensionSource
from vibelens.services.extensions.platforms import PLATFORMS
from vibelens.storage.extension.disk import DiskExtensionStore


def create_agent_extension_stores() -> dict[ExtensionSource, DiskExtensionStore]:
    """Create stores for all agents whose extension directories exist on disk.

    Returns:
        Dict mapping each discovered ExtensionSource to its DiskExtensionStore.
    """
    stores: dict[ExtensionSource, DiskExtensionStore] = {}
    for source_type, platform in PLATFORMS.items():
        resolved = platform.skills_dir.expanduser().resolve()
        if resolved.is_dir():
            stores[source_type] = DiskExtensionStore(
                extensions_dir=resolved, source_type=source_type
            )
    return stores
