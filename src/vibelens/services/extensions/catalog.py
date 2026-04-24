"""Extension catalog browsing and install logic."""

from pathlib import Path

from cachetools import TTLCache

from vibelens.deps import get_recommendation_store
from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import AgentExtensionItem
from vibelens.models.personalization.recommendation import UserProfile
from vibelens.services.extensions.catalog_resolver import install_catalog_item
from vibelens.services.extensions.search import (
    ExtensionQuery,
    SortMode,
    coerce_legacy_sort,
    rank_catalog,
)
from vibelens.storage.extension.catalog import CatalogSnapshot, load_catalog
from vibelens.utils.github import (
    GITHUB_REPO_RE,
    fetch_github_tree_file,
    github_blob_to_raw_url,
    github_tree_file_to_raw_url,
    github_tree_to_raw_url,
    is_github_single_file_tree,
    list_github_tree,
    parse_github_url,
)
from vibelens.utils.http import async_fetch_text
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CATALOG_TREE_MAX_ENTRIES = 500
CATALOG_FILE_MAX_BYTES = 200_000
_content_cache: TTLCache = TTLCache(maxsize=64, ttl=3600)
_tree_cache: TTLCache = TTLCache(maxsize=128, ttl=3600)
_file_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)


def list_extensions(
    search_text: str | None,
    extension_type: str | None,
    sort: str,
    page: int,
    per_page: int,
) -> tuple[list[dict], int]:
    """Rank, filter, paginate catalog items via the unified search module.

    Args:
        search_text: User-typed query string. Empty or None triggers browse mode.
        extension_type: Filter by extension type value (applied before scoring).
        sort: Sort criterion -- default, personalized, quality, name, recent.
            Legacy values (popularity, relevance) are coerced.
        page: Page number, 1-indexed.
        per_page: Number of items per page.

    Returns:
        Tuple of (item_dicts, total_count).

    Raises:
        ValueError: If no catalog is available.
    """
    catalog = _get_catalog()

    sort_mode = coerce_legacy_sort(sort)
    profile = _load_latest_profile()
    if sort_mode is SortMode.PERSONALIZED and (not profile or not profile.search_keywords):
        logger.info("personalized sort requested without profile; falling back to default")
        sort_mode = SortMode.DEFAULT

    type_filter = _coerce_extension_type(extension_type)

    extension_query = ExtensionQuery(
        search_text=search_text or "",
        profile=profile,
        sort=sort_mode,
        extension_type=type_filter,
    )
    ranked = rank_catalog(extension_query)

    total = len(ranked)
    start = (page - 1) * per_page
    page_scored = ranked[start : start + per_page]

    items: list[dict] = []
    for scored in page_scored:
        item = catalog.get_item(scored.extension_id)
        if item is not None:
            items.append(item.model_dump(mode="json"))
    return items, total


def get_extension_metadata() -> tuple[list[str], bool]:
    """Return catalog metadata for frontend filter and sort options.

    Returns:
        Tuple of (sorted_topics, has_profile).

    Raises:
        ValueError: If no catalog is available.
    """
    catalog = _get_catalog()
    topics = sorted({t for item in catalog.items for t in item.topics})
    profile = _load_latest_profile()
    has_profile = bool(profile and profile.search_keywords)
    return topics, has_profile


def get_extension_by_id(item_id: str) -> AgentExtensionItem | None:
    """Look up a single catalog item by ID, hydrating detail fields.

    Returns the full record when offsets succeed; falls back to the summary
    when hydration fails. Returns None when the item is unknown.

    Args:
        item_id: Unique extension item identifier.

    Returns:
        AgentExtensionItem or None.
    """
    catalog = load_catalog()
    if not catalog:
        return None
    full = catalog.get_full(item_id)
    if full is not None:
        return full
    summary = catalog.get_item(item_id)
    if summary is not None:
        logger.warning("returning summary for %s; detail hydration failed", item_id)
    return summary


async def resolve_extension_content(item_id: str) -> dict:
    """Resolve displayable content for an extension item.

    Always fetches from GitHub via source_url + path_in_repo (the catalog
    no longer ships embedded install_content).

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
    item = catalog.get_full(item_id) or catalog.get_item(item_id)
    if not item:
        raise ValueError(f"Item {item_id} not found")

    result = await _resolve_content(item)
    if result.get("content") is not None:
        _content_cache[item_id] = result
    return result


def list_extension_tree(item_id: str) -> dict:
    """List the remote file tree for a catalog item via the GitHub Contents API.

    Returns:
        Dict with ``name``, ``root`` (source_url), ``entries`` (list of
        ``{path, kind, size}``), and ``truncated`` flag. Empty entries list
        when the item has no parseable GitHub source URL.

    Raises:
        ValueError: If the catalog is unavailable or the item is unknown.
    """
    if item_id in _tree_cache:
        return _tree_cache[item_id]

    catalog = _get_catalog()
    item = catalog.get_full(item_id) or catalog.get_item(item_id)
    if not item:
        raise ValueError(f"Item {item_id} not found")

    source_url = item.source_url or ""
    entries, truncated = list_github_tree(
        source_url=source_url, max_entries=CATALOG_TREE_MAX_ENTRIES
    )
    result = {"name": item.name, "root": source_url, "entries": entries, "truncated": truncated}
    if entries:
        _tree_cache[item_id] = result
    return result


def fetch_extension_file(item_id: str, relative: str) -> dict:
    """Fetch one file from a catalog item's remote tree.

    Args:
        item_id: Catalog item id.
        relative: Posix-style path relative to the item's source_url root.
            For single-file sources, pass the file's basename or an empty
            string.

    Returns:
        Dict with ``path``, ``content``, and ``truncated``.

    Raises:
        ValueError: If the catalog is unavailable, the item is unknown, or
            the file is missing.
    """
    cache_key = (item_id, relative)
    if cache_key in _file_cache:
        return _file_cache[cache_key]

    catalog = _get_catalog()
    item = catalog.get_full(item_id) or catalog.get_item(item_id)
    if not item:
        raise ValueError(f"Item {item_id} not found")

    if not item.source_url:
        raise ValueError(f"Item {item_id} has no source URL")

    lookup = relative
    if is_github_single_file_tree(item.source_url):
        lookup = ""

    text = fetch_github_tree_file(source_url=item.source_url, relative=lookup)
    if text is None:
        raise ValueError(f"File {relative!r} not found for {item_id}")

    truncated = len(text.encode("utf-8")) > CATALOG_FILE_MAX_BYTES
    if truncated:
        text = text.encode("utf-8")[:CATALOG_FILE_MAX_BYTES].decode("utf-8", errors="ignore")

    display_path = relative or lookup or item.source_url.rsplit("/", 1)[-1]
    result = {"path": display_path, "content": text, "truncated": truncated}
    _file_cache[cache_key] = result
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
        NotImplementedError: For HOOK / MCP_SERVER / REPO items (not yet
            supported via the catalog this release).
        ValueError: If install dispatch fails.
        FileExistsError: If file exists and overwrite is False.
    """
    catalog = load_catalog()
    if not catalog:
        raise KeyError(f"Item {item_id} not found")
    item = catalog.get_full(item_id) or catalog.get_item(item_id)
    if not item:
        raise KeyError(f"Item {item_id} not found")

    if item.extension_type in (AgentExtensionType.HOOK, AgentExtensionType.MCP_SERVER):
        raise NotImplementedError(
            f"catalog {item.extension_type.value} install is not yet supported"
        )

    if item.extension_type == AgentExtensionType.REPO:
        raise NotImplementedError(
            "catalog REPO install is not yet supported (hub does not emit REPO items)"
        )

    installed_path = install_catalog_item(
        item=item, target_platform=target_platform, overwrite=overwrite
    )
    logger.info("Installed %s to %s", item_id, installed_path)
    return item.name, installed_path


def _get_catalog() -> CatalogSnapshot:
    """Load catalog or raise ValueError.

    Raises:
        ValueError: If no catalog is available.
    """
    catalog = load_catalog()
    if not catalog:
        raise ValueError("No catalog available")
    return catalog


def _load_latest_profile() -> UserProfile | None:
    """Load user profile from the most recent recommendation analysis."""
    store = get_recommendation_store()
    analyses = store.list_analyses()
    if not analyses:
        return None
    result = store.load(analyses[0].id)
    if not result:
        return None
    return result.user_profile


def _coerce_extension_type(raw: str | None) -> AgentExtensionType | None:
    """Coerce an HTTP-level string to :class:`AgentExtensionType`.

    Unknown values are logged and treated as "no filter" so a stale
    client can't break catalog browse with a 500.
    """
    if not raw:
        return None
    try:
        return AgentExtensionType(raw)
    except ValueError:
        logger.warning("unknown extension_type %r; ignoring filter", raw)
        return None


async def _resolve_content(item: AgentExtensionItem) -> dict:
    """Resolve displayable content for an extension item from GitHub.

    Branching on extension type and URL shape (first hit wins):

    * REPO -> repo README at HEAD.
    * PLUGIN -> README (if present), else ``.claude-plugin/plugin.json``.
    * Blob URL -> fetch the blob's raw content.
    * Tree URL pointing at a single file -> fetch that file directly.
    * Bare repo URL -> fetch README at HEAD.
    * Tree URL pointing at a directory -> fetch ``SKILL.md`` inside it.
    """
    if item.extension_type == AgentExtensionType.REPO and item.repo_full_name:
        owner, repo = item.repo_full_name.split("/", 1)
        readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
        content = await async_fetch_text(readme_url)
        if content:
            return {"item_id": item.extension_id, "content": content, "content_type": "readme"}
        return {
            "item_id": item.extension_id,
            "content": None,
            "content_type": None,
            "error": "Failed to fetch README from GitHub",
        }

    if item.extension_type == AgentExtensionType.PLUGIN:
        parsed = parse_github_url(item.source_url)
        if parsed:
            owner, repo, ref, base = parsed
            base_path = base.rstrip("/")
            for candidate in ("README.md", ".claude-plugin/plugin.json"):
                rel = f"{base_path}/{candidate}".strip("/") if base_path else candidate
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{rel}"
                content = await async_fetch_text(raw_url)
                if content:
                    kind = "readme" if candidate.endswith("README.md") else "markdown"
                    return {
                        "item_id": item.extension_id,
                        "content": content,
                        "content_type": kind,
                    }
        return {
            "item_id": item.extension_id,
            "content": None,
            "content_type": None,
            "error": "Failed to fetch README or plugin.json from GitHub",
        }

    blob_raw_url = github_blob_to_raw_url(blob_url=item.source_url)
    if blob_raw_url:
        content = await async_fetch_text(blob_raw_url)
        if content:
            return {"item_id": item.extension_id, "content": content, "content_type": "markdown"}
        return {
            "item_id": item.extension_id,
            "content": None,
            "content_type": None,
            "error": "Failed to fetch content from GitHub",
        }

    if is_github_single_file_tree(item.source_url):
        raw_url = github_tree_file_to_raw_url(tree_url=item.source_url)
        if raw_url:
            content = await async_fetch_text(raw_url)
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
                "error": "Failed to fetch file from GitHub",
            }

    # Bare-repo URL (e.g. "https://github.com/owner/repo"): fetch README at HEAD.
    if GITHUB_REPO_RE.match(item.source_url):
        parsed = parse_github_url(item.source_url)
        if parsed:
            owner, repo, _, _ = parsed
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
            return {"item_id": item.extension_id, "content": content, "content_type": "skill_md"}
        return {
            "item_id": item.extension_id,
            "content": None,
            "content_type": None,
            "error": "Failed to fetch SKILL.md from GitHub",
        }

    return {"item_id": item.extension_id, "content": None, "content_type": None}
