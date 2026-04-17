"""Generic base service for extension management (skills, commands, hooks, subagents)."""

import time
from dataclasses import dataclass
from typing import Generic, TypeVar

from vibelens.storage.extension.base_store import (
    VALID_EXTENSION_NAME,
    BaseExtensionStore,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

CACHE_TTL_SECONDS = 300


@dataclass
class SyncTarget:
    """Unified sync target for all extension types."""

    agent: str
    count: int
    dir: str


class BaseExtensionService(Generic[T]):
    """Orchestrates extension CRUD across a central store and agent stores.

    Subclasses override ``_sync_to_agent`` / ``_unsync_from_agent`` for
    type-specific agent-side behavior (e.g. HookService does JSON merge
    instead of file copy).
    """

    def __init__(
        self,
        central_store: BaseExtensionStore[T],
        agent_stores: dict[str, BaseExtensionStore[T]],
        cache_ttl: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._central = central_store
        self._agents = agent_stores
        self._cache: list[T] | None = None
        self._cache_at: float = 0.0
        self._cache_ttl = cache_ttl

    def install(self, name: str, content: str, sync_to: list[str] | None = None) -> T:
        """Write to central store and optionally sync to agents."""
        if not VALID_EXTENSION_NAME.match(name):
            raise ValueError(f"Extension name must be kebab-case: {name!r}")
        if not content.strip():
            raise ValueError("Extension content must not be empty")
        if self._central.exists(name):
            raise FileExistsError(f"Extension {name!r} already exists. Use modify() to update.")
        logger.debug("Writing %r to central store at %s", name, self._central.root)
        self._central.write(name, content)
        self._invalidate_cache()
        if sync_to:
            results = self.sync_to_agents(name, sync_to)
            failed = [k for k, ok in results.items() if not ok]
            if failed:
                logger.error("Sync failed for agents: %s", failed)
        return self.get_item(name)

    def modify(self, name: str, content: str) -> T:
        """Update content in central store and auto-sync to agents that have it."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found in central store")
        self._central.write(name, content)
        self._invalidate_cache()
        for agent_key in self._find_installed_agents(name):
            store = self._agents.get(agent_key)
            if store:
                self._sync_to_agent(name, store)
        return self.get_item(name)

    def uninstall(self, name: str) -> list[str]:
        """Delete from central and all agent stores. Returns agents removed from."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found")
        removed_from: list[str] = []
        for agent_key, store in self._agents.items():
            if store.exists(name):
                self._unsync_from_agent(name, store)
                removed_from.append(agent_key)
        self._central.delete(name)
        self._invalidate_cache()
        return removed_from

    def uninstall_from_agent(self, name: str, agent: str) -> None:
        """Remove from a single agent store."""
        store = self._agents.get(agent)
        if store is None:
            raise KeyError(f"Unknown agent: {agent!r}")
        if not store.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not in agent {agent!r}")
        self._unsync_from_agent(name, store)

    def import_from_agent(self, agent: str, name: str) -> T:
        """Copy an extension from an agent store into central."""
        store = self._agents.get(agent)
        if store is None:
            raise KeyError(f"Unknown agent: {agent!r}")
        if not store.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not in agent {agent!r}")
        self._central.copy_from(store, name)
        self._invalidate_cache()
        return self.get_item(name)

    def import_all_from_agent(self, agent: str, overwrite: bool = False) -> list[str]:
        """Import all extensions from an agent store. Returns names imported.

        Args:
            agent: Agent key.
            overwrite: If True, overwrite existing central extensions.
        """
        store = self._agents.get(agent)
        if store is None:
            raise KeyError(f"Unknown agent: {agent!r}")
        imported: list[str] = []
        for name in store.list_names():
            if not overwrite and self._central.exists(name):
                continue
            self._central.copy_from(store, name)
            imported.append(name)
        if imported:
            self._invalidate_cache()
        return imported

    def import_all_agents(self) -> None:
        """Import from all known agent stores."""
        for agent_key in self._agents:
            try:
                self.import_all_from_agent(agent_key)
            except Exception:
                logger.warning("Failed to import from agent %s", agent_key, exc_info=True)

    def list_items(
        self, page: int = 1, page_size: int = 50, search: str | None = None
    ) -> tuple[list[T], int]:
        """List extensions with pagination and optional search."""
        all_items = self._get_cached_items()
        if search:
            term = search.lower()
            all_items = [i for i in all_items if self._matches_search(i, term)]
        total = len(all_items)
        start = (page - 1) * page_size
        return all_items[start : start + page_size], total

    def get_item(self, name: str) -> T:
        """Get a single extension by name with installed_in populated."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found")
        item = self._central.read(name)
        self._populate_installed_in(item, name)
        return item

    def get_item_content(self, name: str) -> str:
        """Get raw content of an extension."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found")
        return self._central.read_raw(name)

    def get_item_path(self, name: str) -> str:
        """Get the central store path for an extension."""
        return str(self._central._item_path(name))

    def sync_to_agents(self, name: str, agents: list[str]) -> dict[str, bool]:
        """Copy extension from central to specified agents. Returns per-agent success."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found in central store")
        logger.debug("Syncing %r to agents %s (known: %s)", name, agents, list(self._agents.keys()))
        results: dict[str, bool] = {}
        for agent_key in agents:
            store = self._agents.get(agent_key)
            if store is None:
                logger.warning("Unknown agent %r, skipping sync", agent_key)
                results[agent_key] = False
            else:
                logger.debug("Copying %r to agent %r at %s", name, agent_key, store.root)
                self._sync_to_agent(name, store)
                results[agent_key] = True
        self._invalidate_cache()
        return results

    def invalidate(self) -> None:
        """Clear the item cache."""
        self._invalidate_cache()

    def list_sync_targets(self) -> list[SyncTarget]:
        """Return available agent sync targets with item counts."""
        return [
            SyncTarget(agent=agent_key, count=len(store.list_names()), dir=str(store._root))
            for agent_key, store in self._agents.items()
        ]

    def _sync_to_agent(self, name: str, agent_store: BaseExtensionStore[T]) -> None:
        """Copy extension from central to agent store. Override for hooks."""
        agent_store.copy_from(self._central, name)

    def _unsync_from_agent(self, name: str, agent_store: BaseExtensionStore[T]) -> None:
        """Remove extension from agent store. Override for hooks."""
        agent_store.delete(name)

    def _find_installed_agents(self, name: str) -> list[str]:
        return [k for k, s in self._agents.items() if s.exists(name)]

    def _populate_installed_in(self, item: T, name: str) -> None:
        installed = self._find_installed_agents(name)
        if hasattr(item, "installed_in"):
            item.installed_in = installed  # type: ignore[attr-defined]

    def _matches_search(self, item: T, term: str) -> bool:
        name = getattr(item, "name", "")
        desc = getattr(item, "description", "")
        tags = getattr(item, "tags", [])
        return term in name.lower() or term in desc.lower() or any(term in t.lower() for t in tags)

    def _get_cached_items(self) -> list[T]:
        now = time.time()
        if self._cache is not None and (now - self._cache_at) < self._cache_ttl:
            return list(self._cache)
        names = sorted(self._central.list_names())
        items = []
        for name in names:
            try:
                item = self._central.read(name)
                self._populate_installed_in(item, name)
                items.append(item)
            except Exception:
                logger.warning("Failed to read extension %s", name, exc_info=True)
        self._cache = items
        self._cache_at = now
        return list(items)

    def _invalidate_cache(self) -> None:
        self._cache = None
        self._cache_at = 0.0
