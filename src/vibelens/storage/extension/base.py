"""Base class for all extension storage backends."""

import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path

from vibelens.models.extension import ExtensionInfo, ExtensionSource
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# How long get_cached() reuses its in-memory list before rescanning disk
CACHE_TTL_SECONDS = 300


class BaseExtensionStore(ABC):
    """Abstract base for all extension stores.

    Both the central VibeLens store and agent-native stores inherit from this
    class. The common abstraction is: a directory of named extensions that can
    be listed, read, written, deleted, and copied between stores.
    """

    def __init__(self) -> None:
        self._cache: list[ExtensionInfo] | None = None
        self._cached_at: float = 0.0

    @property
    @abstractmethod
    def source_type(self) -> ExtensionSource:
        """Unified source/store type for this store."""

    @property
    @abstractmethod
    def extensions_dir(self) -> Path:
        """Root directory for this store's extensions."""

    @abstractmethod
    def list_extensions(self) -> list[ExtensionInfo]:
        """List all installed extensions with metadata (fresh scan)."""

    @abstractmethod
    def get_extension(self, name: str) -> ExtensionInfo | None:
        """Look up a single extension by name."""

    @abstractmethod
    def read_content(self, name: str) -> str | None:
        """Read the full extension definition file content."""

    @abstractmethod
    def write_extension(self, name: str, content: str) -> Path:
        """Create or overwrite an extension's definition file.

        Returns:
            Absolute path to the written file.

        Raises:
            ValueError: If name is invalid kebab-case.
        """

    @abstractmethod
    def delete_extension(self, name: str) -> bool:
        """Remove an installed extension entirely.

        Returns:
            True if the extension was deleted, False if it did not exist.
        """

    def extension_path(self, name: str) -> Path:
        """Return the directory path for one extension."""
        return self.extensions_dir / name

    def import_extension_from(
        self, source_store: "BaseExtensionStore", name: str, overwrite: bool = False
    ) -> ExtensionInfo | None:
        """Copy one extension directory from another store into this store."""
        source_dir = source_store.extension_path(name)
        if not source_dir.is_dir():
            return None

        target_dir = self.extension_path(name)
        # Symlinks (e.g. from skillshub) must be unlinked before copytree
        if target_dir.is_symlink():
            if not overwrite:
                return self.get_extension(name)
            target_dir.unlink()
        elif target_dir.exists():
            if not overwrite:
                return self.get_extension(name)
            shutil.rmtree(target_dir)

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target_dir)
        self.invalidate_cache()
        return self.get_extension(name)

    def import_all_from(
        self, source_store: "BaseExtensionStore", overwrite: bool = False
    ) -> list[ExtensionInfo]:
        """Copy every extension from another store into this store."""
        imported: list[ExtensionInfo] = []
        for ext in source_store.get_cached():
            copied = self.import_extension_from(source_store, ext.name, overwrite=overwrite)
            if copied:
                imported.append(copied)
        return imported

    def search_extensions(self, query: str) -> list[ExtensionInfo]:
        """Search extensions by name or description substring (case-insensitive)."""
        query_lower = query.lower()
        return [
            s
            for s in self.get_cached()
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    def get_cached(self) -> list[ExtensionInfo]:
        """Return cached extension list, rescanning if stale."""
        now = time.monotonic()
        if self._cache is None or (now - self._cached_at) > CACHE_TTL_SECONDS:
            self._cache = self.list_extensions()
            self._cached_at = now
        return self._cache

    def invalidate_cache(self) -> None:
        """Force next get_cached() to rescan."""
        self._cache = None
        self._cached_at = 0.0
