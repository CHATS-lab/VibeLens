"""Abstract base class for file-based extension stores.

All extension stores (skill, command, subagent, hook) share a common CRUD
shape: write/read/list/delete/copy named items under a root directory.
They differ only in on-disk layout, parsing, filtering, and copy mechanics.

This base class factors the common parts and requires subclasses to
supply the specifics via three template methods.
"""

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

from vibelens.models.extension.item import VALID_EXTENSION_NAME
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

TItem = TypeVar("TItem")


class BaseExtensionStore(ABC, Generic[TItem]):
    """CRUD on a single directory of named items.

    Subclasses must implement:
        * _item_path(name) — where on disk the item's primary file lives.
        * _parse(name, text) — parse raw content into a domain model.
        * _iter_candidate_names() — enumerate potential names found on disk.

    Subclasses may override:
        * _include(name, raw) — filter hook (default: accept all).
        * _normalize_content(content) — transform before write (default: passthrough).
        * _delete_impl(name) — disk removal mechanics (default: unlink single file).
        * _copy_impl(source, name) — cross-store copy (default: copy2 single file).
    """

    def __init__(self, root: Path, *, create: bool = False) -> None:
        """Initialize a store rooted at a directory.

        Args:
            root: Directory containing items.
            create: If True, create root dir on init (for central store).
        """
        self._root = root.expanduser().resolve()
        if create:
            self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        """Root directory for this store."""
        return self._root

    def path_for(self, name: str) -> Path:
        """Return the filesystem path this store would use for an item (may not exist)."""
        return self._item_path(name)

    @abstractmethod
    def _item_path(self, name: str) -> Path:
        """Return the primary file path for a given item name."""

    def _item_root(self, name: str) -> Path:
        """Return the on-disk root for an item.

        Default: same as ``_item_path`` (single-file stores). Dir-based
        stores override to return the item's containing directory.
        """
        return self._item_path(name)

    @abstractmethod
    def _parse(self, name: str, text: str) -> TItem:
        """Parse raw content text into a domain model."""

    @abstractmethod
    def _iter_candidate_names(self) -> list[str]:
        """Return candidate names found on disk (before name/content filtering)."""

    def _include(self, name: str, raw: str) -> bool:
        """Filter hook for list_names. Override to exclude items."""
        return True

    def _normalize_content(self, content: str) -> str:
        """Transform content before write. Override to inject frontmatter, etc."""
        return content

    def _delete_impl(self, name: str) -> bool:
        """Remove the item from disk. Default: unlink single file."""
        path = self._item_path(name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def _copy_impl(self, source: "BaseExtensionStore[TItem]", name: str) -> bool:
        """Copy one item from another store. Default: copy2 single file."""
        source_path = source._item_path(name)
        if not source_path.is_file():
            return False
        target_path = self._item_path(name)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        return True

    def exists(self, name: str) -> bool:
        """Check if a valid item exists in this store."""
        raw = self.read_raw(name)
        return raw is not None

    def read_raw(self, name: str) -> str | None:
        """Read raw content text. Returns None if missing or filtered out."""
        path = self._item_path(name)
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", path, exc)
            return None
        if not self._include(name, text):
            return None
        return text

    def read(self, name: str) -> TItem | None:
        """Read and parse an item. Returns None if not found."""
        raw = self.read_raw(name)
        if raw is None:
            return None
        return self._parse(name, raw)

    def write(self, name: str, content: str) -> Path:
        """Write content for a named item. Returns the path written.

        Args:
            name: Kebab-case item name.
            content: Raw content (normalized before write).

        Returns:
            Path to the written file.

        Raises:
            ValueError: If name is not valid kebab-case.
        """
        if not VALID_EXTENSION_NAME.match(name):
            raise ValueError(f"Name must be kebab-case: {name!r}")
        normalized = self._normalize_content(content)
        path = self._item_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(normalized.rstrip() + "\n", encoding="utf-8")
        return path

    def delete(self, name: str) -> bool:
        """Remove the item. Returns True if deleted."""
        return self._delete_impl(name)

    def copy_from(self, source: "BaseExtensionStore[TItem]", name: str) -> bool:
        """Copy an item from another store. Returns True on success."""
        return self._copy_impl(source, name)

    @staticmethod
    def _replace_target(target: Path) -> None:
        """Remove a target path that may be a symlink, file, or directory.

        Necessary because ``shutil.rmtree`` refuses symlinks and ``Path.unlink``
        refuses non-symlink directories. No-op when target is missing.
        """
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target)

    def link_from(self, source: "BaseExtensionStore[TItem]", name: str) -> bool:
        """Create a symlink in this store pointing at the source's named item.

        Replaces any existing file/dir/symlink at the target path. Returns True
        on success. Raises ``OSError`` if the platform/filesystem doesn't
        support symlinks (Windows without dev mode, some FUSE mounts, etc.) so
        callers can fall back to copy.
        """
        source_root = source._item_root(name)
        if not source_root.exists():
            raise FileNotFoundError(f"source missing: {source_root}")

        target_root = self._item_root(name)
        target_root.parent.mkdir(parents=True, exist_ok=True)
        self._replace_target(target_root)

        target_root.symlink_to(
            source_root.resolve(), target_is_directory=source_root.is_dir()
        )
        return True

    def list_names(self) -> list[str]:
        """Return sorted list of valid item names passing the include filter."""
        if not self._root.is_dir():
            return []
        names: list[str] = []
        for candidate in self._iter_candidate_names():
            if not VALID_EXTENSION_NAME.match(candidate):
                continue
            raw = self.read_raw(candidate)
            if raw is None:
                continue
            names.append(candidate)
        return sorted(names)
