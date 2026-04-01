"""Application configuration package.

Provides JSON/YAML configuration with environment variable overrides.
Priority (highest to lowest): env vars → .env file → settings file → defaults.
"""

from vibelens.config.llm_config import (
    DEFAULT_SETTINGS_PATH,
    LLMConfig,
    discover_settings_path,
    load_llm_config,
    mask_api_key,
    save_llm_config,
)
from vibelens.config.loader import discover_config_path
from vibelens.config.settings import Settings, load_settings

__all__ = [
    "DEFAULT_SETTINGS_PATH",
    "LLMConfig",
    "Settings",
    "discover_config_path",
    "discover_settings_path",
    "load_llm_config",
    "load_settings",
    "mask_api_key",
    "save_llm_config",
]
