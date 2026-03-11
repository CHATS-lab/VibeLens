"""Application configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """VibeLens configuration loaded from environment / .env file."""

    model_config = {"env_prefix": "VIBELENS_"}

    # Server
    host: str = "127.0.0.1"
    port: int = 12001

    # Local Claude Code data
    claude_dir: Path = Path.home() / ".claude"

    # Database
    db_path: Path = Path.home() / ".vibelens" / "vibelens.db"

    # MongoDB (optional)
    mongodb_uri: str = ""
    mongodb_db: str = "vibelens"

    # HuggingFace (optional)
    hf_token: str = ""


def load_settings() -> Settings:
    """Load settings from environment and .env file."""
    return Settings(_env_file=".env", _env_file_encoding="utf-8")
