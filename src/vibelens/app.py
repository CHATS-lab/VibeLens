"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from vibelens import __version__
from vibelens.api import build_router
from vibelens.api.demo_guard import DemoGuardMiddleware
from vibelens.deps import (
    get_example_store,
    get_inference_config,
    get_plugin_service,
    get_settings,
    get_skill_service,
    get_trajectory_store,
    is_demo_mode,
    reconstruct_upload_registry,
)
from vibelens.models.enums import AppMode
from vibelens.services.dashboard.loader import warm_cache
from vibelens.services.extensions.search import (
    warm_index as warm_extension_search_index,
)
from vibelens.services.job_tracker import cleanup_stale as cleanup_stale_jobs
from vibelens.services.session.demo import (
    load_demo_examples,
    seed_example_analyses,
    seed_example_skills,
)
from vibelens.services.session.search import (
    build_full_search_index,
    build_search_index,
    refresh_search_index,
)
from vibelens.storage.extension.catalog import _clear_user_catalog, load_catalog
from vibelens.utils import get_logger
from vibelens.utils.log import configure_logging

logger = get_logger(__name__)

# Directory containing the built React frontend assets
STATIC_DIR = Path(__file__).parent / "static"
# How often to evict finished jobs from the in-memory tracker
JOB_CLEANUP_INTERVAL_SECONDS = 600


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize store and start background tasks on startup.

    Only essential setup (store init, demo loading) runs synchronously.
    Skill import and mock seeding run in a thread (lightweight).
    Dashboard cache warming runs as an async task that processes
    sessions in batches, yielding the event loop between batches
    so other endpoints (friction history, LLM status) can respond
    without waiting for all sessions to finish loading.
    """
    settings = get_settings()
    configure_logging(settings.logging)

    _clear_user_catalog()
    load_catalog()

    # Initialize the trajectory store (local or disk)
    store = get_trajectory_store()
    store.initialize()
    _log_startup_summary(settings, store)

    # Load example sessions (demo: required, self: for example analyses)
    if settings.demo.session_paths:
        example_store = get_example_store()
        example_store.initialize()
        loaded = load_demo_examples(settings, example_store)
        if loaded:
            logger.info("Loaded %d example trajectory groups", loaded)

    if settings.mode == AppMode.DEMO:
        reconstruct_upload_registry()

    # All heavy work runs in background so the server accepts connections immediately
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_background_startup)

    # Tier 1 search index runs synchronously — triggers lazy session indexing
    # which the dashboard and session list APIs depend on at first request
    build_search_index()

    # Dashboard cache warming and full-text search run in background
    asyncio.create_task(_async_warm_cache())
    asyncio.create_task(_async_build_full_search_index())
    # Extension catalog search index (~0.5s cold build on 28K items)
    asyncio.create_task(_async_warm_extension_index())

    # Periodic incremental search index refresh (diff-based, <1s typical)
    search_refresh_task = asyncio.create_task(_periodic_search_refresh())

    # Periodic cleanup of finished job tracker entries to prevent memory leak
    cleanup_task = asyncio.create_task(_periodic_job_cleanup())

    yield

    search_refresh_task.cancel()
    cleanup_task.cancel()


async def _periodic_job_cleanup() -> None:
    """Evict finished jobs from the in-memory tracker every 10 minutes."""
    while True:
        await asyncio.sleep(JOB_CLEANUP_INTERVAL_SECONDS)
        try:
            cleanup_stale_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Job cleanup failed", exc_info=True)


async def _async_warm_cache() -> None:
    """Warm the dashboard cache in a background thread."""
    try:
        await asyncio.to_thread(warm_cache)
    except Exception:
        logger.warning("Dashboard cache warming failed", exc_info=True)


async def _async_build_full_search_index() -> None:
    """Build the full-text (Tier 2) search index in a background thread."""
    try:
        await asyncio.to_thread(build_full_search_index)
    except Exception:
        logger.warning("Full search index build failed", exc_info=True)


async def _async_warm_extension_index() -> None:
    """Build the extension catalog search index in a background thread."""
    try:
        await asyncio.to_thread(warm_extension_search_index)
    except Exception:
        logger.warning("Extension catalog search index warm failed", exc_info=True)


# How often to diff-refresh the search index for new sessions
SEARCH_REFRESH_INTERVAL_SECONDS = 300


async def _periodic_search_refresh() -> None:
    """Incrementally refresh the search index every 5 minutes.

    Uses diff-based refresh that only loads new sessions and removes
    stale ones, completing in <1s for typical workloads.
    """
    while True:
        await asyncio.sleep(SEARCH_REFRESH_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(refresh_search_index)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Search index refresh failed", exc_info=True)


def _run_background_startup() -> None:
    """Run lightweight startup tasks in a background thread.

    Skill import and example seeding are fast and don't involve heavy
    JSON parsing, so a thread is fine.
    """
    get_skill_service().import_all_agents()
    get_plugin_service().import_all_agents()
    seed_example_analyses()
    seed_example_skills()


def _log_startup_summary(settings, store) -> None:
    """Log a single-line startup summary with key configuration details."""
    inference = get_inference_config()
    store_type = type(store).__name__
    logger.info(
        "VibeLens v%s started: mode=%s store=%s llm_backend=%s host=%s:%d",
        __version__,
        settings.mode.value,
        store_type,
        inference.backend.value,
        settings.server.host,
        settings.server.port,
    )


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(title="VibeLens", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if is_demo_mode():
        app.add_middleware(DemoGuardMiddleware)

    app.include_router(build_router(), prefix="/api")

    if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app
