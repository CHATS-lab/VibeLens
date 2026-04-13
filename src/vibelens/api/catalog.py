"""Catalog browsing endpoints."""

from fastapi import APIRouter, HTTPException, Query

from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.schemas.catalog import (
    CatalogInstallRequest,
    CatalogInstallResponse,
    CatalogListResponse,
)
from vibelens.services.catalog.install import install_catalog_item
from vibelens.services.recommendation.catalog import CatalogSnapshot, load_catalog
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])


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
    items: list[CatalogItem],
    search: str | None,
    item_type: str | None,
    category: str | None,
    platform: str | None,
) -> list[CatalogItem]:
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
        result = [i for i in result if i.item_type.value == item_type]

    if category:
        result = [i for i in result if i.category == category]

    if platform:
        result = [i for i in result if platform in i.platforms]

    return result


def _sort_items(items: list[CatalogItem], sort: str) -> list[CatalogItem]:
    """Sort items by the given criterion.

    Args:
        items: Items to sort.
        sort: Sort key — "name" for alphabetical, anything else for quality descending.

    Returns:
        Sorted list of catalog items.
    """
    if sort == "name":
        return sorted(items, key=lambda i: i.name.lower())
    return sorted(items, key=lambda i: i.quality_score, reverse=True)


@router.get("")
async def list_catalog(
    search: str | None = Query(default=None, description="Search name, description, tags"),
    item_type: str | None = Query(default=None, description="Filter by item type"),
    category: str | None = Query(default=None, description="Filter by category"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    sort: str = Query(default="quality", description="Sort: quality or name"),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=200, description="Items per page"),
) -> CatalogListResponse:
    """List catalog items with search, filters, and pagination.

    Args:
        search: Keyword to match against name, description, and tags.
        item_type: Filter by item type value.
        category: Filter by category string.
        platform: Filter by platform string.
        sort: Sort criterion — "quality" (default) or "name".
        page: Page number, 1-indexed.
        per_page: Number of items per page (1-200).

    Returns:
        Paginated catalog listing with total count.
    """
    catalog = _get_catalog()
    filtered = _filter_items(catalog.items, search, item_type, category, platform)
    sorted_items = _sort_items(filtered, sort)

    total = len(sorted_items)
    start = (page - 1) * per_page
    page_items = sorted_items[start : start + per_page]

    item_dicts = []
    for item in page_items:
        d = item.model_dump(mode="json")
        d.pop("install_content", None)
        item_dicts.append(d)

    return CatalogListResponse(items=item_dicts, total=total, page=page, per_page=per_page)


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
    if not item.install_content:
        raise HTTPException(status_code=400, detail=f"Item {item_id} has no installable content")
    try:
        installed_path = install_catalog_item(
            item=item,
            target_platform=body.target_platform,
            overwrite=body.overwrite,
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
