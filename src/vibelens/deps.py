"""Dependency injection singletons for VibeLens.

Service/store classes are imported inside factories to break import cycles
with the service registries under ``vibelens.services.extensions``.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from vibelens.config import (
    InferenceConfig,
    Settings,
    load_settings,
    save_inference_config,
)
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.backends import create_backend_from_config
from vibelens.models.enums import AgentExtensionType, AppMode
from vibelens.storage.trajectory.base import BaseTrajectoryStore
from vibelens.storage.trajectory.disk import DiskTrajectoryStore
from vibelens.storage.trajectory.local import LocalTrajectoryStore
from vibelens.utils.json import read_jsonl
from vibelens.utils.log import get_logger

# Sentinel for "key absent from _registry".
_MISSING = object()
# Sentinel for "inference_backend never resolved"; None is a valid cached value.
_NOT_CHECKED = object()
# Lazy singleton registry: name -> instance (e.g. "settings", "skill_service").
_registry: dict[str, Any] = {}
# session_token -> upload stores belonging to that browser tab.
_upload_registry: dict[str, list[DiskTrajectoryStore]] = {}

logger = get_logger(__name__)


def _get_or_create(key: str, factory: Callable[[], Any]) -> Any:
    """Return a cached singleton, creating it on first access."""
    value = _registry.get(key, _MISSING)
    if value is _MISSING:
        value = factory()
        _registry[key] = value
    return value


def reset_singletons() -> None:
    """Clear all cached singletons and upload registry for test isolation."""
    _registry.clear()
    _upload_registry.clear()


def get_settings() -> Settings:
    """Return cached application settings."""
    return _get_or_create("settings", load_settings)


def set_settings(settings: Settings) -> None:
    """Pre-register settings so get_settings() returns them."""
    _registry["settings"] = settings


def is_demo_mode() -> bool:
    """Check whether the application is running in demo mode."""
    return get_settings().mode == AppMode.DEMO


def is_test_mode() -> bool:
    """Check whether the application is running in test mode."""
    return get_settings().mode == AppMode.TEST


def get_share_service():
    """Return cached ShareService singleton."""

    def _create():
        from vibelens.services.session.share import ShareService

        return ShareService(get_settings().storage.share_dir)

    return _get_or_create("share_service", _create)


def get_friction_store():
    """Return cached FrictionStore singleton."""

    def _create():
        from vibelens.services.friction.store import FrictionStore

        return FrictionStore(get_settings().storage.friction_dir)

    return _get_or_create("friction_store", _create)


def _iter_supporting(extension_type: AgentExtensionType) -> Iterator[tuple[str, Any]]:
    """Yield (agent_key, platform) for installed platforms supporting ``extension_type``."""
    from vibelens.services.extensions.platforms import installed_platforms

    for key, platform in installed_platforms().items():
        if extension_type in platform.supported_types:
            yield key, platform


def _build_simple_stores(
    extension_type: AgentExtensionType, dir_attr: str, store_class: Callable[..., Any]
) -> dict[str, Any]:
    """Build a per-agent store dict for extension types with a single source dir.

    Skips platforms whose ``dir_attr`` is None.
    """
    stores: dict[str, Any] = {}
    for key, platform in _iter_supporting(extension_type):
        source_dir = getattr(platform, dir_attr)
        if source_dir is None:
            continue
        stores[key] = store_class(source_dir.expanduser().resolve(), create=True)
    return stores


def get_skill_service():
    """Return cached SkillService singleton."""

    def _create():
        from vibelens.services.extensions.skill_service import SkillService
        from vibelens.storage.extension.skill_store import SkillStore

        settings = get_settings()
        central = SkillStore(settings.storage.managed_skills_dir, create=True)
        agents = _build_simple_stores(AgentExtensionType.SKILL, "skills_dir", SkillStore)
        return SkillService(central=central, agents=agents)

    return _get_or_create("skill_service", _create)


def get_command_service():
    """Return cached CommandService singleton."""

    def _create():
        from vibelens.services.extensions.command_service import CommandService
        from vibelens.storage.extension.command_store import CommandStore

        settings = get_settings()
        central = CommandStore(settings.storage.managed_commands_dir, create=True)
        agents = _build_simple_stores(AgentExtensionType.COMMAND, "commands_dir", CommandStore)
        return CommandService(central=central, agents=agents)

    return _get_or_create("command_service", _create)


def get_subagent_service():
    """Return cached SubagentService singleton."""

    def _create():
        from vibelens.services.extensions.subagent_service import SubagentService
        from vibelens.storage.extension.subagent_store import SubagentStore

        settings = get_settings()
        central = SubagentStore(settings.storage.managed_subagents_dir, create=True)
        agents = _build_simple_stores(AgentExtensionType.SUBAGENT, "subagents_dir", SubagentStore)
        return SubagentService(central=central, agents=agents)

    return _get_or_create("subagent_service", _create)


def get_hook_service():
    """Return cached HookService singleton."""

    def _create():
        from vibelens.services.extensions.hook_service import HookService
        from vibelens.storage.extension.hook_store import HookStore

        settings = get_settings()
        central = HookStore(settings.storage.managed_hooks_dir, create=True)
        agent_settings = _build_agent_hook_config_paths()
        return HookService(central=central, agents=agent_settings)

    return _get_or_create("hook_service", _create)


def get_plugin_service():
    """Return cached PluginService singleton."""

    def _create():
        from vibelens.services.extensions.plugin_service import PluginService
        from vibelens.storage.extension.plugin_stores import PluginStore

        settings = get_settings()
        central = PluginStore(settings.storage.managed_plugins_dir, create=True)
        agent_plugin_stores = _build_agent_plugin_stores()
        return PluginService(central=central, agents=agent_plugin_stores)

    return _get_or_create("plugin_service", _create)


def get_collection_service():
    """Return cached CollectionService singleton."""

    def _create():
        from vibelens.services.extensions.collection_service import CollectionService
        from vibelens.storage.extension.collection_store import CollectionStore

        settings = get_settings()
        store = CollectionStore(settings.storage.managed_collections_dir, create=True)
        services_by_type = {
            AgentExtensionType.SKILL: get_skill_service(),
            AgentExtensionType.COMMAND: get_command_service(),
            AgentExtensionType.SUBAGENT: get_subagent_service(),
            AgentExtensionType.HOOK: get_hook_service(),
            AgentExtensionType.PLUGIN: get_plugin_service(),
        }
        return CollectionService(store=store, services_by_type=services_by_type)

    return _get_or_create("collection_service", _create)


def _build_agent_plugin_stores() -> dict:
    """Build agent plugin store instances from platform registry.

    Each agent uses the store class that matches its on-disk manifest
    layout: Claude goes through the 4-file marketplace merge; Codex,
    Cursor, and Copilot use the canonical Claude-shape layout with
    renamed manifest directories; Gemini uses a flat
    ``gemini-extension.json`` with field translation.
    """
    from vibelens.models.enums import AgentType
    from vibelens.storage.extension.plugin_stores import (
        ClaudePluginStore,
        CodexPluginStore,
        CopilotPluginStore,
        CursorPluginStore,
        GeminiPluginStore,
        PluginStore,
    )

    store_class_map = {
        AgentType.CODEX: CodexPluginStore,
        AgentType.CURSOR: CursorPluginStore,
        AgentType.COPILOT: CopilotPluginStore,
        AgentType.GEMINI: GeminiPluginStore,
    }

    stores: dict = {}
    for key, platform in _iter_supporting(AgentExtensionType.PLUGIN):
        if platform.source == AgentType.CLAUDE:
            cache_root = platform.root.expanduser() / "plugins" / "cache"
            stores[key] = ClaudePluginStore(cache_root, create=True)
            continue
        if platform.plugins_dir is None:
            continue
        store_class = store_class_map.get(platform.source, PluginStore)
        stores[key] = store_class(platform.plugins_dir.expanduser().resolve(), create=True)
    return stores


def _build_agent_hook_config_paths() -> dict[str, Path]:
    """Build mapping of agent key to each platform's hook config file path.

    The file does not need to exist yet — it will be created on first sync.
    """
    paths: dict[str, Path] = {}
    for key, platform in _iter_supporting(AgentExtensionType.HOOK):
        if platform.hook_config_path is None:
            continue
        paths[key] = platform.hook_config_path.expanduser().resolve()
    return paths


def _personalization_store_for(subdir: str, registry_key: str):
    """Return a cached PersonalizationStore scoped to one mode subdirectory."""

    def _create():
        from vibelens.services.personalization.store import PersonalizationStore

        base = get_settings().storage.personalization_dir
        return PersonalizationStore(base / subdir)

    return _get_or_create(registry_key, _create)


def get_creation_store():
    """Return cached PersonalizationStore for creation results."""
    return _personalization_store_for("creation", "creation_store")


def get_evolution_store():
    """Return cached PersonalizationStore for evolution results."""
    return _personalization_store_for("evolution", "evolution_store")


def get_recommendation_store():
    """Return cached PersonalizationStore for recommendation results."""
    return _personalization_store_for("recommendation", "recommendation_store")


def get_inference_config() -> InferenceConfig:
    """Return the inference config from cached settings."""
    return get_settings().inference


def set_inference_config(config: InferenceConfig) -> None:
    """Update inference config, persist to settings.json, and recreate backend."""
    settings = get_settings()
    settings.inference = config
    save_inference_config(config)

    backend = create_backend_from_config(config)
    set_inference_backend(backend)


def get_inference_backend() -> InferenceBackend | None:
    """Return cached InferenceBackend, or None if disabled."""
    value = _registry.get("inference_backend", _NOT_CHECKED)
    if value is not _NOT_CHECKED:
        return value

    from vibelens.llm.backends import create_backend_from_config

    backend = create_backend_from_config(get_inference_config())
    set_inference_backend(backend)
    return backend


def set_inference_backend(backend: InferenceBackend | None) -> None:
    """Replace the inference backend singleton at runtime."""
    _registry["inference_backend"] = backend


def get_upload_stores(session_token: str | None) -> list[DiskTrajectoryStore]:
    """Return upload stores for a given session_token.

    Args:
        session_token: Browser tab UUID identifying the user.

    Returns:
        List of DiskStore instances belonging to this token, or empty list.
    """
    if not session_token:
        return []
    return _upload_registry.get(session_token, [])


def get_all_upload_stores() -> list[DiskTrajectoryStore]:
    """Return all upload stores across all tokens.

    Used for token-agnostic lookups like shared session resolution,
    where the viewer's token differs from the uploader's.

    Returns:
        Flat list of every registered upload DiskStore.
    """
    stores: list[DiskTrajectoryStore] = []
    for token_stores in _upload_registry.values():
        stores.extend(token_stores)
    return stores


def register_upload_store(session_token: str, store: DiskTrajectoryStore) -> None:
    """Register an upload store for a session_token.

    Args:
        session_token: Browser tab UUID that owns this upload.
        store: DiskStore instance for the upload directory.
    """
    _upload_registry.setdefault(session_token, []).append(store)
    logger.info(
        "Registered upload store for token=%s root=%s (total=%d)",
        session_token[:8],
        store.root,
        len(_upload_registry[session_token]),
    )


def reconstruct_upload_registry() -> None:
    """Rebuild the per-user upload registry from metadata.jsonl on startup.

    Reads the global metadata.jsonl (one record per upload), creates a
    DiskStore for each upload_id, and registers it under its session_token.
    Uploads without a session_token are skipped (no owner to register under).
    """
    settings = get_settings()
    metadata_path = settings.upload.dir / "metadata.jsonl"
    if not metadata_path.exists():
        logger.info("No metadata.jsonl found, skipping upload registry reconstruction")
        return

    _upload_registry.clear()
    registered = 0

    for line in read_jsonl(metadata_path):
        token = line.get("session_token")
        upload_id = line.get("upload_id")
        if not token or not upload_id:
            continue

        store_root = settings.upload.dir / upload_id
        if not store_root.exists():
            continue

        tags = {"_upload_id": upload_id, "_session_token": token}
        store = DiskTrajectoryStore(root=store_root, default_tags=tags)
        store.initialize()
        _upload_registry.setdefault(token, []).append(store)
        registered += 1

    logger.info(
        "Reconstructed upload registry: %d uploads across %d tokens",
        registered,
        len(_upload_registry),
    )


def get_trajectory_store() -> BaseTrajectoryStore:
    """Return cached TrajectoryStore singleton.

    In self-use mode returns LocalStore. In demo mode this is unused
    (store_resolver uses get_upload_stores + get_example_store instead).
    """

    def _create_store() -> BaseTrajectoryStore:
        settings = get_settings()
        return (
            DiskTrajectoryStore(settings.upload.dir) if is_demo_mode() else LocalTrajectoryStore()
        )

    return _get_or_create("store", _create_store)


def get_example_store() -> DiskTrajectoryStore:
    """Return cached DiskStore for demo example sessions.

    Separate from the upload store so examples live in ``~/.vibelens/examples/``
    and uploads live in ``~/.vibelens/uploads/``.
    """

    def _create():
        return DiskTrajectoryStore(get_settings().storage.examples_dir)

    return _get_or_create("example_store", _create)
