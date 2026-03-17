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

    # Database
    db_path: Path = Field(
        default=Path.home() / ".vibelens" / "vibelens.db",
        description="File path for the local SQLite database.",
    )

    # Upload
    upload_dir: Path = Field(
        default=Path.home() / ".vibelens" / "uploads",
        description="Directory to store uploaded zip files.",
    )
    upload_allowed_extensions: str = Field(
        default=".json,.jsonl",
        description="Comma-separated allowed file extensions for single-file upload.",
    )
    max_file_size_bytes: int = Field(
        default=50 * 1024 * 1024,
        description="Maximum single file upload size (50 MB).",
    )
    max_zip_bytes: int = Field(
        default=200 * 1024 * 1024,
        description="Maximum zip file size (200 MB).",
    )
    max_extracted_bytes: int = Field(
        default=500 * 1024 * 1024,
        description="Maximum total extracted size (500 MB).",
    )
    max_file_count: int = Field(
        default=10_000,
        description="Maximum files in a zip archive.",
    )
    subagent_file_prefix: str = Field(
        default="agent-",
        description="Filename prefix identifying sub-agent session files.",
    )
    min_confidence: float = Field(
        default=0.5,
        description="Minimum fingerprint confidence to accept a format match.",
    )
    stream_chunk_size: int = Field(
        default=64 * 1024,
        description="Chunk size in bytes for streaming uploads to disk.",
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

    # Demo mode
    demo_storage: str = Field(
        default="memory",
        description="Storage backend for demo mode: 'memory' or 'sqlite'.",
    )
    demo_example_sessions: str = Field(
        default="",
        description="Comma-separated file paths to pre-load as example sessions.",
    )
    demo_session_ttl: int = Field(
        default=3600,
        description="Seconds before orphaned demo uploads are cleaned up.",
    )
    demo_persist_uploads: bool = Field(
        default=False,
        description="Save raw uploaded files to disk in demo mode.",
    )

    @property
    def example_session_paths(self) -> list[Path]:
        """Parse comma-separated example session paths into a list."""
        if not self.demo_example_sessions:
            return []
        return [
            Path(p.strip()).expanduser()
            for p in self.demo_example_sessions.split(",")
            if p.strip()
        ]

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
