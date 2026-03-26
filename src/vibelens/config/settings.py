"""Core settings model and loader."""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from vibelens.config.loader import apply_yaml_defaults, discover_config_path
from vibelens.models.enums import AppMode
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

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
    public_url: str = Field(
        default="",
        description="Public-facing base URL for shareable links (e.g. https://vibelens.chats-lab.org).",
    )

    # Data sources
    claude_dir: Path = Field(
        default=Path.home() / ".claude",
        description="Root directory containing Claude Code conversation history.",
    )
    codex_dir: Path = Field(
        default=Path.home() / ".codex",
        description="Root directory for Codex CLI session data.",
    )
    gemini_dir: Path = Field(
        default=Path.home() / ".gemini",
        description="Root directory for Gemini CLI session data.",
    )

    # Shares
    share_dir: Path = Field(
        default=Path.home() / ".vibelens" / "shares",
        description="Directory for shared session snapshots.",
    )

    # Managed skills
    managed_skills_dir: Path = Field(
        default=Path.home() / ".vibelens" / "skills",
        description="Central directory containing VibeLens-managed skills.",
    )

    # Agent-native skills
    skills_dir: Path = Field(
        default=Path.home() / ".claude" / "skills",
        description="Root directory containing installed Claude Code skills.",
    )

    # Friction persistence
    friction_dir: Path = Field(
        default=Path.home() / ".vibelens" / "friction",
        description="Directory for persisted friction analysis results.",
    )

    # Skill analysis persistence
    skill_analysis_dir: Path = Field(
        default=Path.home() / ".vibelens" / "skill_analyses",
        description="Directory for persisted skill analysis results.",
    )

    # Upload
    upload_dir: Path = Field(
        default=Path.home() / ".vibelens" / "uploads",
        description="Directory to store uploaded zip files.",
    )
    max_zip_bytes: int = Field(
        default=10 * 1024 * 1024 * 1024,
        description="Maximum zip file size (10 GB).",
    )
    max_extracted_bytes: int = Field(
        default=20 * 1024 * 1024 * 1024,
        description="Maximum total extracted size (20 GB).",
    )
    max_file_count: int = Field(
        default=10_000,
        description="Maximum files in a zip archive.",
    )
    stream_chunk_size: int = Field(
        default=64 * 1024,
        description="Chunk size in bytes for streaming uploads to disk.",
    )

    # LLM batching
    max_batch_tokens: int = Field(
        default=80_000,
        description=(
            "Maximum input token budget for session contexts in one LLM batch. "
            "Prompt overhead (system prompt, schema, template) is computed dynamically "
            "and subtracted automatically. Increase for models with larger context windows."
        ),
    )

    # Agent visibility
    visible_agents: list[str] = Field(
        default=["all"],
        description=(
            "Agent names to display in the session list. "
            'Use ["all"] to show every agent, or specify names like '
            '["claude-code", "codex"].'
        ),
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
        self.codex_dir = self.codex_dir.expanduser()
        self.gemini_dir = self.gemini_dir.expanduser()
        self.managed_skills_dir = self.managed_skills_dir.expanduser()
        self.skills_dir = self.skills_dir.expanduser()
        self.share_dir = self.share_dir.expanduser()
        self.friction_dir = self.friction_dir.expanduser()
        self.skill_analysis_dir = self.skill_analysis_dir.expanduser()
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
