"""Core settings model and loader."""

import hashlib
import json
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from vibelens.config.loader import discover_config_path
from vibelens.models.enums import AppMode
from vibelens.models.llm.inference import _BACKEND_LEGACY_ALIASES, BackendType
from vibelens.utils.log import DOMAIN_PREFIXES, get_logger

logger = get_logger(__name__)

ENV_PREFIX = "VIBELENS_"
SETTINGS_JSON_PATH = Path.home() / ".vibelens" / "settings.json"

LogLevelName = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _vibelens_home(*parts: str) -> Path:
    """``~/.vibelens/<parts>`` resolved at call time, not import time."""
    return Path.home() / ".vibelens" / Path(*parts) if parts else Path.home() / ".vibelens"


def _default_log_dir() -> Path:
    """Default log dir: ~/.vibelens/logs."""
    return _vibelens_home("logs")


class ServerConfig(BaseModel):
    """HTTP server binding."""

    host: str = Field(default="127.0.0.1", description="Network interface to bind.")
    port: int = Field(default=12001, description="TCP port for the HTTP server.")
    public_url: str = Field(default="", description="Public-facing base URL for shareable links.")


class DemoConfig(BaseModel):
    """Demo mode example loading."""

    example_sessions: str = Field(
        default="", description="Comma-separated file paths to pre-load as example sessions."
    )

    @property
    def session_paths(self) -> list[Path]:
        """Parse comma-separated example session paths into a list.

        When ``example_sessions`` is empty, falls back to the bundled
        ``vibelens/data/examples/recipe-book`` directory shipped with the
        package so pip/uv users get sample sessions out of the box.
        """
        if not self.example_sessions:
            from vibelens.config.loader import bundled_examples_dir

            bundled = bundled_examples_dir()
            return [bundled] if bundled is not None else []
        return [Path(p.strip()).expanduser() for p in self.example_sessions.split(",") if p.strip()]


class StorageConfig(BaseModel):
    """Persistent storage directories."""

    share_dir: Path = Field(
        default_factory=lambda: _vibelens_home("shares"),
        description="Directory for shared session snapshots.",
    )
    managed_skills_dir: Path = Field(
        default_factory=lambda: _vibelens_home("extensions", "skills"),
        description="Central directory containing VibeLens-managed skills.",
    )
    managed_commands_dir: Path = Field(
        default_factory=lambda: _vibelens_home("extensions", "commands"),
        description="Central directory for VibeLens-managed commands.",
    )
    managed_subagents_dir: Path = Field(
        default_factory=lambda: _vibelens_home("extensions", "subagents"),
        description="Central directory for VibeLens-managed subagents.",
    )
    managed_hooks_dir: Path = Field(
        default_factory=lambda: _vibelens_home("extensions", "hooks"),
        description="Central directory for VibeLens-managed hooks.",
    )
    managed_plugins_dir: Path = Field(
        default_factory=lambda: _vibelens_home("extensions", "plugins"),
        description="Central directory for VibeLens-managed plugins.",
    )
    managed_collections_dir: Path = Field(
        default_factory=lambda: _vibelens_home("extensions", "collections"),
        description="Central directory for VibeLens-managed extension collections.",
    )
    friction_dir: Path = Field(
        default_factory=lambda: _vibelens_home("friction"),
        description="Directory for persisted friction analysis results.",
    )
    personalization_dir: Path = Field(
        default_factory=lambda: _vibelens_home("personalization"),
        description=(
            "Root directory for persisted personalization results. Each mode "
            "(creation, evolution, recommendation) keeps its own store under "
            "a subdirectory of this path."
        ),
    )
    examples_dir: Path = Field(
        default_factory=lambda: _vibelens_home("examples"),
        description="Directory for storing parsed demo example trajectories.",
    )


class UploadConfig(BaseModel):
    """Upload processing limits."""

    dir: Path = Field(
        default_factory=lambda: _vibelens_home("uploads"),
        description="Directory to store uploaded zip files.",
    )
    max_zip_bytes: int = Field(
        default=10 * 1024 * 1024 * 1024, description="Maximum zip file size (10 GB)."
    )
    max_extracted_bytes: int = Field(
        default=20 * 1024 * 1024 * 1024, description="Maximum total extracted size (20 GB)."
    )
    max_file_count: int = Field(default=10000, description="Maximum files in a zip archive.")
    stream_chunk_size: int = Field(
        default=64 * 1024, description="Chunk size in bytes for streaming uploads to disk."
    )


class DonationConfig(BaseModel):
    """Donation server settings."""

    url: str = Field(
        default="https://vibelens.chats-lab.org",
        description="URL of the donation server to send donated sessions to.",
    )
    dir: Path = Field(
        default_factory=lambda: _vibelens_home("donations"),
        description="Directory for storing received donation ZIP files and index.",
    )


class InferenceConfig(BaseModel):
    """LLM inference backend configuration. Mutable at runtime."""

    backend: BackendType = Field(default=BackendType.DISABLED, description="Inference Backend")
    api_key: str = Field(default="", description="API key for the LLM provider.")
    base_url: str | None = Field(
        default=None, description="Custom base URL. Auto-resolved from PROVIDER_BASE_URLS if None."
    )
    model: str = Field(default="anthropic/claude-haiku-4-5", description="Model in litellm format.")
    timeout: int = Field(default=300, description="Inference timeout in seconds.")
    max_input_tokens: int = Field(default=80000, description="Max input tokens per request.")
    max_output_tokens: int = Field(default=10000, description="Max output tokens per request.")
    max_sessions: int = Field(default=30, description="Maximum sessions per analysis request.")
    temperature: float = Field(default=1.0, description="Sampling temperature.")
    thinking: bool = Field(
        default=False,
        description="Enable extended thinking / reasoning mode for supported backends.",
    )

    @field_validator("backend", mode="before")
    @classmethod
    def normalize_legacy_backend(cls, value: str) -> str:
        """Map legacy backend strings to current BackendType values."""
        if isinstance(value, str):
            if value.startswith("BackendType."):
                member_name = value.removeprefix("BackendType.")
                try:
                    return BackendType[member_name].value
                except KeyError:
                    pass
            return _BACKEND_LEGACY_ALIASES.get(value, value)
        return value


class LoggingConfig(BaseModel):
    """Log system configuration."""

    level: LogLevelName = Field(default="INFO", description="Global log level.")
    dir: Path = Field(
        default_factory=_default_log_dir,
        description="Directory for log files. Defaults to ~/.vibelens/logs.",
    )
    max_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Rotate each log file after reaching this size in bytes.",
    )
    backup_count: int = Field(
        default=3,
        description="Number of rotated backups to retain per log file.",
    )
    per_domain: dict[str, LogLevelName] = Field(
        default_factory=dict,
        description="Override global level for a specific domain (e.g. analysis: DEBUG).",
    )

    @field_validator("per_domain")
    @classmethod
    def _validate_domain_keys(cls, value: dict[str, str]) -> dict[str, str]:
        """Reject unknown domain names so typos fail at config load."""
        unknown = set(value) - set(DOMAIN_PREFIXES)
        if unknown:
            valid = ", ".join(sorted(DOMAIN_PREFIXES))
            raise ValueError(f"Unknown log domain(s): {sorted(unknown)}. Valid: {valid}.")
        return value


class Settings(BaseSettings):
    """VibeLens configuration loaded from environment / .env / YAML config.

    Sub-models group related fields. Each field maps to a nested
    environment variable with ``__`` delimiter (e.g. ``VIBELENS_SERVER__HOST``).
    """

    model_config = {"env_prefix": ENV_PREFIX, "env_nested_delimiter": "__"}
    _yaml_file: ClassVar[Path | None] = None

    mode: AppMode = Field(
        default=AppMode.SELF,
        description="Operating mode: 'self' for local use, 'demo' for public-facing.",
    )
    server: ServerConfig = Field(default_factory=ServerConfig, description="HTTP server binding.")
    demo: DemoConfig = Field(default_factory=DemoConfig, description="Demo mode settings.")
    storage: StorageConfig = Field(
        default_factory=StorageConfig, description="Storage directories."
    )
    upload: UploadConfig = Field(default_factory=UploadConfig, description="Upload limits.")
    donation: DonationConfig = Field(default_factory=DonationConfig, description="Donation server.")
    inference: InferenceConfig = Field(
        default_factory=InferenceConfig, description="LLM inference backend."
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig, description="Log system configuration."
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Insert YAML and JSON settings sources into the priority chain.

        Priority (highest to lowest):
            init > env > .env > YAML > settings.json > file_secret > defaults
        """
        from pydantic_settings import YamlConfigSettingsSource

        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        if cls._yaml_file and cls._yaml_file.exists():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=cls._yaml_file))
        sources.append(_JsonInferenceSource(settings_cls))
        sources.append(file_secret_settings)
        return tuple(sources)

    @model_validator(mode="after")
    def expand_paths(self) -> "Settings":
        """Expand ~ in Path fields and resolve the examples cache dir."""
        self.storage.share_dir = self.storage.share_dir.expanduser()
        self.storage.managed_skills_dir = self.storage.managed_skills_dir.expanduser()
        self.storage.managed_commands_dir = self.storage.managed_commands_dir.expanduser()
        self.storage.managed_subagents_dir = self.storage.managed_subagents_dir.expanduser()
        self.storage.managed_hooks_dir = self.storage.managed_hooks_dir.expanduser()
        self.storage.managed_plugins_dir = self.storage.managed_plugins_dir.expanduser()
        self.storage.friction_dir = self.storage.friction_dir.expanduser()
        self.storage.personalization_dir = self.storage.personalization_dir.expanduser()
        self.storage.examples_dir = self._resolve_examples_dir()
        self.upload.dir = self.upload.dir.expanduser()
        self.donation.dir = self.donation.dir.expanduser()
        self.logging.dir = self.logging.dir.expanduser()
        return self

    def _resolve_examples_dir(self) -> Path:
        """Derive examples cache dir from configured example paths.

        Different configs get separate cache directories so switching
        configs doesn't serve stale data.
        """
        base = self.storage.examples_dir.expanduser()
        if not self.demo.example_sessions:
            return base
        digest = hashlib.md5(self.demo.example_sessions.encode()).hexdigest()[:8]
        return base / digest


class _JsonInferenceSource(PydanticBaseSettingsSource):
    """Read the ``inference`` key from ``~/.vibelens/settings.json``."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """Return nothing — we populate via __call__ instead."""
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """Load inference config from settings.json if it exists."""
        if not SETTINGS_JSON_PATH.exists():
            return {}
        try:
            raw = json.loads(SETTINGS_JSON_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(raw, dict):
            return {}
        # Support both new "inference" key and legacy "llm" key
        section = raw.get("inference") or raw.get("llm")
        if not isinstance(section, dict):
            return {}
        return {"inference": {k: v for k, v in section.items() if v is not None}}


def save_inference_config(config: InferenceConfig) -> None:
    """Persist inference config to ``~/.vibelens/settings.json``.

    Reads existing file to preserve non-inference keys, then writes
    the ``"inference"`` section with the current configuration.

    Args:
        config: Current inference configuration to persist.
    """
    existing: dict = {}
    if SETTINGS_JSON_PATH.exists():
        try:
            existing = json.loads(SETTINGS_JSON_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Only persist fields that differ from InferenceConfig defaults,
    # so users pick up new defaults automatically on upgrade.
    defaults = InferenceConfig()
    section: dict = {
        "backend": config.backend.value,
        "model": config.model,
        "api_key": config.api_key,
        "base_url": config.base_url,
    }
    if config.timeout != defaults.timeout:
        section["timeout"] = config.timeout
    if config.max_output_tokens != defaults.max_output_tokens:
        section["max_output_tokens"] = config.max_output_tokens
    if config.max_input_tokens != defaults.max_input_tokens:
        section["max_input_tokens"] = config.max_input_tokens
    if config.max_sessions != defaults.max_sessions:
        section["max_sessions"] = config.max_sessions
    if config.temperature != defaults.temperature:
        section["temperature"] = config.temperature
    if config.thinking != defaults.thinking:
        section["thinking"] = config.thinking
    existing["inference"] = section
    # Remove legacy "llm" key if present
    existing.pop("llm", None)

    SETTINGS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_JSON_PATH.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    logger.info("Saved inference config to %s", SETTINGS_JSON_PATH)


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
    Settings._yaml_file = resolved_path
    try:
        settings = Settings(_env_file=".env", _env_file_encoding="utf-8")
    finally:
        Settings._yaml_file = None
    if resolved_path:
        logger.info("Loaded config from %s", resolved_path)
    return settings
