"""FastAPI route aggregation."""

from fastapi import APIRouter

from vibelens.api.dashboard import router as dashboard_router
from vibelens.api.donation import router as donation_router
from vibelens.api.friction import router as friction_router
from vibelens.api.insights import router as insights_router
from vibelens.api.sessions import router as sessions_router
from vibelens.api.shares import router as shares_router
from vibelens.api.skill_analysis import router as skill_analysis_router
from vibelens.api.skill_management import router as skills_router
from vibelens.api.system import router as system_router
from vibelens.api.upload import router as upload_router


def build_router() -> APIRouter:
    """Aggregate all sub-routers into a single API router."""
    router = APIRouter()
    router.include_router(sessions_router)
    router.include_router(donation_router)
    router.include_router(upload_router)
    router.include_router(dashboard_router)
    router.include_router(shares_router)
    router.include_router(system_router)
    router.include_router(insights_router)
    router.include_router(friction_router)
    router.include_router(skills_router)
    router.include_router(skill_analysis_router)
    return router
