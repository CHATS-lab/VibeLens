"""Base class for all skill storage backends."""

import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path

from vibelens.models.skill import SkillInfo, SkillSourceType
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# How long get_cached() reuses its in-memory list before rescanning disk
CACHE_TTL_SECONDS = 300


class BaseSkillStore(ABC):
    """Abstract base for all skill stores.

    Both the central VibeLens store and agent-native stores inherit from this
    class. The common abstraction is: a directory of named skills that can be
    listed, read, written, deleted, and copied between stores.
    """

    def __init__(self) -> None:
        self._cache: list[SkillInfo] | None = None
        self._cached_at: float = 0.0

    @property
    @abstractmethod
    def source_type(self) -> SkillSourceType:
        """Unified source/store type for this store."""

    @property
    @abstractmethod
    def skills_dir(self) -> Path:
        """Root directory for this agent's skills."""

    @abstractmethod
    def list_skills(self) -> list[SkillInfo]:
        """List all installed skills with metadata (fresh scan)."""

    @abstractmethod
    def get_skill(self, name: str) -> SkillInfo | None:
        """Look up a single skill by name."""

    @abstractmethod
    def read_content(self, name: str) -> str | None:
        """Read the full skill definition file content."""

    @abstractmethod
    def write_skill(self, name: str, content: str) -> Path:
        """Create or overwrite a skill's definition file.

        Returns:
            Absolute path to the written file.

        Raises:
            ValueError: If name is invalid kebab-case.
        """

    @abstractmethod
    def delete_skill(self, name: str) -> bool:
        """Remove an installed skill entirely.

        Returns:
            True if the skill was deleted, False if it did not exist.
        """

    def skill_path(self, name: str) -> Path:
        """Return the directory path for one skill."""
        return self.skills_dir / name

    def import_skill_from(
        self, source_store: "BaseSkillStore", name: str, overwrite: bool = False
    ) -> SkillInfo | None:
        """Copy one skill directory from another store into this store."""
        source_dir = source_store.skill_path(name)
        if not source_dir.is_dir():
            return None

        target_dir = self.skill_path(name)
        # Symlinks (e.g. from skillshub) must be unlinked before copytree
        if target_dir.is_symlink():
            if not overwrite:
                return self.get_skill(name)
            target_dir.unlink()
        elif target_dir.exists():
            if not overwrite:
                return self.get_skill(name)
            shutil.rmtree(target_dir)

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target_dir)
        self.invalidate_cache()
        return self.get_skill(name)

    def import_all_from(
        self, source_store: "BaseSkillStore", overwrite: bool = False
    ) -> list[SkillInfo]:
        """Copy every skill from another store into this store."""
        imported: list[SkillInfo] = []
        for skill in source_store.get_cached():
            copied = self.import_skill_from(source_store, skill.name, overwrite=overwrite)
            if copied:
                imported.append(copied)
        return imported

    def search_skills(self, query: str) -> list[SkillInfo]:
        """Search skills by name or description substring (case-insensitive)."""
        query_lower = query.lower()
        return [
            s
            for s in self.get_cached()
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]

    def get_cached(self) -> list[SkillInfo]:
        """Return cached skill list, rescanning if stale."""
        now = time.monotonic()
        if self._cache is None or (now - self._cached_at) > CACHE_TTL_SECONDS:
            self._cache = self.list_skills()
            self._cached_at = now
        return self._cache

    def invalidate_cache(self) -> None:
        """Force next get_cached() to rescan."""
        self._cache = None
        self._cached_at = 0.0
