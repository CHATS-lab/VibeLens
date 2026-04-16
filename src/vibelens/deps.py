"""Dependency injection singletons for VibeLens."""

from collections.abc import Callable
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
from vibelens.models.enums import AppMode
from vibelens.storage.trajectory.base import BaseTrajectoryStore
from vibelens.storage.trajectory.disk import DiskTrajectoryStore
from vibelens.storage.trajectory.local import LocalTrajectoryStore
from vibelens.utils.json import read_jsonl
from vibelens.utils.log import get_logger

# Internal singleton registry and upload store registry
_MISSING = object()
# Lazy-loaded singletons
_NOT_CHECKED = object()
# General singletons like stores and services
_registry: dict[str, Any] = {}
# Mapping of session_token to list of upload DiskStores for that user
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
    from vibelens.services.session.share import ShareService

    return _get_or_create("share_service", lambda: ShareService(get_settings().storage.share_dir))


def get_friction_store():
    """Return cached FrictionStore singleton."""
    from vibelens.services.friction.store import FrictionStore

    settings = get_settings()
    return _get_or_create("friction_store", lambda: FrictionStore(settings.storage.friction_dir))


def get_skill_service():
    """Return cached SkillService singleton."""

    def _create():
        from vibelens.services.extensions.skill_service import SkillService
        from vibelens.storage.extension.skill_store import SkillStore

        settings = get_settings()
        central = SkillStore(settings.storage.managed_skills_dir, create=True)
        agent_skill_stores = _build_agent_skill_stores()
        return SkillService(central=central, agents=agent_skill_stores)

    return _get_or_create("skill_service", _create)


def _build_agent_skill_stores() -> dict:
    """Build agent SkillStore instances from platform registry."""
    from vibelens.models.enums import AgentType
    from vibelens.services.extensions.platforms import PLATFORMS
    from vibelens.storage.extension.skill_store import SkillStore

    stores: dict[AgentType, SkillStore] = {}
    for source, platform in PLATFORMS.items():
        resolved = platform.skills_dir.expanduser().resolve()
        if resolved.is_dir():
            stores[AgentType[source.name]] = SkillStore(resolved)
    return stores


def get_command_service():
    """Return cached CommandService singleton."""

    def _create():
        from vibelens.services.extensions.command_service import CommandService
        from vibelens.storage.extension.command_store import CommandStore

        settings = get_settings()
        central = CommandStore(settings.storage.managed_commands_dir, create=True)
        agent_command_stores = _build_agent_command_stores()
        return CommandService(central=central, agents=agent_command_stores)

    return _get_or_create("command_service", _create)


def _build_agent_command_stores() -> dict:
    """Build agent CommandStore instances from platform registry."""
    from vibelens.models.enums import AgentType
    from vibelens.services.extensions.platforms import PLATFORMS
    from vibelens.storage.extension.command_store import CommandStore

    stores: dict[AgentType, CommandStore] = {}
    for source, platform in PLATFORMS.items():
        if platform.commands_dir is None:
            continue
        resolved = platform.commands_dir.expanduser().resolve()
        if resolved.is_dir():
            stores[AgentType[source.name]] = CommandStore(resolved)
    return stores


def get_subagent_service():
    """Return cached SubagentService singleton."""

    def _create():
        from vibelens.services.extensions.subagent_service import SubagentService
        from vibelens.storage.extension.subagent_store import SubagentStore

        settings = get_settings()
        central = SubagentStore(settings.storage.managed_subagents_dir, create=True)
        agent_subagent_stores = _build_agent_subagent_stores()
        return SubagentService(central=central, agents=agent_subagent_stores)

    return _get_or_create("subagent_service", _create)


def _build_agent_subagent_stores() -> dict:
    """Build agent SubagentStore instances from platform registry.

    Subagents live in their own directory (``platform.subagents_dir``), not
    shared with commands.
    """
    from vibelens.models.enums import AgentType
    from vibelens.services.extensions.platforms import PLATFORMS
    from vibelens.storage.extension.subagent_store import SubagentStore

    stores: dict[AgentType, SubagentStore] = {}
    for source, platform in PLATFORMS.items():
        if platform.subagents_dir is None:
            continue
        resolved = platform.subagents_dir.expanduser().resolve()
        if resolved.is_dir():
            stores[AgentType[source.name]] = SubagentStore(resolved)
    return stores


def get_hook_service():
    """Return cached HookService singleton."""

    def _create():
        from vibelens.services.extensions.hook_service import HookService
        from vibelens.storage.extension.hook_store import HookStore

        settings = get_settings()
        central = HookStore(settings.storage.managed_hooks_dir, create=True)
        agent_settings = _build_agent_settings_paths()
        return HookService(central=central, agent_settings=agent_settings)

    return _get_or_create("hook_service", _create)


def _build_agent_settings_paths() -> dict:
    """Build mapping of AgentType to each platform's settings.json path.

    Only platforms with a non-None ``settings_path`` (CLAUDE, CODEX) are included.
    The file does not need to exist yet — it will be created on first sync.
    """
    from vibelens.models.enums import AgentType
    from vibelens.services.extensions.platforms import PLATFORMS

    paths: dict[AgentType, Path] = {}
    for source, platform in PLATFORMS.items():
        if platform.settings_path is None:
            continue
        resolved = platform.settings_path.expanduser().resolve()
        paths[AgentType[source.name]] = resolved
    return paths


def get_personalization_store():
    """Return cached PersonalizationStore singleton."""
    from vibelens.services.personalization.store import PersonalizationStore

    settings = get_settings()
    return _get_or_create(
        "personalization_store",
        lambda: PersonalizationStore(settings.storage.personalization_dir),
    )


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
    settings = get_settings()
    return _get_or_create(
        "example_store", lambda: DiskTrajectoryStore(settings.storage.examples_dir)
    )
