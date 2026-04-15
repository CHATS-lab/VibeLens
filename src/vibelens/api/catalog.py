"""Catalog browsing endpoints."""

import re

import httpx
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query

from vibelens.deps import get_personalization_store
from vibelens.models.extension import ExtensionItem
from vibelens.models.personalization.recommendation import UserProfile
from vibelens.schemas.catalog import (
    CatalogInstallRequest,
    CatalogInstallResponse,
    CatalogListResponse,
    CatalogMetaResponse,
)
from vibelens.services.catalog.install import (
    install_catalog_item,
    install_from_source_url,
)
from vibelens.services.recommendation.catalog import CatalogSnapshot, load_catalog
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])

_content_cache: TTLCache = TTLCache(maxsize=64, ttl=3600)

_GITHUB_TREE_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<ref>[^/]+)/(?P<path>.+)"
)

CONTENT_FETCH_TIMEOUT = 15


def _get_catalog() -> CatalogSnapshot:
    """Load catalog or raise 404.

    Returns:
        CatalogSnapshot with available catalog data.

    Raises:
        HTTPException: 404 if no catalog is available.
    """
    catalog = load_catalog()
    if not catalog:
        raise HTTPException(status_code=404, detail="No catalog available")
    return catalog


def _filter_items(
    items: list[ExtensionItem],
    search: str | None,
    item_type: str | None,
    category: str | None,
    platform: str | None,
) -> list[ExtensionItem]:
    """Apply search and filter criteria to items.

    Args:
        items: Full list of catalog items.
        search: Keyword to match against name, description, and tags.
        item_type: Item type value to filter by.
        category: Category string to filter by.
        platform: Platform string to filter by.

    Returns:
        Filtered list of catalog items.
    """
    result = items

    if search:
        q = search.lower()
        result = [
            i
            for i in result
            if q in i.name.lower()
            or q in i.description.lower()
            or any(q in t.lower() for t in i.tags)
        ]

    if item_type:
        result = [i for i in result if i.extension_type.value == item_type]

    if category:
        result = [i for i in result if i.category == category]

    if platform:
        result = [i for i in result if platform in i.platforms]

    return result


def _score_relevance(item: ExtensionItem, keywords: list[str]) -> float:
    """Score item relevance against user profile keywords.

    Args:
        item: Catalog item to score.
        keywords: Lowercased search keywords from user profile.

    Returns:
        Relevance score from 0.0 to 1.0.
    """
    if not keywords:
        return 0.0
    text = f"{item.name} {item.description} {' '.join(item.tags)} {item.category}".lower()
    hits = sum(1 for kw in keywords if kw in text)
    return hits / len(keywords)


def _load_latest_profile() -> UserProfile | None:
    """Load user profile from the most recent recommendation analysis.

    Returns:
        UserProfile if a recommendation analysis exists, else None.
    """
    store = get_personalization_store()
    analyses = store.list_analyses()
    if not analyses:
        return None
    result = store.load(analyses[0].analysis_id)
    if not result:
        return None
    return result.user_profile


def _sort_items(
    items: list[ExtensionItem], sort: str, profile: UserProfile | None = None
) -> list[ExtensionItem]:
    """Sort items by the given criterion.

    Args:
        items: Items to sort.
        sort: Sort key - quality, name, popularity, recent, or relevance.
        profile: Optional user profile for relevance sorting.

    Returns:
        Sorted list of catalog items.
    """
    if sort == "name":
        return sorted(items, key=lambda i: i.name.lower())
    if sort == "popularity":
        return sorted(items, key=lambda i: i.popularity, reverse=True)
    if sort == "recent":
        return sorted(items, key=lambda i: i.updated_at, reverse=True)
    if sort == "relevance" and profile and profile.search_keywords:
        keywords = [kw.lower() for kw in profile.search_keywords]
        return sorted(
            items,
            key=lambda i: (_score_relevance(i, keywords), i.quality_score),
            reverse=True,
        )
    return sorted(items, key=lambda i: i.quality_score, reverse=True)


@router.get("")
async def list_catalog(
    search: str | None = Query(default=None, description="Search name, description, tags"),
    item_type: str | None = Query(default=None, description="Filter by item type"),
    category: str | None = Query(default=None, description="Filter by category"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    sort: str = Query(
        default="quality", description="Sort: quality, name, popularity, recent, relevance"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=200, description="Items per page"),
) -> CatalogListResponse:
    """List catalog items with search, filters, and pagination.

    Args:
        search: Keyword to match against name, description, and tags.
        item_type: Filter by item type value.
        category: Filter by category string.
        platform: Filter by platform string.
        sort: Sort criterion — quality (default), name, popularity, recent, or relevance.
        page: Page number, 1-indexed.
        per_page: Number of items per page (1-200).

    Returns:
        Paginated catalog listing with total count.
    """
    catalog = _get_catalog()
    filtered = _filter_items(catalog.items, search, item_type, category, platform)
    profile = _load_latest_profile() if sort == "relevance" else None
    sorted_items = _sort_items(filtered, sort, profile=profile)

    total = len(sorted_items)
    start = (page - 1) * per_page
    page_items = sorted_items[start : start + per_page]

    item_dicts = []
    for item in page_items:
        d = item.model_dump(mode="json")
        d.pop("install_content", None)
        item_dicts.append(d)

    return CatalogListResponse(items=item_dicts, total=total, page=page, per_page=per_page)


@router.get("/meta")
async def catalog_meta() -> CatalogMetaResponse:
    """Return catalog metadata for frontend filter and sort options.

    Returns:
        Categories list and profile availability flag.
    """
    catalog = _get_catalog()
    categories = sorted({item.category for item in catalog.items})
    profile = _load_latest_profile()
    has_profile = bool(profile and profile.search_keywords)
    return CatalogMetaResponse(categories=categories, has_profile=has_profile)


@router.get("/{item_id:path}/content")
async def get_catalog_item_content(item_id: str) -> dict:
    """Fetch displayable content for a catalog item.

    For file-based items with install_content: returns it directly.
    For repo items: fetches README from GitHub.
    For featured skills: fetches SKILL.md from GitHub tree URL.

    Args:
        item_id: Unique catalog item identifier.

    Returns:
        Dict with item_id, content (str or null), and content_type.
    """
    if item_id in _content_cache:
        return _content_cache[item_id]

    catalog = _get_catalog()
    item = catalog.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

    result = await _resolve_content(item)
    _content_cache[item_id] = result
    return result


async def _resolve_content(item: ExtensionItem) -> dict:
    """Resolve displayable content for a catalog item.

    Args:
        item: Catalog item to resolve content for.

    Returns:
        Dict with item_id, content, and content_type.
    """
    if item.install_content:
        return {
            "item_id": item.extension_id,
            "content": item.install_content,
            "content_type": "install_content",
        }

    if item.extension_type.value == "repo" and item.repo_full_name:
        owner, repo = item.repo_full_name.split("/", 1)
        readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
        content = await _fetch_url_content(readme_url)
        if content:
            return {
                "item_id": item.extension_id,
                "content": content,
                "content_type": "readme",
            }
        return {
            "item_id": item.extension_id,
            "content": None,
            "content_type": None,
            "error": "Failed to fetch README from GitHub",
        }

    match = _GITHUB_TREE_RE.match(item.source_url)
    if match:
        owner = match.group("owner")
        repo = match.group("repo")
        ref = match.group("ref")
        path = match.group("path")
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}/SKILL.md"
        content = await _fetch_url_content(raw_url)
        if content:
            return {
                "item_id": item.extension_id,
                "content": content,
                "content_type": "skill_md",
            }
        return {
            "item_id": item.extension_id,
            "content": None,
            "content_type": None,
            "error": "Failed to fetch SKILL.md from GitHub",
        }

    return {"item_id": item.extension_id, "content": None, "content_type": None}


async def _fetch_url_content(url: str) -> str | None:
    """Fetch text content from a URL.

    Args:
        url: URL to fetch.

    Returns:
        Response text or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=CONTENT_FETCH_TIMEOUT) as http_client:
            resp = await http_client.get(url, follow_redirects=True)
            if resp.status_code < 400:
                return resp.text
    except (httpx.HTTPError, httpx.TimeoutException):
        pass
    logger.warning("Failed to fetch content from %s", url)
    return None


@router.post("/{item_id:path}/install")
async def install_item(item_id: str, body: CatalogInstallRequest) -> CatalogInstallResponse:
    """Install a catalog item to the target agent platform.

    Args:
        item_id: Unique catalog item identifier.
        body: Install request with target platform and overwrite flag.

    Returns:
        Install response with success status and installed path.

    Raises:
        HTTPException: 404 if item not found, 400 if not installable,
            409 if file exists and overwrite is False.
    """
    catalog = _get_catalog()
    item = catalog.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    try:
        if item.install_content:
            installed_path = install_catalog_item(
                item=item, target_platform=body.target_platform, overwrite=body.overwrite
            )
        elif item.extension_type.value in ("hook", "repo"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Item {item_id} requires install_content"
                    f" for {item.extension_type.value} type"
                ),
            )
        else:
            installed_path = install_from_source_url(
                item=item, target_platform=body.target_platform, overwrite=body.overwrite
            )
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail="File already exists. Set overwrite=true to replace.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CatalogInstallResponse(
        success=True,
        installed_path=str(installed_path),
        message=f"Installed {item.name} to {installed_path}",
    )


@router.get("/{item_id:path}")
async def get_catalog_item(item_id: str) -> dict:
    """Get full catalog item by ID, including install_content.

    Args:
        item_id: Unique catalog item identifier.

    Returns:
        Full item dict including install_content.

    Raises:
        HTTPException: 404 if item is not found.
    """
    catalog = _get_catalog()
    item = catalog.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item.model_dump(mode="json")
