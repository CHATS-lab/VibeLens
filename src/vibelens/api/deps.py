"""Dependency injection for FastAPI route handlers."""

from vibelens.config import Settings, load_settings, validate_mongodb_config
from vibelens.db import get_connection
from vibelens.sources.huggingface import HuggingFaceSource
from vibelens.sources.local import LocalSource
from vibelens.sources.mongodb import MongoDBSource
from vibelens.targets.mongodb import MongoDBTarget

_settings: Settings | None = None
_local_source: LocalSource | None = None
_hf_source: HuggingFaceSource | None = None
_mongodb_target: MongoDBTarget | None = None
_mongodb_source: MongoDBSource | None = None


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


def get_mongodb_target() -> MongoDBTarget:
    """Return cached MongoDBTarget instance.

    Raises:
        ValueError: If MongoDB is not configured.
    """
    global _mongodb_target
    if _mongodb_target is None:
        settings = get_settings()
        uri = validate_mongodb_config(settings)
        _mongodb_target = MongoDBTarget(uri, db_name=settings.mongodb_db)
    return _mongodb_target


def get_mongodb_source() -> MongoDBSource:
    """Return cached MongoDBSource instance.

    Raises:
        ValueError: If MongoDB is not configured.
    """
    global _mongodb_source
    if _mongodb_source is None:
        settings = get_settings()
        uri = validate_mongodb_config(settings)
        _mongodb_source = MongoDBSource(uri, db_name=settings.mongodb_db)
    return _mongodb_source
