"""Skill management service — orchestrates central + agent stores."""

import time
from dataclasses import dataclass

from vibelens.models.extension.skill import VALID_SKILL_NAME, Skill
from vibelens.storage.extension.skill_store import SkillStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 300


@dataclass
class SyncTarget:
    """An agent platform available for skill sync."""

    key: str
    label: str
    skill_count: int
    skills_dir: str


class SkillService:
    """Orchestrates skill CRUD across central and agent stores."""

    def __init__(self, central: SkillStore, agents: dict[str, SkillStore]) -> None:
        self._central = central
        self._agents = agents
        self._cache: list[Skill] | None = None
        self._cache_at: float = 0.0

    def install(
        self,
        name: str,
        content: str,
        sync_to: list[str] | None = None,
    ) -> Skill:
        """Write skill to central store and optionally sync to agents.

        Args:
            name: Kebab-case skill name.
            content: Full SKILL.md content.
            sync_to: Agent keys to sync to after install.

        Returns:
            Installed Skill with installed_in populated.

        Raises:
            ValueError: If name invalid or content empty.
            FileExistsError: If skill already exists.
        """
        if not VALID_SKILL_NAME.match(name):
            raise ValueError(f"Skill name must be kebab-case: {name!r}")
        if not content.strip():
            raise ValueError("Skill content must not be empty")
        if self._central.exists(name):
            raise FileExistsError(f"Skill {name!r} already exists. Use modify() to update.")

        self._central.write(name, content)
        if sync_to:
            self.sync_to_agents(name, sync_to)
        self.invalidate()

        return self._read_with_agents(name)

    def import_from_agent(self, agent: str, name: str) -> Skill:
        """Copy a skill from an agent directory into central.

        Args:
            agent: Agent key (e.g. "claude").
            name: Skill name.

        Returns:
            Imported Skill.

        Raises:
            KeyError: If agent not found.
            FileNotFoundError: If skill not in agent dir.
        """
        store = self._resolve_agent(agent)
        if not store.exists(name):
            raise FileNotFoundError(f"Skill {name!r} not found in agent {agent!r}")

        self._central.copy_from(store, name)
        self.invalidate()
        return self._read_with_agents(name)

    def import_all_from_agent(self, agent: str, overwrite: bool = False) -> list[str]:
        """Import all skills from an agent directory. Returns imported names.

        Args:
            agent: Agent key.
            overwrite: If True, overwrite existing central skills.

        Returns:
            List of imported skill names.

        Raises:
            KeyError: If agent not found.
        """
        store = self._resolve_agent(agent)
        imported: list[str] = []
        for name in store.list_names():
            if not overwrite and self._central.exists(name):
                continue
            self._central.copy_from(store, name)
            imported.append(name)

        if imported:
            self.invalidate()
        return imported

    def uninstall(self, name: str) -> list[str]:
        """Delete from central and all agent stores.

        Args:
            name: Skill name.

        Returns:
            List of agent keys the skill was removed from.

        Raises:
            FileNotFoundError: If not in central.
        """
        if not self._central.exists(name):
            raise FileNotFoundError(f"Skill {name!r} not found in central store")

        removed_from: list[str] = []
        for agent_key, store in self._agents.items():
            if store.delete(name):
                removed_from.append(agent_key)

        self._central.delete(name)
        self.invalidate()
        return removed_from

    def uninstall_from_agent(self, name: str, agent: str) -> None:
        """Remove from a single agent store only.

        Args:
            name: Skill name.
            agent: Agent key.

        Raises:
            KeyError: If agent not found.
            FileNotFoundError: If skill not in that agent.
        """
        store = self._resolve_agent(agent)
        if not store.exists(name):
            raise FileNotFoundError(f"Skill {name!r} not in agent {agent!r}")
        store.delete(name)
        self.invalidate()

    def list_skills(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str | None = None,
    ) -> tuple[list[Skill], int]:
        """List skills with pagination and optional search.

        Args:
            page: 1-based page number.
            page_size: Items per page.
            search: Case-insensitive substring match on name/description.

        Returns:
            Tuple of (page items, total matching count).
        """
        all_skills = self._get_cached()

        if search:
            query = search.lower()
            all_skills = [
                s for s in all_skills
                if query in s.name.lower() or query in s.description.lower()
            ]

        total = len(all_skills)
        start = (max(page, 1) - 1) * page_size
        page_items = all_skills[start : start + page_size]
        return page_items, total

    def get_skill(self, name: str) -> Skill:
        """Get a single skill with installed_in populated.

        Args:
            name: Skill name.

        Returns:
            Skill with installed_in set.

        Raises:
            FileNotFoundError: If not found.
        """
        return self._read_with_agents(name)

    def get_skill_content(self, name: str) -> str:
        """Get raw SKILL.md text.

        Args:
            name: Skill name.

        Returns:
            Raw SKILL.md content.

        Raises:
            FileNotFoundError: If not found.
        """
        raw = self._central.read_raw(name)
        if raw is None:
            raise FileNotFoundError(f"Skill {name!r} not found")
        return raw

    def find_installed_agents(self, name: str) -> list[str]:
        """Return agent keys where this skill exists on disk."""
        return [key for key, store in self._agents.items() if store.exists(name)]

    def list_sync_targets(self) -> list[SyncTarget]:
        """List available agent platforms with skill counts."""
        return [
            SyncTarget(
                key=key,
                label=key.replace("_", " ").title(),
                skill_count=len(store.list_names()),
                skills_dir=str(store.root),
            )
            for key, store in self._agents.items()
        ]

    def modify(self, name: str, content: str) -> Skill:
        """Update skill content. Auto-syncs to agents that already have it.

        Args:
            name: Skill name.
            content: New SKILL.md content.

        Returns:
            Updated Skill.

        Raises:
            FileNotFoundError: If not in central.
        """
        if not self._central.exists(name):
            raise FileNotFoundError(f"Skill {name!r} not found in central store")

        self._central.write(name, content)

        for agent_key, store in self._agents.items():
            if store.exists(name):
                self._central_to_agent(name, agent_key)

        self.invalidate()
        return self._read_with_agents(name)

    def sync_to_agents(self, name: str, agents: list[str]) -> dict[str, bool]:
        """Copy skill from central to specified agents.

        Args:
            name: Skill name.
            agents: Agent keys to sync to.

        Returns:
            Dict mapping agent key to success boolean.

        Raises:
            FileNotFoundError: If not in central.
        """
        if not self._central.exists(name):
            raise FileNotFoundError(f"Skill {name!r} not found in central store")

        results: dict[str, bool] = {}
        for agent_key in agents:
            results[agent_key] = self._central_to_agent(name, agent_key)

        self.invalidate()
        return results

    def invalidate(self) -> None:
        """Clear cached skill list."""
        self._cache = None
        self._cache_at = 0.0

    def _get_cached(self) -> list[Skill]:
        """Return cached skill list, refreshing if stale."""
        now = time.monotonic()
        if self._cache is None or (now - self._cache_at) > CACHE_TTL_SECONDS:
            skills = []
            for name in self._central.list_names():
                skill = self._central.read(name)
                if skill:
                    skill.installed_in = self.find_installed_agents(name)
                    skills.append(skill)
            self._cache = skills
            self._cache_at = now
        return self._cache

    def _read_with_agents(self, name: str) -> Skill:
        """Read a skill from central and populate installed_in."""
        skill = self._central.read(name)
        if skill is None:
            raise FileNotFoundError(f"Skill {name!r} not found")
        skill.installed_in = self.find_installed_agents(name)
        return skill

    def _resolve_agent(self, agent: str) -> SkillStore:
        """Look up an agent store by key."""
        store = self._agents.get(agent)
        if store is None:
            raise KeyError(f"Unknown agent: {agent!r}")
        return store

    def _central_to_agent(self, name: str, agent_key: str) -> bool:
        """Copy skill from central to one agent. Returns False if agent unknown."""
        store = self._agents.get(agent_key)
        if store is None:
            logger.warning("Unknown agent %r, skipping sync", agent_key)
            return False
        return store.copy_from(self._central, name)
