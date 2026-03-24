"""Skill management API routes — list, view, install, edit, delete, search."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from vibelens.deps import get_skill_store
from vibelens.models.skill import VALID_SKILL_NAME

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillWriteRequest(BaseModel):
    """Request body for creating or updating a skill."""

    name: str = Field(description="Skill name in kebab-case.")
    content: str = Field(description="Full SKILL.md content including frontmatter.")


@router.get("/local")
def list_local_skills() -> list[dict]:
    """List all locally installed skills with metadata."""
    store = get_skill_store()
    skills = store.get_cached()
    return [s.model_dump(mode="json") for s in skills]


@router.get("/search")
def search_skills(q: str = "") -> list[dict]:
    """Search installed skills by name or description."""
    store = get_skill_store()
    if not q.strip():
        return [s.model_dump(mode="json") for s in store.get_cached()]
    results = store.search_skills(q)
    return [s.model_dump(mode="json") for s in results]


@router.get("/local/{name}")
def get_local_skill_content(name: str) -> dict:
    """Read the full content of a locally installed skill."""
    store = get_skill_store()
    info = store.get_skill(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found")

    content = store.read_content(name)
    return {"name": name, "content": content, "info": info.model_dump(mode="json")}


@router.post("/install")
def install_skill(req: SkillWriteRequest) -> dict:
    """Install a new skill by writing its SKILL.md content."""
    if not VALID_SKILL_NAME.match(req.name):
        raise HTTPException(status_code=422, detail="Skill name must be kebab-case")
    if not req.content.strip():
        raise HTTPException(status_code=422, detail="Skill content must not be empty")

    store = get_skill_store()
    existing = store.get_skill(req.name)
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Skill {req.name!r} already exists. Use PUT to update."
        )

    path = store.write_skill(req.name, req.content)
    info = store.get_skill(req.name)
    return {"path": str(path), "info": info.model_dump(mode="json") if info else None}


@router.put("/local/{name}")
def update_skill(name: str, req: SkillWriteRequest) -> dict:
    """Update an existing skill's SKILL.md content."""
    store = get_skill_store()
    if not store.get_skill(name):
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found")
    if not req.content.strip():
        raise HTTPException(status_code=422, detail="Skill content must not be empty")

    path = store.write_skill(name, req.content)
    info = store.get_skill(name)
    return {"path": str(path), "info": info.model_dump(mode="json") if info else None}


@router.delete("/local/{name}")
def delete_skill(name: str) -> dict:
    """Delete an installed skill and its entire directory."""
    store = get_skill_store()
    deleted = store.delete_skill(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found")
    return {"deleted": name}
