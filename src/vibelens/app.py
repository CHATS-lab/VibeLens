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
from vibelens.config import load_settings
from vibelens.deps import (
    get_agent_skill_stores,
    get_central_skill_store,
    get_codex_skill_store,
    get_example_store,
    get_llm_config,
    get_skill_analysis_store,
    get_skill_store,
    get_store,
    reconstruct_upload_registry,
)
from vibelens.models.enums import AppMode
from vibelens.services.dashboard.loader import warm_cache
from vibelens.services.job_tracker import cleanup_stale as cleanup_stale_jobs
from vibelens.services.session.demo import load_demo_examples
from vibelens.services.session.search import build_search_index
from vibelens.utils import get_logger

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


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
    settings = load_settings()

    # Initialize the trajectory store (local or disk)
    store = get_store()
    store.initialize()
    _log_startup_summary(settings, store)

    if settings.app_mode == AppMode.DEMO:
        example_store = get_example_store()
        example_store.initialize()
        loaded = load_demo_examples(settings, example_store)
        if loaded:
            logger.info("Loaded %d trajectory groups for demo mode", loaded)
        reconstruct_upload_registry()

    # Lightweight startup tasks in a thread (no heavy I/O)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _lightweight_startup, settings)

    # Build search index eagerly so first search is instant
    asyncio.create_task(_async_build_search_index())

    # Dashboard cache warming as an async background task so it yields
    # the event loop between session batches instead of holding the GIL
    asyncio.create_task(_async_warm_cache())

    # Periodic cleanup of finished job tracker entries to prevent memory leak
    cleanup_task = asyncio.create_task(_periodic_job_cleanup())

    yield

    cleanup_task.cancel()


JOB_CLEANUP_INTERVAL_SECONDS = 600


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


async def _async_build_search_index() -> None:
    """Pre-build the search index at startup so the first query is instant."""
    try:
        await asyncio.to_thread(build_search_index)
    except Exception:
        logger.warning("Search index pre-build failed", exc_info=True)


async def _async_warm_cache() -> None:
    """Run dashboard cache warming in the background, yielding periodically.

    Wraps the synchronous warm_cache() in asyncio.to_thread so it runs
    in the default thread pool. Unlike run_in_executor fire-and-forget,
    this is a proper task that can be awaited and doesn't silently swallow
    exceptions.
    """
    try:
        await asyncio.to_thread(warm_cache)
    except Exception:
        logger.warning("Dashboard cache warming failed", exc_info=True)


def _lightweight_startup(settings) -> None:
    """Run lightweight startup tasks in a background thread.

    Skill import and mock seeding are fast and don't involve heavy
    JSON parsing, so a thread is fine.
    """
    _load_agent_skills_into_central_store()
    if settings.app_mode in (AppMode.TEST, AppMode.DEMO):
        _seed_mock_skill_history()


def _load_agent_skills_into_central_store() -> None:
    """Import skills from all agent interfaces into the central store on startup.

    Scans Claude Code, Codex, and all third-party agent skill directories,
    copying any skills not already present in the central repository (~/.vibelens/skills/).
    Existing central skills are never overwritten to preserve user edits.
    """
    central = get_central_skill_store()
    agent_stores = [
        ("claude_code", get_skill_store()),
        ("codex", get_codex_skill_store()),
        *((s.source_type.value, s) for s in get_agent_skill_stores()),
    ]
    total_imported = 0
    for label, store in agent_stores:
        try:
            imported = central.import_all_from(store, overwrite=False)
            if imported:
                logger.info("Imported %d skills from %s into central store", len(imported), label)
                total_imported += len(imported)
        except Exception:
            logger.warning("Failed to import skills from %s", label, exc_info=True)

    if total_imported:
        logger.info("Total skills imported into central store: %d", total_imported)


def _seed_mock_skill_history() -> None:
    """Pre-populate skill analysis history with one record per mode.

    Picks the first 3 available session IDs from the trajectory store
    and generates mock analysis results for retrieval, creation, and
    evolution modes so the History sidebar has sample entries.
    """
    from vibelens.models.skill.skills import SkillMode
    from vibelens.services.skill.mock import build_mock_skill_result

    analysis_store = get_skill_analysis_store()

    # Skip seeding if history already has records
    if analysis_store.list_analyses():
        return

    from vibelens.services.session.store_resolver import list_all_metadata

    metadata = list_all_metadata()
    session_ids = [m["session_id"] for m in metadata if "session_id" in m][:3]
    if not session_ids:
        logger.info("No sessions available to seed skill analysis history")
        return

    for mode in (SkillMode.RETRIEVAL, SkillMode.CREATION, SkillMode.EVOLUTION):
        try:
            result = build_mock_skill_result(session_ids, mode)
            analysis_store.save(result)
            logger.info("Seeded mock skill analysis history: mode=%s", mode)
        except Exception:
            logger.warning("Failed to seed mock skill analysis for mode=%s", mode, exc_info=True)


def _log_startup_summary(settings, store) -> None:
    """Log a single-line startup summary with key configuration details."""
    llm_config = get_llm_config()
    store_type = type(store).__name__
    logger.info(
        "VibeLens v%s started: mode=%s store=%s llm_backend=%s host=%s:%d",
        __version__,
        settings.app_mode.value,
        store_type,
        llm_config.backend.value,
        settings.host,
        settings.port,
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
    app.include_router(build_router(), prefix="/api")

    if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app
