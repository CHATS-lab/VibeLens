"""Extension API router aggregation."""

from fastapi import APIRouter

from vibelens.api.extensions.agents import router as agents_router
from vibelens.api.extensions.catalog import router as catalog_router
from vibelens.api.extensions.collections import build_collections_router
from vibelens.api.extensions.factory import build_typed_router
from vibelens.api.extensions.hook import router as hooks_router
from vibelens.deps import (
    get_collection_service,
    get_command_service,
    get_plugin_service,
    get_skill_service,
    get_subagent_service,
)
from vibelens.models.enums import AgentExtensionType


def build_extensions_router() -> APIRouter:
    """Aggregate all extension sub-routers under /extensions prefix."""
    extensions_router = APIRouter(prefix="/extensions", tags=["extensions"])
    extensions_router.include_router(catalog_router, prefix="/catalog")
    extensions_router.include_router(agents_router)
    extensions_router.include_router(
        build_typed_router(get_skill_service, AgentExtensionType.SKILL)
    )
    extensions_router.include_router(
        build_typed_router(get_plugin_service, AgentExtensionType.PLUGIN)
    )
    extensions_router.include_router(
        build_typed_router(get_command_service, AgentExtensionType.COMMAND)
    )
    extensions_router.include_router(
        build_typed_router(get_subagent_service, AgentExtensionType.SUBAGENT)
    )
    extensions_router.include_router(hooks_router)
    extensions_router.include_router(build_collections_router(get_collection_service))
    return extensions_router
