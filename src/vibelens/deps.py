"""Dependency injection singletons for VibeLens."""

from pathlib import Path

from vibelens.config import Settings, load_settings
from vibelens.llm.backend import InferenceBackend
from vibelens.models.enums import AppMode
from vibelens.storage.base import TrajectoryStore
from vibelens.storage.disk import DiskStore
from vibelens.storage.local import LocalStore

_settings: Settings | None = None
_store: TrajectoryStore | None = None
_share_service = None
_friction_store = None
_skill_store = None
_inference_backend: InferenceBackend | None = None
_inference_checked = False

DATASETS_ROOT = Path("datasets")


def get_settings() -> Settings:
    """Return cached application settings."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def is_demo_mode() -> bool:
    """Check whether the application is running in demo mode."""
    return get_settings().app_mode == AppMode.DEMO


def is_test_mode() -> bool:
    """Check whether the application is running in test mode."""
    return get_settings().app_mode == AppMode.TEST


def get_share_service():
    """Return cached ShareService singleton."""
    from vibelens.services.share_service import ShareService

    global _share_service
    if _share_service is None:
        _share_service = ShareService(get_settings().share_dir)
    return _share_service


def get_friction_store():
    """Return cached FrictionStore singleton."""
    from vibelens.services.friction_store import FrictionStore

    global _friction_store
    if _friction_store is None:
        _friction_store = FrictionStore(get_settings().friction_dir)
    return _friction_store


def get_skill_store():
    """Return cached ClaudeCodeSkillStore singleton."""
    from vibelens.storage.skill.claude_code import ClaudeCodeSkillStore

    global _skill_store
    if _skill_store is None:
        _skill_store = ClaudeCodeSkillStore(get_settings().skills_dir)
    return _skill_store


def get_inference_backend() -> InferenceBackend | None:
    """Return cached InferenceBackend, or None if disabled."""
    global _inference_backend, _inference_checked
    if _inference_checked:
        return _inference_backend
    _inference_checked = True
    from vibelens.llm.backends import create_backend

    _inference_backend = create_backend(get_settings())
    return _inference_backend


def set_inference_backend(backend: InferenceBackend | None) -> None:
    """Replace the inference backend singleton at runtime."""
    global _inference_backend, _inference_checked
    _inference_backend = backend
    _inference_checked = True


def get_store() -> TrajectoryStore:
    """Return cached TrajectoryStore singleton.

    In demo mode returns DiskStore; in self mode returns LocalStore.
    """
    global _store
    if _store is None:
        _store = DiskStore(DATASETS_ROOT) if is_demo_mode() else LocalStore(settings=get_settings())
    return _store
