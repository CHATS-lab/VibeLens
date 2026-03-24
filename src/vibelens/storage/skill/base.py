"""Abstract base class for agent-specific skill storage backends.

Each backend knows how to discover, read, write, and search skills for one
agent type. The service layer composes multiple SkillStore instances to present
a unified view across all agents.
"""

import time
from abc import ABC, abstractmethod
from pathlib import Path

from vibelens.models.enums import AgentType
from vibelens.models.skill import SkillInfo
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 300


class SkillStore(ABC):
    """Abstract base for agent-specific skill storage backends.

    Provides cached listing with TTL. Subclasses implement the concrete
    discovery, parsing, read/write, and deletion logic for their agent type.
    """

    def __init__(self) -> None:
        self._cache: list[SkillInfo] | None = None
        self._cached_at: float = 0.0

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Agent type enum value for this store."""

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
