"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from vibelens import __version__
from vibelens.config import load_settings
from vibelens.db import init_db

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize database and optional MongoDB on startup."""
    settings = load_settings()
    await init_db(settings.db_path)

    mongodb_target = None
    mongodb_source = None

    if settings.mongodb_uri:
        from vibelens.sources.mongodb import MongoDBSource
        from vibelens.targets.mongodb import MongoDBTarget

        mongodb_target = MongoDBTarget(settings.mongodb_uri, db_name=settings.mongodb_db)
        mongodb_source = MongoDBSource(settings.mongodb_uri, db_name=settings.mongodb_db)
        await mongodb_target.ensure_indexes()
        logger.info("MongoDB connected: %s", settings.mongodb_db)

    yield

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
