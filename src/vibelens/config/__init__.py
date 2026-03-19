"""Application configuration package.

Provides YAML-first configuration with environment variable overrides.
Priority (highest to lowest): env vars → .env file → YAML config → defaults.
"""

from vibelens.config.loader import discover_config_path
from vibelens.config.settings import Settings, load_settings

__all__ = [
    "Settings",
    "discover_config_path",
    "load_settings",
]
