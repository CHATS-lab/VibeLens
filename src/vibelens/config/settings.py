"""Core settings model and loader."""

import logging
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from vibelens.config.loader import apply_yaml_defaults, discover_config_path
from vibelens.models.enums import AppMode

logger = logging.getLogger(__name__)

ENV_PREFIX = "VIBELENS_"


class Settings(BaseSettings):
    """VibeLens configuration loaded from environment / .env / YAML config.

    Fields are grouped by subsystem. Each field maps to an environment
    variable with the ``VIBELENS_`` prefix (e.g. ``VIBELENS_HOST``).
    """

    model_config = {"env_prefix": ENV_PREFIX}

    # Application mode
    app_mode: AppMode = Field(
        default=AppMode.SELF,
        description="Operating mode: 'self' for local use, 'demo' for public-facing.",
    )

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

    # Upload
    upload_dir: Path = Field(
        default=Path.home() / ".vibelens" / "uploads",
        description="Directory to store uploaded zip files.",
    )
    max_zip_bytes: int = Field(
        default=500 * 1024 * 1024,
        description="Maximum zip file size (500 MB).",
    )
    max_extracted_bytes: int = Field(
        default=1024 * 1024 * 1024,
        description="Maximum total extracted size (1 GB).",
    )
    max_file_count: int = Field(
        default=10_000,
        description="Maximum files in a zip archive.",
    )
    stream_chunk_size: int = Field(
        default=64 * 1024,
        description="Chunk size in bytes for streaming uploads to disk.",
    )

    # Demo mode
    demo_example_sessions: str = Field(
        default="",
        description="Comma-separated file paths to pre-load as example sessions.",
    )

    @property
    def example_session_paths(self) -> list[Path]:
        """Parse comma-separated example session paths into a list."""
        if not self.demo_example_sessions:
            return []
        return [
            Path(p.strip()).expanduser() for p in self.demo_example_sessions.split(",") if p.strip()
        ]

    @model_validator(mode="after")
    def expand_paths(self) -> "Settings":
        """Expand ~ in Path fields so YAML values like ~/.claude work."""
        self.claude_dir = self.claude_dir.expanduser()
        self.upload_dir = self.upload_dir.expanduser()
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
