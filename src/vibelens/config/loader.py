"""YAML config file auto-discovery."""

import os
from importlib.resources import files
from pathlib import Path

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CONFIG_ENV_VAR = "VIBELENS_CONFIG"
DEFAULT_CONFIG_NAMES = ["vibelens.yaml", "vibelens.yml"]
REPO_FALLBACK_CONFIG_NAME = "config/self-use.yaml"
BUNDLED_DEFAULT_CONFIG = "default.yaml"


def discover_config_path() -> Path | None:
    """Auto-discover a YAML config file.

    Checks (in order):
        1. ``VIBELENS_CONFIG`` environment variable
        2. ``vibelens.yaml`` or ``vibelens.yml`` in the current directory
        3. ``config/self-use.yaml`` in the current directory (for repo dev)
        4. ``vibelens/data/config/default.yaml`` shipped in the package

    Returns:
        Path to the config file, or None if nothing is discoverable.
    """
    env_value = os.environ.get(CONFIG_ENV_VAR)
    if env_value:
        path = Path(env_value)
        if path.exists():
            return path
        logger.warning("%s points to missing file: %s", CONFIG_ENV_VAR, path)
        return None

    for name in DEFAULT_CONFIG_NAMES:
        path = Path(name)
        if path.exists():
            return path

    repo_fallback = Path(REPO_FALLBACK_CONFIG_NAME)
    if repo_fallback.exists():
        return repo_fallback

    return _bundled_default_config()


def _bundled_default_config() -> Path | None:
    """Return the bundled ``default.yaml`` shipped with the package."""
    try:
        resource = files("vibelens.data.config").joinpath(BUNDLED_DEFAULT_CONFIG)
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    path = Path(str(resource))
    return path if path.exists() else None


def bundled_examples_dir() -> Path | None:
    """Return the bundled example sessions directory, if available."""
    try:
        resource = files("vibelens.data.examples").joinpath("recipe-book")
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    path = Path(str(resource))
    return path if path.exists() else None
