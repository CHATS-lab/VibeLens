"""Dependency injection singletons for VibeLens."""

from pathlib import Path

from vibelens.config import Settings, load_settings
from vibelens.models.enums import AppMode
from vibelens.stores.base import TrajectoryStore
from vibelens.stores.disk import DiskStore
from vibelens.stores.local import LocalStore

_settings: Settings | None = None
_store: TrajectoryStore | None = None

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


def get_store() -> TrajectoryStore:
    """Return cached TrajectoryStore singleton.

    In demo mode returns DiskStore; in self mode returns LocalStore.
    """
    global _store
    if _store is None:
        if is_demo_mode():
            _store = DiskStore(DATASETS_ROOT)
        else:
            _store = LocalStore(get_settings().claude_dir)
    return _store
