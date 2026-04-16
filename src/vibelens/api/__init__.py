"""FastAPI route aggregation."""

from fastapi import APIRouter

from vibelens.api.command import router as commands_router
from vibelens.api.creation import router as creation_router
from vibelens.api.dashboard import router as dashboard_router
from vibelens.api.donation import router as donation_router
from vibelens.api.evolution import router as evolution_router
from vibelens.api.extensions import router as extensions_router
from vibelens.api.friction import router as friction_router
from vibelens.api.hook import router as hooks_router
from vibelens.api.recommendation import router as recommendation_router
from vibelens.api.sessions import router as sessions_router
from vibelens.api.shares import router as shares_router
from vibelens.api.skill import router as skills_router
from vibelens.api.subagent import router as subagents_router
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
    router.include_router(friction_router)
    router.include_router(skills_router)
    router.include_router(commands_router)
    router.include_router(subagents_router)
    router.include_router(hooks_router)
    router.include_router(creation_router)
    router.include_router(evolution_router)
    router.include_router(recommendation_router)
    router.include_router(extensions_router)
    return router
