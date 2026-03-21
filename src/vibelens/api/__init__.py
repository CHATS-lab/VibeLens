"""FastAPI route aggregation."""

from fastapi import APIRouter

from vibelens.api.dashboard import router as dashboard_router
from vibelens.api.sessions import router as sessions_router
from vibelens.api.system import router as system_router
from vibelens.api.upload import router as upload_router


def build_router() -> APIRouter:
    """Aggregate all sub-routers into a single API router."""
    router = APIRouter()
    router.include_router(sessions_router)
    router.include_router(upload_router)
    router.include_router(dashboard_router)
    router.include_router(system_router)
    return router
