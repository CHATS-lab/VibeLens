"""Extension catalog browsing and install logic."""

from pathlib import Path

from cachetools import TTLCache

from vibelens.deps import get_personalization_store
from vibelens.models.extension import ExtensionItem
from vibelens.models.personalization.recommendation import UserProfile
from vibelens.services.extensions.catalog_resolver import (
    install_catalog_item,
    install_from_source_url,
)
from vibelens.storage.extension.catalog import CatalogSnapshot, load_catalog
from vibelens.utils.github import github_blob_to_raw_url, github_tree_to_raw_url
from vibelens.utils.http import async_fetch_text
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

_content_cache: TTLCache = TTLCache(maxsize=64, ttl=3600)


def list_extensions(
    search: str | None,
    extension_type: str | None,
    category: str | None,
    platform: str | None,
    sort: str,
    page: int,
    per_page: int,
) -> tuple[list[dict], int]:
    """Filter, sort, paginate catalog items.

    Args:
        search: Keyword to match against name, description, and tags.
        extension_type: Filter by extension type value.
        category: Filter by category string.
        platform: Filter by platform string.
        sort: Sort criterion -- quality, name, popularity, recent, or relevance.
        page: Page number, 1-indexed.
        per_page: Number of items per page.

    Returns:
        Tuple of (item_dicts, total_count).

    Raises:
        ValueError: If no catalog is available.
    """
    catalog = _get_catalog()
    filtered = _filter_items(catalog.items, search, extension_type, category, platform)
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

    return item_dicts, total


def get_extension_metadata() -> tuple[list[str], bool]:
    """Return catalog metadata for frontend filter and sort options.

    Returns:
        Tuple of (sorted_categories, has_profile).

    Raises:
        ValueError: If no catalog is available.
    """
    catalog = _get_catalog()
    categories = sorted({item.category for item in catalog.items})
    profile = _load_latest_profile()
    has_profile = bool(profile and profile.search_keywords)
    return categories, has_profile


def get_extension_by_id(item_id: str) -> ExtensionItem | None:
    """Look up a single catalog item by ID.

    Args:
        item_id: Unique extension item identifier.

    Returns:
        ExtensionItem or None if catalog missing or item not found.
    """
    catalog = load_catalog()
    if not catalog:
        return None
    return catalog.get_item(item_id)


async def resolve_extension_content(item_id: str) -> dict:
    """Resolve displayable content for an extension item.

    Checks in-memory cache first, then fetches from GitHub if needed.

    Args:
        item_id: Unique extension item identifier.

    Returns:
        Dict with item_id, content, and content_type.

    Raises:
        ValueError: If no catalog available or item not found.
    """
    if item_id in _content_cache:
        return _content_cache[item_id]

    catalog = _get_catalog()
    item = catalog.get_item(item_id)
    if not item:
        raise ValueError(f"Item {item_id} not found")

    result = await _resolve_content(item)
    _content_cache[item_id] = result
    return result


def install_extension(item_id: str, target_platform: str, overwrite: bool) -> tuple[str, Path]:
    """Install an extension item to the target agent platform.

    Args:
        item_id: Unique extension item identifier.
        target_platform: Target agent platform for installation.
        overwrite: Whether to overwrite existing files.

    Returns:
        Tuple of (item_name, installed_path).

    Raises:
        KeyError: If item not found in catalog.
        ValueError: If item is not installable.
        FileExistsError: If file exists and overwrite is False.
    """
    catalog = load_catalog()
    if not catalog:
        raise KeyError(f"Item {item_id} not found")
    item = catalog.get_item(item_id)
    if not item:
        raise KeyError(f"Item {item_id} not found")

    if item.install_content:
        installed_path = install_catalog_item(
            item=item, target_platform=target_platform, overwrite=overwrite
        )
    elif item.extension_type.value in ("hook", "repo"):
        raise ValueError(
            f"Item {item_id} requires install_content for {item.extension_type.value} type"
        )
    else:
        installed_path = install_from_source_url(
            item=item, target_platform=target_platform, overwrite=overwrite
        )

    return item.name, installed_path


def _get_catalog() -> CatalogSnapshot:
    """Load catalog or raise ValueError.

    Returns:
        CatalogSnapshot with available catalog data.

    Raises:
        ValueError: If no catalog is available.
    """
    catalog = load_catalog()
    if not catalog:
        raise ValueError("No catalog available")
    return catalog


def _filter_items(
    items: list[ExtensionItem],
    search: str | None,
    extension_type: str | None,
    category: str | None,
    platform: str | None,
) -> list[ExtensionItem]:
    """Apply search and filter criteria to items.

    Args:
        items: Full list of catalog items.
        search: Keyword to match against name, description, and tags.
        extension_type: Extension type value to filter by.
        category: Category string to filter by.
        platform: Platform string to filter by.

    Returns:
        Filtered list of items.
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

    if extension_type:
        result = [i for i in result if i.extension_type.value == extension_type]

    if category:
        result = [i for i in result if i.category == category]

    if platform:
        result = [i for i in result if platform in i.platforms]

    return result


def _score_relevance(item: ExtensionItem, keywords: list[str]) -> float:
    """Score item relevance against user profile keywords.

    Args:
        item: Extension item to score.
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
    result = store.load(analyses[0].id)
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
        Sorted list of items.
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


async def _resolve_content(item: ExtensionItem) -> dict:
    """Resolve displayable content for an extension item.

    Args:
        item: Extension item to resolve content for.

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
        content = await async_fetch_text(readme_url)
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

    raw_url = github_tree_to_raw_url(tree_url=item.source_url, filename="SKILL.md")
    if raw_url:
        content = await async_fetch_text(raw_url)
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

    blob_raw_url = github_blob_to_raw_url(blob_url=item.source_url)
    if blob_raw_url:
        content = await async_fetch_text(blob_raw_url)
        if content:
            return {
                "item_id": item.extension_id,
                "content": content,
                "content_type": "markdown",
            }
        return {
            "item_id": item.extension_id,
            "content": None,
            "content_type": None,
            "error": "Failed to fetch content from GitHub",
        }

    return {"item_id": item.extension_id, "content": None, "content_type": None}
