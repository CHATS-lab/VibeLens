"""FastAPI route aggregation."""

from fastapi import APIRouter

from vibelens.api.analysis import router as analysis_router
from vibelens.api.pull import router as pull_router
from vibelens.api.push import router as push_router
from vibelens.api.sessions import router as sessions_router
from vibelens.api.system import router as system_router
from vibelens.api.upload import router as upload_router


def build_router() -> APIRouter:
    """Aggregate all sub-routers into a single API router."""
    router = APIRouter()
    router.include_router(sessions_router)
    router.include_router(push_router)
    router.include_router(pull_router)
    router.include_router(upload_router)
    router.include_router(analysis_router)
    router.include_router(system_router)
    return router
