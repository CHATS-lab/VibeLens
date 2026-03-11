"""Dependency injection for FastAPI route handlers."""

from vibelens.config import Settings, load_settings
from vibelens.db import get_connection

_settings: Settings | None = None


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
