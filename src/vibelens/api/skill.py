"""Skill management API routes."""

from fastapi import APIRouter, HTTPException

from vibelens.deps import get_skill_service
from vibelens.schemas.skills import (
    SkillDetailResponse,
    SkillInstallRequest,
    SkillListResponse,
    SkillModifyRequest,
    SkillSyncRequest,
    SkillSyncTargetResponse,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])

DEFAULT_PAGE_SIZE = 50


@router.post("/import/{agent}")
def import_from_agent(agent: str) -> dict:
    """Import all skills from an agent directory into central store."""
    service = get_skill_service()
    try:
        imported = service.import_all_from_agent(agent)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
    return {"agent": agent, "imported": imported, "count": len(imported)}


@router.get("")
def list_skills(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    search: str | None = None,
    refresh: bool = False,
) -> SkillListResponse:
    """List skills with pagination, optional search, and sync targets."""
    service = get_skill_service()
    if refresh:
        service.invalidate()
    skills, total = service.list_skills(page=page, page_size=page_size, search=search)
    targets = service.list_sync_targets()
    return SkillListResponse(
        items=skills,
        total=total,
        page=page,
        page_size=page_size,
        sync_targets=[
            SkillSyncTargetResponse(
                agent=t.agent, skill_count=t.skill_count, skills_dir=t.skills_dir
            )
            for t in targets
        ],
    )


@router.get("/{name}")
def get_skill(name: str) -> SkillDetailResponse:
    """Get full skill detail with content."""
    service = get_skill_service()
    try:
        skill = service.get_skill(name)
        content = service.get_skill_content(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found") from None
    return SkillDetailResponse(skill=skill, content=content, path=str(service._central.root / name))


@router.post("")
def install_skill(req: SkillInstallRequest) -> dict:
    """Install a new skill."""
    service = get_skill_service()
    try:
        skill = service.install(name=req.name, content=req.content, sync_to=req.sync_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return skill.model_dump()


@router.put("/{name}")
def modify_skill(name: str, req: SkillModifyRequest) -> dict:
    """Update an existing skill's content."""
    service = get_skill_service()
    try:
        skill = service.modify(name=name, content=req.content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found") from None
    return skill.model_dump()


@router.delete("/{name}")
def uninstall_skill(name: str) -> dict:
    """Delete a skill from central and all agent stores."""
    service = get_skill_service()
    try:
        removed_from = service.uninstall(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found") from None
    return {"deleted": name, "removed_from": removed_from}


@router.post("/{name}/agents")
def sync_skill(name: str, req: SkillSyncRequest) -> dict:
    """Sync a skill to specified agent platforms."""
    service = get_skill_service()
    try:
        results = service.sync_to_agents(name, req.agents)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found") from None
    skill = service.get_skill(name)
    return {"name": name, "results": results, "skill": skill.model_dump()}


@router.delete("/{name}/agents/{agent}")
def unsync_skill(name: str, agent: str) -> dict:
    """Remove a skill from a single agent platform."""
    service = get_skill_service()
    try:
        service.uninstall_from_agent(name, agent)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Skill {name!r} not in agent {agent!r}"
        ) from None
    skill = service.get_skill(name)
    return {"name": name, "agent": agent, "skill": skill.model_dump()}
