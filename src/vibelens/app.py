"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from vibelens import __version__
from vibelens.config import load_settings
from vibelens.deps import get_store
from vibelens.models.enums import AppMode
from vibelens.services.dashboard_service import warm_cache
from vibelens.services.demo_loader import load_demo_examples
from vibelens.storage.disk import DiskStore
from vibelens.utils import get_logger

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize store and load demo data on startup."""
    settings = load_settings()

    store = get_store()
    store.initialize()

    if settings.app_mode == AppMode.DEMO and isinstance(store, DiskStore):
        loaded = load_demo_examples(settings, store)
        if loaded:
            logger.info("Loaded %d trajectory groups for demo mode", loaded)

    # Pre-compute dashboard in background thread (doesn't block server startup)
    asyncio.get_event_loop().run_in_executor(None, warm_cache)

    yield


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
