"""YAML config file loading and auto-discovery."""

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

ENV_PREFIX = "VIBELENS_"
CONFIG_ENV_VAR = "VIBELENS_CONFIG"

DEFAULT_CONFIG_NAMES = ["vibelens.yaml", "vibelens.yml"]

# Maps nested YAML sections/keys → flat Settings field names.
# Supports readable YAML structure while keeping a flat pydantic model.
YAML_FIELD_MAP: dict[str, dict[str, str]] = {
    "server": {
        "host": "host",
        "port": "port",
    },
    "sources": {
        "claude_dir": "claude_dir",
    },
    "upload": {
        "dir": "upload_dir",
        "max_zip_bytes": "max_zip_bytes",
        "max_extracted_bytes": "max_extracted_bytes",
        "max_file_count": "max_file_count",
        "stream_chunk_size": "stream_chunk_size",
    },
    "app": {
        "mode": "app_mode",
    },
    "demo": {
        "example_sessions": "demo_example_sessions",
    },
}


def discover_config_path() -> Path | None:
    """Auto-discover a YAML config file.

    Checks (in order):
        1. ``VIBELENS_CONFIG`` environment variable
        2. ``vibelens.yaml`` or ``vibelens.yml`` in the current directory

    Returns:
        Path to the config file, or None if not found.
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

    return None


def apply_yaml_defaults(config_path: Path) -> None:
    """Load a YAML config file and set env vars for unset fields.

    Values from the YAML file only apply when the corresponding
    ``VIBELENS_*`` environment variable is not already set, giving
    env vars the highest priority.

    Args:
        config_path: Path to the YAML configuration file.
    """
    flat_values = load_yaml_flat(config_path)
    for field_name, value in flat_values.items():
        env_key = f"{ENV_PREFIX}{field_name.upper()}"
        if env_key not in os.environ:
            os.environ[env_key] = str(value)


def load_yaml_flat(config_path: Path) -> dict[str, str]:
    """Load a YAML config file and flatten it to Settings field names.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Dictionary mapping Settings field names to string values.
    """
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}

    result: dict[str, str] = {}
    for section, field_map in YAML_FIELD_MAP.items():
        section_data = raw.get(section)
        if not isinstance(section_data, dict):
            continue
        for yaml_key, settings_field in field_map.items():
            if yaml_key in section_data and section_data[yaml_key] is not None:
                result[settings_field] = str(section_data[yaml_key])

    return result
