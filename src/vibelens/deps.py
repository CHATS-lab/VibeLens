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
from vibelens.config.llm_config import DEFAULT_LLM_CONFIG_PATH, discover_llm_config_path
from vibelens.llm.backend import InferenceBackend
from vibelens.models.enums import AppMode
from vibelens.storage.conversation.base import TrajectoryStore
from vibelens.storage.conversation.disk import DiskStore
from vibelens.storage.conversation.local import LocalStore

_MISSING = object()
_NOT_CHECKED = object()
_registry: dict[str, Any] = {}


def _get_or_create(key: str, factory: Callable[[], Any]) -> Any:
    """Return a cached singleton, creating it on first access."""
    value = _registry.get(key, _MISSING)
    if value is _MISSING:
        value = factory()
        _registry[key] = value
    return value


def reset_singletons() -> None:
    """Clear all cached singletons for test isolation."""
    _registry.clear()


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


def get_skill_store():
    """Return cached Claude Code skill store singleton."""
    from vibelens.models.skill import SkillSourceType
    from vibelens.storage.skill.disk import DiskSkillStore

    return _get_or_create(
        "skill_store",
        lambda: DiskSkillStore(get_settings().skills_dir, SkillSourceType.CLAUDE_CODE),
    )


def get_codex_skill_store():
    """Return cached CodexSkillStore singleton."""
    from vibelens.storage.skill.codex import CodexSkillStore

    return _get_or_create(
        "codex_skill_store", lambda: CodexSkillStore(get_settings().codex_dir / "skills")
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
    """Update LLM config singleton, persist to YAML, and recreate backend."""
    _registry["llm_config"] = config

    config_path = discover_llm_config_path() or DEFAULT_LLM_CONFIG_PATH
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


def get_store() -> TrajectoryStore:
    """Return cached TrajectoryStore singleton.

    In demo mode returns DiskStore(upload_dir); in self mode returns LocalStore.
    """

    def _create_store() -> TrajectoryStore:
        settings = get_settings()
        return DiskStore(settings.upload_dir) if is_demo_mode() else LocalStore(settings=settings)

    return _get_or_create("store", _create_store)


def get_example_store() -> DiskStore:
    """Return cached DiskStore for demo example sessions.

    Separate from the upload store so examples live in ``~/.vibelens/examples/``
    and uploads live in ``~/.vibelens/uploads/``.
    """
    return _get_or_create("example_store", lambda: DiskStore(get_settings().examples_dir))
