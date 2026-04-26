"""FastAPI application factory."""

import asyncio
import logging
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
from vibelens.utils.startup import PROGRESS, Status, quiet_vibelens_logger

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
    # configure_logging resets the vibelens logger level, undoing the WARNING
    # quiet that start_spinner installed in cli.py. Re-apply it while startup
    # is still running so INFO chatter does not leak into the banner.
    if PROGRESS.status is Status.RUNNING:
        quiet_vibelens_logger()

    search_refresh_task: asyncio.Task | None = None
    cleanup_task: asyncio.Task | None = None

    try:
        PROGRESS.set("Loading extension catalog…")
        _clear_user_catalog()
        catalog = load_catalog()

        PROGRESS.set("Building session index…")
        store = get_trajectory_store()
        store.initialize()
        # Eagerly trigger the lazy index build so the spinner reflects real
        # progress; session_count() calls _ensure_index() under the hood.
        session_count = await asyncio.to_thread(store.session_count)
        _log_startup_summary(settings, store)

        if settings.demo.session_paths:
            example_store = get_example_store()
            example_store.initialize()
            loaded = load_demo_examples(settings, example_store)
            if loaded:
                logger.info("Loaded %d example trajectory groups", loaded)

        if settings.mode == AppMode.DEMO:
            reconstruct_upload_registry()

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _run_background_startup)

        if settings.search.enabled:
            build_search_index()
            asyncio.create_task(_async_build_full_search_index())
            search_refresh_task = asyncio.create_task(_periodic_search_refresh())
        else:
            logger.info(
                "Session search index disabled (settings.search.enabled=false); "
                "skipping Tier 1/2 build to save ~2-3 GB RSS"
            )

        PROGRESS.set("Warming dashboard cache…")
        await asyncio.to_thread(warm_cache)

        asyncio.create_task(_async_warm_extension_index())
        cleanup_task = asyncio.create_task(_periodic_job_cleanup())

        extension_count = catalog.manifest.total if catalog else None
        PROGRESS.totals(sessions=session_count, extensions=extension_count)
        PROGRESS.mark_ready()

        # Restore uvicorn loggers so request access logs resume after ready.
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    except Exception:
        PROGRESS.mark_failed()
        raise

    yield

    if search_refresh_task is not None:
        search_refresh_task.cancel()
    if cleanup_task is not None:
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
