"""FastAPI application factory."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from vibelens import __version__
from vibelens.config import load_settings
from vibelens.config.settings import Settings
from vibelens.db import init_db
from vibelens.models.enums import AppMode
from vibelens.stores import SHARED_TOKEN, MemorySessionStore, SessionStore

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
TTL_CLEANUP_INTERVAL_SECONDS = 60


async def _load_example_sessions(store: SessionStore, settings: Settings) -> int:
    """Parse configured example files and store under shared token.

    Args:
        store: The session store to load examples into.
        settings: Application settings with example_session_paths.

    Returns:
        Number of sessions loaded.
    """
    from vibelens.ingest.fingerprint import parse_auto
    from vibelens.models.enums import DataSourceType

    loaded = 0
    for file_path in settings.example_session_paths:
        if not file_path.exists():
            logger.warning("Example session file not found: %s", file_path)
            continue
        try:
            parsed = parse_auto(file_path)
            for summary, messages in parsed:
                summary.source_type = DataSourceType.LOCAL
                summary.source_name = f"example:{file_path.name}"
                stored = await store.store_session(summary, messages, SHARED_TOKEN)
                if stored:
                    loaded += 1
        except (ValueError, OSError) as exc:
            logger.warning("Failed to load example %s: %s", file_path.name, exc)
    return loaded


async def _ttl_cleanup_loop(store: MemorySessionStore, interval_seconds: int) -> None:
    """Periodically evict expired token buckets.

    Args:
        store: MemorySessionStore to clean up.
        interval_seconds: Sleep interval between cleanup runs.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        store.cleanup_expired()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize database and optional MongoDB on startup."""
    settings = load_settings()
    is_demo = settings.app_mode == AppMode.DEMO
    uses_memory = is_demo and settings.demo_storage == "memory"

    # Initialize session store via deps so all endpoints share the same instance
    from vibelens.api.deps import get_session_store

    store = get_session_store()

    # Skip SQLite init when demo mode uses pure memory storage
    if not uses_memory:
        await init_db(settings.db_path)
        settings.upload_dir.mkdir(parents=True, exist_ok=True)

    # Load example sessions in demo mode
    cleanup_task = None
    if is_demo:
        loaded = await _load_example_sessions(store, settings)
        if loaded:
            logger.info("Loaded %d example sessions for demo mode", loaded)

        # Start TTL cleanup for memory store
        if isinstance(store, MemorySessionStore):
            cleanup_task = asyncio.create_task(
                _ttl_cleanup_loop(store, TTL_CLEANUP_INTERVAL_SECONDS)
            )

    # Skip MongoDB in demo mode
    mongodb_target = None
    mongodb_source = None
    if not is_demo and settings.mongodb_uri:
        from vibelens.sources.mongodb import MongoDBSource
        from vibelens.targets.mongodb import MongoDBTarget

        mongodb_target = MongoDBTarget(settings.mongodb_uri, db_name=settings.mongodb_db)
        mongodb_source = MongoDBSource(settings.mongodb_uri, db_name=settings.mongodb_db)
        await mongodb_target.ensure_indexes()
        logger.info("MongoDB connected: %s", settings.mongodb_db)

    yield

    if cleanup_task:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
    if mongodb_target:
        await mongodb_target.close()
    if mongodb_source:
        await mongodb_source.close()


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    from vibelens.api import build_router

    app = FastAPI(title="VibeLens", version=__version__, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_router(), prefix="/api")

    if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
