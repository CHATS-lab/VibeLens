"""Subagent management API routes."""

from fastapi import APIRouter, HTTPException

from vibelens.deps import get_subagent_service
from vibelens.schemas.subagents import (
    SubagentDetailResponse,
    SubagentInstallRequest,
    SubagentListResponse,
    SubagentModifyRequest,
    SubagentSyncRequest,
    SubagentSyncTargetResponse,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/subagents", tags=["subagents"])

DEFAULT_PAGE_SIZE = 50


@router.post("/import/{agent}")
def import_from_agent(agent: str) -> dict:
    """Import all subagents from an agent directory into central store."""
    service = get_subagent_service()
    try:
        imported = service.import_all_from_agent(agent)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
    return {"agent": agent, "imported": imported, "count": len(imported)}


@router.get("")
def list_subagents(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    search: str | None = None,
    refresh: bool = False,
) -> SubagentListResponse:
    """List subagents with pagination, optional search, and sync targets."""
    service = get_subagent_service()
    if refresh:
        service.invalidate()
    subagents, total = service.list_subagents(page=page, page_size=page_size, search=search)
    targets = service.list_sync_targets()
    return SubagentListResponse(
        items=subagents,
        total=total,
        page=page,
        page_size=page_size,
        sync_targets=[
            SubagentSyncTargetResponse(
                agent=t.agent, subagent_count=t.subagent_count, subagents_dir=t.subagents_dir
            )
            for t in targets
        ],
    )


@router.get("/{name}")
def get_subagent(name: str) -> SubagentDetailResponse:
    """Get full subagent detail with content."""
    service = get_subagent_service()
    try:
        subagent = service.get_subagent(name)
        content = service.get_subagent_content(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subagent {name!r} not found") from None
    return SubagentDetailResponse(
        subagent=subagent, content=content, path=str(service._central.root / f"{name}.md")
    )


@router.post("")
def install_subagent(req: SubagentInstallRequest) -> dict:
    """Install a new subagent."""
    service = get_subagent_service()
    try:
        subagent = service.install(name=req.name, content=req.content, sync_to=req.sync_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return subagent.model_dump()


@router.put("/{name}")
def modify_subagent(name: str, req: SubagentModifyRequest) -> dict:
    """Update an existing subagent's content."""
    service = get_subagent_service()
    try:
        subagent = service.modify(name=name, content=req.content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subagent {name!r} not found") from None
    return subagent.model_dump()


@router.delete("/{name}")
def uninstall_subagent(name: str) -> dict:
    """Delete a subagent from central and all agent stores."""
    service = get_subagent_service()
    try:
        removed_from = service.uninstall(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subagent {name!r} not found") from None
    return {"deleted": name, "removed_from": removed_from}


@router.post("/{name}/agents")
def sync_subagent(name: str, req: SubagentSyncRequest) -> dict:
    """Sync a subagent to specified agent platforms."""
    service = get_subagent_service()
    try:
        results = service.sync_to_agents(name, req.agents)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subagent {name!r} not found") from None
    subagent = service.get_subagent(name)
    return {"name": name, "results": results, "subagent": subagent.model_dump()}


@router.delete("/{name}/agents/{agent}")
def unsync_subagent(name: str, agent: str) -> dict:
    """Remove a subagent from a single agent platform."""
    service = get_subagent_service()
    try:
        service.uninstall_from_agent(name, agent)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Subagent {name!r} not in agent {agent!r}"
        ) from None
    subagent = service.get_subagent(name)
    return {"name": name, "agent": agent, "subagent": subagent.model_dump()}
