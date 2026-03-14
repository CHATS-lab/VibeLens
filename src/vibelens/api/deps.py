"""Dependency injection for FastAPI route handlers."""

from vibelens.config import Settings, load_settings
from vibelens.db import get_connection
from vibelens.sources.huggingface import HuggingFaceSource
from vibelens.sources.local import LocalSource

_settings: Settings | None = None
_local_source: LocalSource | None = None
_hf_source: HuggingFaceSource | None = None


async def get_db():  # noqa: ANN201
    """Yield a database connection."""
    conn = await get_connection()
    try:
        yield conn
    finally:
        await conn.close()


def get_settings() -> Settings:
    """Return cached application settings."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def get_local_source() -> LocalSource:
    """Return cached LocalSource instance."""
    global _local_source
    if _local_source is None:
        settings = get_settings()
        _local_source = LocalSource(settings.claude_dir)
    return _local_source


def get_hf_source() -> HuggingFaceSource:
    """Return cached HuggingFaceSource instance."""
    global _hf_source
    if _hf_source is None:
        settings = get_settings()
        data_dir = settings.db_path.parent
        _hf_source = HuggingFaceSource(data_dir, hf_token=settings.hf_token)
    return _hf_source
