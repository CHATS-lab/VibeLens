"""Hook management service — extends BaseExtensionService with JSON merge sync.

Unlike commands/subagents (where agent-side storage is a directory of .md files),
hooks live inside each agent's ``settings.json`` under the top-level ``hooks`` key.
Sync merges each event/group from the central hook into the agent's settings.json,
tagging every inserted group with ``_vibelens_managed: {hook_name}`` so the group
can be located for later unsync/modify operations without touching unmanaged entries.
"""

import copy
import json
from pathlib import Path

from vibelens.models.extension.hook import Hook
from vibelens.models.extension.item import VALID_EXTENSION_NAME
from vibelens.services.extensions.base_service import (
    DEFAULT_LINK_TYPE,
    BaseExtensionService,
    LinkType,
    SyncTarget,
)
from vibelens.storage.extension.hook_store import HookStore, serialize_hook
from vibelens.utils.json import atomic_write_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

VIBELENS_MARKER_KEY = "_vibelens_managed"
HOOKS_ROOT_KEY = "hooks"
JSON_INDENT = 2


class HookService(BaseExtensionService[Hook]):
    """Hook-specific service. Overrides sync for JSON merge into settings.json."""

    def __init__(self, central: HookStore, agents: dict[str, Path]) -> None:
        """Create a HookService.

        Args:
            central: Central HookStore under ``~/.vibelens/hooks/``.
            agents: Map of agent key to each agent's hook config JSON path.
        """
        super().__init__(central_store=central, agent_stores={})
        self._hook_config_paths: dict[str, Path] = {str(k): v for k, v in agents.items()}

    def install(
        self,
        name: str,
        description: str = "",
        topics: list[str] | None = None,
        hook_config: dict[str, list[dict]] | None = None,
        sync_to: list[str] | None = None,
        content: str | None = None,
        link_type: LinkType = DEFAULT_LINK_TYPE,
    ) -> Hook:
        """Install a hook. Accepts structured fields or raw JSON content.

        Args:
            name: Kebab-case hook name.
            description: Human description.
            topics: Topics for discovery.
            hook_config: Event-name to list-of-hook-groups mapping.
            sync_to: Agent keys to sync to after install.
            content: Raw JSON content (overrides structured fields if provided).

        Returns:
            Installed Hook with installed_in populated.

        Raises:
            ValueError: If name is not valid kebab-case.
            FileExistsError: If hook already exists.
        """
        if not VALID_EXTENSION_NAME.match(name):
            raise ValueError(f"Hook name must be kebab-case: {name!r}")
        if self._central.exists(name):
            raise FileExistsError(f"Hook {name!r} already exists. Use modify() to update.")

        if content is None:
            hook = Hook(
                name=name,
                description=description,
                topics=topics or [],
                hook_config=hook_config or {},
            )
            content = serialize_hook(hook)

        self._central.write(name, content)
        self._invalidate_cache()
        if sync_to:
            self.sync_to_agents(name, sync_to)
        return self.get_item(name)

    def modify(
        self,
        name: str,
        description: str | None = None,
        topics: list[str] | None = None,
        hook_config: dict[str, list[dict]] | None = None,
        content: str | None = None,
        link_type: LinkType = DEFAULT_LINK_TYPE,
    ) -> Hook:
        """Partial update. None fields are left unchanged.

        Args:
            name: Hook name.
            description: New description, or None to keep current.
            topics: New topics, or None to keep current.
            hook_config: New hook_config, or None to keep current.
            content: Raw JSON content (overrides structured fields if provided).

        Returns:
            Updated Hook.

        Raises:
            FileNotFoundError: If hook not in central.
        """
        existing = self._central.read(name)
        if existing is None:
            raise FileNotFoundError(f"Hook {name!r} not found in central store")

        if content is None:
            hook = Hook(
                name=name,
                description=description if description is not None else existing.description,
                topics=topics if topics is not None else existing.topics,
                hook_config=hook_config if hook_config is not None else existing.hook_config,
            )
            content = serialize_hook(hook)

        self._central.write(name, content)
        self._invalidate_cache()

        for agent_key in self._find_installed_agents(name):
            self._sync_to_agent_by_key(name, agent_key)

        return self.get_item(name)

    def uninstall(self, name: str) -> list[str]:
        """Delete from central and remove from every agent settings.json.

        Args:
            name: Hook name.

        Returns:
            List of agent keys the hook was removed from.

        Raises:
            FileNotFoundError: If hook not in central.
        """
        if not self._central.exists(name):
            raise FileNotFoundError(f"Hook {name!r} not found in central store")

        removed_from = self._find_installed_agents(name)
        for agent_key in removed_from:
            self._remove_marker_from_settings(name, agent_key)

        self._central.delete(name)
        self._invalidate_cache()
        return removed_from

    def uninstall_from_agent(self, name: str, agent: str) -> None:
        """Remove the hook from a single agent's settings.json only.

        Args:
            name: Hook name.
            agent: Agent key.

        Raises:
            KeyError: If agent not found.
            FileNotFoundError: If hook not installed in that agent.
        """
        agent_key = self._resolve_agent_key(agent)
        if not self._agent_has_marker(name, agent_key):
            raise FileNotFoundError(f"Hook {name!r} not in agent {agent!r}")
        self._remove_marker_from_settings(name, agent_key)
        self._invalidate_cache()

    def sync_to_agents(
        self,
        name: str,
        agents: list[str],
        link_type: LinkType = DEFAULT_LINK_TYPE,
    ) -> dict[str, bool]:
        """Merge central hook into each listed agent's settings.json.

        Args:
            name: Hook name.
            agents: Agent keys to sync to.

        Returns:
            Dict mapping agent key to success boolean (False if agent unknown).

        Raises:
            FileNotFoundError: If hook not in central.
        """
        if not self._central.exists(name):
            raise FileNotFoundError(f"Hook {name!r} not found in central store")

        results: dict[str, bool] = {}
        for agent_key_raw in agents:
            try:
                agent_key = self._resolve_agent_key(agent_key_raw)
            except KeyError:
                logger.warning("Unknown agent %r, skipping sync", agent_key_raw)
                results[agent_key_raw] = False
                continue
            self._sync_to_agent_by_key(name, agent_key)
            results[agent_key_raw] = True

        self._invalidate_cache()
        return results

    def import_from_agent(
        self, agent: str, name: str, event_name: str | None = None, matcher: str | None = None
    ) -> Hook:
        """Extract a hook group from an agent's settings.json into central.

        Args:
            agent: Agent key (e.g. "claude").
            name: Name for the new central hook.
            event_name: Event name to look up (e.g. "PreToolUse").
            matcher: Matcher field on the group to locate.

        Returns:
            Created Hook stored in central.

        Raises:
            ValueError: If name is not valid kebab-case.
            KeyError: If agent not found.
            FileNotFoundError: If no matching hook group found.
            FileExistsError: If a central hook with this name already exists.
        """
        if not VALID_EXTENSION_NAME.match(name):
            raise ValueError(f"Hook name must be kebab-case: {name!r}")
        if self._central.exists(name):
            raise FileExistsError(f"Hook {name!r} already exists in central store")

        agent_key = self._resolve_agent_key(agent)
        settings = self._read_settings(self._hook_config_paths[agent_key])
        groups = settings.get(HOOKS_ROOT_KEY, {}).get(event_name, [])
        matching = [g for g in groups if g.get("matcher") == matcher]
        if not matching:
            raise FileNotFoundError(
                f"No hook group for event={event_name!r} matcher={matcher!r} in agent {agent!r}"
            )

        stripped = [_strip_marker(g) for g in matching]
        hook = Hook(name=name, hook_config={event_name: stripped})
        self._central.write(name, serialize_hook(hook))
        self._invalidate_cache()
        return self.get_item(name)

    def list_sync_targets(self) -> list[SyncTarget]:
        """Return sync targets with each agent's hook config path."""
        return [
            SyncTarget(
                agent=agent_key,
                count=self._count_managed_hooks(path),
                dir=str(path),
            )
            for agent_key, path in self._hook_config_paths.items()
        ]

    def _find_installed_agents(self, name: str) -> list[str]:
        """Return agent keys whose settings.json has any group marked with this hook."""
        return [key for key in self._hook_config_paths if self._agent_has_marker(name, key)]

    def _sync_to_agent_by_key(self, name: str, agent_key: str) -> None:
        """Merge central hook into one agent's settings.json."""
        hook = self._central.read(name)
        if hook is None:
            return

        path = self._hook_config_paths[agent_key]
        settings = self._read_settings(path)
        hooks_root = settings.setdefault(HOOKS_ROOT_KEY, {})

        for event_name, groups in hook.hook_config.items():
            existing = hooks_root.get(event_name, [])
            cleaned = [g for g in existing if g.get(VIBELENS_MARKER_KEY) != name]
            for group in groups:
                tagged = {**copy.deepcopy(group), VIBELENS_MARKER_KEY: name}
                cleaned.append(tagged)
            hooks_root[event_name] = cleaned

        self._write_settings(path, settings)

    def _remove_marker_from_settings(self, name: str, agent_key: str) -> None:
        """Remove every hook group tagged with ``name`` from this agent's settings."""
        path = self._hook_config_paths[agent_key]
        settings = self._read_settings(path)
        hooks_root = settings.get(HOOKS_ROOT_KEY, {})
        if not hooks_root:
            return

        cleaned_root: dict[str, list[dict]] = {}
        for event_name, groups in hooks_root.items():
            kept = [g for g in groups if g.get(VIBELENS_MARKER_KEY) != name]
            if kept:
                cleaned_root[event_name] = kept

        if cleaned_root:
            settings[HOOKS_ROOT_KEY] = cleaned_root
        else:
            settings.pop(HOOKS_ROOT_KEY, None)
        self._write_settings(path, settings)

    def _agent_has_marker(self, name: str, agent_key: str) -> bool:
        """Return True if the agent's settings.json contains any group marked with this hook."""
        path = self._hook_config_paths[agent_key]
        settings = self._read_settings(path)
        hooks_root = settings.get(HOOKS_ROOT_KEY, {})
        for groups in hooks_root.values():
            if any(g.get(VIBELENS_MARKER_KEY) == name for g in groups):
                return True
        return False

    def _count_managed_hooks(self, path: Path) -> int:
        """Count unique managed hook names across all event groups in an agent settings.json."""
        settings = self._read_settings(path)
        hooks_root = settings.get(HOOKS_ROOT_KEY, {})
        names: set[str] = set()
        for groups in hooks_root.values():
            for group in groups:
                marker = group.get(VIBELENS_MARKER_KEY)
                if isinstance(marker, str):
                    names.add(marker)
        return len(names)

    def _resolve_agent_key(self, agent: str) -> str:
        """Look up an agent key from the settings paths dict."""
        key = agent.value if hasattr(agent, "value") else str(agent)
        if key not in self._hook_config_paths:
            raise KeyError(f"Unknown agent: {agent!r}")
        return key

    def _read_settings(self, path: Path) -> dict:
        """Read settings.json. Returns empty dict if missing or invalid."""
        if not path.is_file():
            return {}
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cannot read settings.json at %s: %s", path, exc)
            return {}
        return data if isinstance(data, dict) else {}

    def _write_settings(self, path: Path, data: dict) -> None:
        """Write settings.json atomically (tmp file + rename)."""
        atomic_write_json(path, data, indent=JSON_INDENT)


def _strip_marker(group: dict) -> dict:
    """Return a deep copy of a hook group with the VibeLens marker removed."""
    stripped = copy.deepcopy(group)
    stripped.pop(VIBELENS_MARKER_KEY, None)
    return stripped
