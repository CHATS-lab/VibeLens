"""Dependency injection singletons for VibeLens."""

from collections.abc import Callable
from typing import Any

from vibelens.config import (
    LLMConfig,
    Settings,
    load_llm_config,
    load_settings,
    save_llm_config,
)
from vibelens.config.llm_config import DEFAULT_SETTINGS_PATH, discover_settings_path
from vibelens.llm.backend import InferenceBackend
from vibelens.models.enums import AppMode
from vibelens.storage.trajectory.base import BaseTrajectoryStore
from vibelens.storage.trajectory.disk import DiskTrajectoryStore
from vibelens.storage.trajectory.local import LocalTrajectoryStore
from vibelens.utils.json import read_jsonl
from vibelens.utils.log import get_logger

_MISSING = object()
_NOT_CHECKED = object()
_registry: dict[str, Any] = {}
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


def is_demo_mode() -> bool:
    """Check whether the application is running in demo mode."""
    return get_settings().app_mode == AppMode.DEMO


def is_test_mode() -> bool:
    """Check whether the application is running in test mode."""
    return get_settings().app_mode == AppMode.TEST


def get_share_service():
    """Return cached ShareService singleton."""
    from vibelens.services.session.share import ShareService

    return _get_or_create("share_service", lambda: ShareService(get_settings().share_dir))


def get_friction_store():
    """Return cached FrictionStore singleton."""
    from vibelens.services.friction.store import FrictionStore

    return _get_or_create("friction_store", lambda: FrictionStore(get_settings().friction_dir))


def get_claude_skill_store():
    """Return cached Claude Code skill store singleton."""
    from vibelens.models.skill import SkillSourceType
    from vibelens.storage.skill.disk import DiskSkillStore

    return _get_or_create(
        "skill_store",
        lambda: DiskSkillStore(get_settings().skills_dir, SkillSourceType.CLAUDE_CODE),
    )


def get_codex_skill_store():
    """Return cached Codex CLI skill store singleton."""
    from vibelens.models.skill import SkillSourceType
    from vibelens.storage.skill.disk import DiskSkillStore

    return _get_or_create(
        "codex_skill_store",
        lambda: DiskSkillStore(
            get_settings().codex_dir / "skills", SkillSourceType.CODEX
        ),
    )


def get_central_skill_store():
    """Return cached central managed skill repository."""
    from vibelens.storage.skill.central import CentralSkillStore

    return _get_or_create(
        "central_skill_store", lambda: CentralSkillStore(get_settings().managed_skills_dir)
    )


def get_agent_skill_stores() -> list:
    """Return cached list of third-party agent skill stores.

    Only includes agents whose skills directories exist on disk.
    """
    from vibelens.storage.skill.agent import create_agent_skill_stores

    return _get_or_create("agent_skill_stores", create_agent_skill_stores)


def get_skill_analysis_store():
    """Return cached SkillAnalysisStore singleton."""
    from vibelens.services.skill.store import SkillAnalysisStore

    return _get_or_create(
        "skill_analysis_store", lambda: SkillAnalysisStore(get_settings().skill_analysis_dir)
    )


def get_llm_config() -> LLMConfig:
    """Return cached LLM configuration, lazy-loading from YAML/env."""
    return _get_or_create("llm_config", load_llm_config)


def set_llm_config(config: LLMConfig) -> None:
    """Update LLM config singleton, persist to settings.json, and recreate backend."""
    _registry["llm_config"] = config

    config_path = discover_settings_path() or DEFAULT_SETTINGS_PATH
    save_llm_config(config, config_path)

    from vibelens.llm.backends import create_backend_from_llm_config

    backend = create_backend_from_llm_config(config)
    set_inference_backend(backend)


def get_inference_backend() -> InferenceBackend | None:
    """Return cached InferenceBackend, or None if disabled."""
    value = _registry.get("inference_backend", _NOT_CHECKED)
    if value is not _NOT_CHECKED:
        return value

    from vibelens.llm.backends import create_backend_from_llm_config

    backend = create_backend_from_llm_config(get_llm_config())
    _registry["inference_backend"] = backend
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
    metadata_path = settings.upload_dir / "metadata.jsonl"
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

        store_root = settings.upload_dir / upload_id
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
            DiskTrajectoryStore(settings.upload_dir)
            if is_demo_mode()
            else LocalTrajectoryStore(settings=settings)
        )

    return _get_or_create("store", _create_store)


def get_example_store() -> DiskTrajectoryStore:
    """Return cached DiskStore for demo example sessions.

    Separate from the upload store so examples live in ``~/.vibelens/examples/``
    and uploads live in ``~/.vibelens/uploads/``.
    """
    return _get_or_create("example_store", lambda: DiskTrajectoryStore(get_settings().examples_dir))
