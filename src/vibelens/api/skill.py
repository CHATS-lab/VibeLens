"""Skill management API routes — list, view, install, edit, delete, search."""

import json
import logging
from pathlib import Path

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException

from vibelens.deps import get_agent_extension_stores, get_central_extension_store
from vibelens.models.extension import VALID_EXTENSION_NAME
from vibelens.schemas.skills import (
    FeaturedSkillInstallRequest,
    SkillLoadRequest,
    SkillSyncRequest,
    SkillWriteRequest,
)
from vibelens.services.extensions.skill import download_skill_directory
from vibelens.services.inference_shared import CACHE_TTL_SECONDS
from vibelens.storage.extension.disk import DiskExtensionStore
from vibelens.utils.github import github_tree_to_raw_url
from vibelens.utils.http import fetch_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])

# JSON manifest of featured skills shipped with the package
FEATURED_SKILLS_PATH = Path(__file__).resolve().parents[3] / "featured-skills.json"
# Default number of skills returned per page in listing endpoints
DEFAULT_PAGE_SIZE = 50


def _find_store_by_key(
    stores: dict, source_key: str
) -> DiskExtensionStore | None:
    """Find an agent store by its ExtensionSource value string, or None."""
    for src, store in stores.items():
        if src.value == source_key:
            return store
    return None


def _resolve_agent_store(source_key: str) -> DiskExtensionStore:
    """Look up an agent extension store by its ExtensionSource value string.

    Args:
        source_key: ExtensionSource value (e.g. "claude", "codex", "cursor").

    Raises:
        HTTPException 404 if no installed agent matches the key.
    """
    store = _find_store_by_key(get_agent_extension_stores(), source_key)
    if not store:
        raise HTTPException(status_code=404, detail=f"Agent store not found: {source_key}")
    return store


@router.get("/local")
def list_local_skills(
    refresh: bool = False, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE
) -> dict:
    """List locally installed skills with pagination.

    Args:
        refresh: If True, invalidate cache and rescan disk before returning.
        page: 1-based page number.
        page_size: Number of skills per page (default 50).

    Returns:
        Dict with items, total count, page, and page_size.
    """
    store = get_central_extension_store()
    if refresh:
        store.invalidate_cache()
    all_skills = store.get_cached()
    total = len(all_skills)
    start = (max(page, 1) - 1) * page_size
    end = start + page_size
    page_items = all_skills[start:end]
    return {
        "items": [s.model_dump(mode="json") for s in page_items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/load/{source}")
def load_skills(source: str, req: SkillLoadRequest) -> dict:
    """Load all skills from an agent-native store into the central store."""
    source_store = _resolve_agent_store(source)
    central_store = get_central_extension_store()
    imported = central_store.import_all_from(source_store, overwrite=req.overwrite)
    return {
        "source": source,
        "count": len(imported),
        "skills": [skill.model_dump(mode="json") for skill in imported],
    }


@router.get("/featured")
def list_featured_skills() -> dict:
    """Return featured skills from the curated catalog.

    Reads from the bundled featured-skills.json file, which contains
    community skills scraped from the Anthropic skills-hub registry.
    """
    if not FEATURED_SKILLS_PATH.is_file():
        logger.warning("featured-skills.json not found at %s", FEATURED_SKILLS_PATH)
        return {"updated_at": None, "total": 0, "categories": [], "skills": []}
    try:
        raw = FEATURED_SKILLS_PATH.read_text(encoding="utf-8")
        return json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read featured-skills.json: %s", exc)
        return {"updated_at": None, "total": 0, "categories": [], "skills": []}


@router.post("/featured/install")
def install_featured_skill(req: FeaturedSkillInstallRequest) -> dict:
    """Install a featured skill from the catalog into the central store.

    Fetches the skill's SKILL.md content from GitHub, writes it to the
    central store, and optionally syncs to specified agent interfaces.

    Args:
        req: Slug of the featured skill and optional target agent interfaces.

    Returns:
        Dict with install results and the created SkillInfo.
    """
    if not FEATURED_SKILLS_PATH.is_file():
        raise HTTPException(status_code=404, detail="Featured skills catalog not found")

    try:
        catalog = json.loads(FEATURED_SKILLS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read catalog: {exc}") from exc

    matched = next((s for s in catalog.get("skills", []) if s["slug"] == req.slug), None)
    if not matched:
        raise HTTPException(status_code=404, detail=f"Skill {req.slug!r} not found in catalog")

    central = get_central_extension_store()
    if central.get_extension(req.slug):
        raise HTTPException(status_code=409, detail=f"Skill {req.slug!r} already installed")

    # Download complete skill directory from GitHub (SKILL.md + auxiliary files)
    source_url = matched.get("source_url", "")
    skill_dir = central.extension_path(req.slug)
    downloaded = download_skill_directory(source_url, skill_dir) if source_url else False

    if not downloaded:
        # Fallback: build a minimal SKILL.md from catalog metadata
        logger.warning("GitHub download failed for %s, using catalog stub", req.slug)
        skill_content = _build_skill_md_from_catalog(matched)
        central.write_extension(req.slug, skill_content)

    # Sync to requested agent interfaces
    agent_stores = get_agent_extension_stores()
    sync_results = {}
    for target_key in req.targets:
        target_store = _find_store_by_key(agent_stores, target_key)
        if not target_store:
            sync_results[target_key] = {"synced": False, "error": f"Unknown target: {target_key}"}
            continue
        try:
            copied = target_store.import_extension_from(central, req.slug, overwrite=True)
            sync_results[target_key] = {"synced": bool(copied)}
            if copied:
                central._inject_source_metadata(req.slug, target_store)
        except Exception as exc:
            sync_results[target_key] = {"synced": False, "error": str(exc)}

    central.invalidate_cache()
    info = central.get_extension(req.slug)
    return {
        "name": req.slug,
        "info": info.model_dump(mode="json") if info else None,
        "sync_results": sync_results,
    }


_featured_content_cache: TTLCache = TTLCache(maxsize=32, ttl=CACHE_TTL_SECONDS)


@router.get("/featured/{slug}/content")
def get_featured_skill_content(slug: str) -> dict:
    """Fetch the SKILL.md content for a featured skill from GitHub.

    Uses an in-memory cache with 1-hour TTL to avoid repeated fetches.

    Args:
        slug: Skill slug from the featured catalog.

    Returns:
        Dict with slug and SKILL.md content string.
    """
    if slug in _featured_content_cache:
        return {"slug": slug, "content": _featured_content_cache[slug]}

    if not FEATURED_SKILLS_PATH.is_file():
        raise HTTPException(status_code=404, detail="Featured skills catalog not found")

    try:
        catalog = json.loads(FEATURED_SKILLS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read catalog: {exc}") from exc

    matched = next((s for s in catalog.get("skills", []) if s["slug"] == slug), None)
    if not matched:
        raise HTTPException(status_code=404, detail=f"Skill {slug!r} not found in catalog")

    source_url = matched.get("source_url", "")
    raw_url = github_tree_to_raw_url(tree_url=source_url, filename="SKILL.md")
    if not raw_url:
        raise HTTPException(status_code=404, detail=f"Cannot resolve content URL for {slug!r}")

    content = fetch_text(raw_url)
    if not content:
        raise HTTPException(status_code=502, detail=f"Failed to fetch SKILL.md for {slug!r}")

    _featured_content_cache[slug] = content
    return {"slug": slug, "content": content}


def _build_skill_md_from_catalog(catalog_entry: dict) -> str:
    """Build a SKILL.md file from a featured skills catalog entry.

    Creates frontmatter with description, tags, and source URL,
    followed by a placeholder body referencing the GitHub source.
    """
    name = catalog_entry.get("name", "")
    summary = catalog_entry.get("summary", "")
    tags = catalog_entry.get("tags", [])
    source_url = catalog_entry.get("source_url", "")
    category = catalog_entry.get("category", "")

    tag_str = json.dumps(tags + ([category] if category else []))

    return (
        f"---\n"
        f"description: {summary}\n"
        f"tags: {tag_str}\n"
        f"source_url: {source_url}\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"{summary}\n\n"
        f"## Source\n\n"
        f"Installed from the Anthropic Skills Hub.\n"
        f"Full skill definition: {source_url}\n"
    )


@router.get("/search")
def search_skills(q: str = "") -> list[dict]:
    """Search installed skills by name or description."""
    store = get_central_extension_store()
    if not q.strip():
        return [s.model_dump(mode="json") for s in store.get_cached()]
    results = store.search_extensions(q)
    return [s.model_dump(mode="json") for s in results]


@router.get("/local/{name}")
def get_local_skill_content(name: str) -> dict:
    """Read the full content of a locally installed skill."""
    store = get_central_extension_store()
    info = store.get_extension(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found")

    content = store.read_content(name)
    return {"name": name, "content": content, "info": info.model_dump(mode="json")}


@router.post("/install")
def install_skill(req: SkillWriteRequest) -> dict:
    """Install a new skill by writing its SKILL.md content."""
    if not VALID_EXTENSION_NAME.match(req.name):
        raise HTTPException(status_code=422, detail="Skill name must be kebab-case")
    if not req.content.strip():
        raise HTTPException(status_code=422, detail="Skill content must not be empty")

    store = get_central_extension_store()
    existing = store.get_extension(req.name)
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Skill {req.name!r} already exists. Use PUT to update."
        )

    path = store.write_extension(req.name, req.content)
    info = store.get_extension(req.name)
    return {"path": str(path), "info": info.model_dump(mode="json") if info else None}


@router.put("/local/{name}")
def update_skill(name: str, req: SkillWriteRequest) -> dict:
    """Update an existing skill's SKILL.md content."""
    store = get_central_extension_store()
    if not store.get_extension(name):
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found")
    if not req.content.strip():
        raise HTTPException(status_code=422, detail="Skill content must not be empty")

    path = store.write_extension(name, req.content)
    info = store.get_extension(name)
    return {"path": str(path), "info": info.model_dump(mode="json") if info else None}


@router.delete("/local/{name}")
def delete_skill(name: str) -> dict:
    """Delete an installed skill and its entire directory."""
    store = get_central_extension_store()
    deleted = store.delete_extension(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found")
    return {"deleted": name}


@router.get("/sources")
def list_skill_sources() -> list[dict]:
    """List available agent interfaces and their skill counts."""
    sources = []
    for src, store in get_agent_extension_stores().items():
        extensions = store.get_cached()
        sources.append(
            {
                "key": src.value,
                "label": src.value.replace("_", " ").title(),
                "skill_count": len(extensions),
                "skills_dir": str(store.extensions_dir),
            }
        )
    return sources


@router.post("/sync/{name}")
def sync_skill_to_targets(name: str, req: SkillSyncRequest) -> dict:
    """Sync a central skill to one or more agent interfaces.

    Copies the skill directory from the central store to each target agent store.

    Args:
        name: Skill name to sync.
        req: Target agent interface keys.

    Returns:
        Dict with sync results per target.
    """
    central = get_central_extension_store()
    if not central.get_extension(name):
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found in central store")

    agent_stores = get_agent_extension_stores()
    results = {}
    for target_key in req.targets:
        target_store = _find_store_by_key(agent_stores, target_key)
        if not target_store:
            results[target_key] = {"synced": False, "error": f"Unknown target: {target_key}"}
            continue
        try:
            copied = target_store.import_extension_from(central, name, overwrite=True)
            skill_path = str(target_store.extension_path(name))
            results[target_key] = {"synced": bool(copied), "path": skill_path}

            # Update the central store's source metadata to record
            # that this skill now also exists in the target agent store
            if copied:
                central._inject_source_metadata(name, target_store)
                central.invalidate_cache()
        except Exception as exc:
            results[target_key] = {"synced": False, "error": str(exc)}

    updated_skill = central.get_extension(name)
    return {
        "name": name,
        "results": results,
        "skill": updated_skill.model_dump(mode="json") if updated_skill else None,
    }
