"""Core settings model and loader."""

import logging
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from vibelens.config.loader import apply_yaml_defaults, discover_config_path

logger = logging.getLogger(__name__)

ENV_PREFIX = "VIBELENS_"


class Settings(BaseSettings):
    """VibeLens configuration loaded from environment / .env / YAML config.

    Fields are grouped by subsystem. Each field maps to an environment
    variable with the ``VIBELENS_`` prefix (e.g. ``VIBELENS_HOST``).
    """

    model_config = {"env_prefix": ENV_PREFIX}

    # Server
    host: str = Field(
        default="127.0.0.1",
        description="Network interface to bind the HTTP server to.",
    )
    port: int = Field(
        default=12001,
        description="TCP port for the HTTP server.",
    )

    # Data sources
    claude_dir: Path = Field(
        default=Path.home() / ".claude",
        description="Root directory containing Claude Code conversation history.",
    )

    # Database
    db_path: Path = Field(
        default=Path.home() / ".vibelens" / "vibelens.db",
        description="File path for the local SQLite database.",
    )

    # MongoDB
    mongodb_uri: str = Field(
        default="",
        description="MongoDB connection URI. Leave empty to disable MongoDB integration.",
    )
    mongodb_db: str = Field(
        default="vibelens",
        description="MongoDB database name for session and message storage.",
    )

    # HuggingFace
    hf_token: str = Field(
        default="",
        description="HuggingFace API token for pulling dataclaw datasets.",
    )

    @model_validator(mode="after")
    def expand_paths(self) -> "Settings":
        """Expand ~ in Path fields so YAML values like ~/.claude work."""
        self.claude_dir = self.claude_dir.expanduser()
        self.db_path = self.db_path.expanduser()
        return self


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from YAML config, environment, and .env file.

    Priority (highest to lowest):
        1. Environment variables (``VIBELENS_*``)
        2. ``.env`` file values
        3. YAML config file values
        4. Field defaults

    Args:
        config_path: Explicit path to a YAML config file.  When ``None``,
            auto-discovers ``vibelens.yaml`` / ``vibelens.yml`` in the
            current directory, or reads ``VIBELENS_CONFIG`` env var.

    Returns:
        Populated Settings instance.
    """
    resolved_path = config_path or discover_config_path()
    if resolved_path:
        apply_yaml_defaults(resolved_path)
        logger.info("Loaded config from %s", resolved_path)

    return Settings(_env_file=".env", _env_file_encoding="utf-8")
