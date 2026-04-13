"""GitHub API enrichment for catalog items."""

import asyncio
import math
import os
import re
import subprocess

import httpx

from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"
ENRICHMENT_CONCURRENCY = 10
ENRICHMENT_TIMEOUT = 10

_GITHUB_REPO_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)"
)


def _extract_repo_full_name(source_url: str) -> str:
    """Extract owner/repo from a GitHub URL.

    Returns empty string if the URL is org-only or invalid.

    Args:
        source_url: GitHub URL to parse.

    Returns:
        'owner/repo' string or empty string.
    """
    if not source_url:
        return ""
    match = _GITHUB_REPO_RE.match(source_url)
    if not match:
        return ""
    owner = match.group("owner")
    repo = match.group("repo")
    if repo in ("tree", "blob", "commit", "issues", "pulls"):
        return ""
    return f"{owner}/{repo}"


def _construct_source_url(
    item: CatalogItem,
    path_map: dict[str, str],
    bwc_repo: str | None = None,
    cct_repo: str | None = None,
) -> str:
    """Construct a GitHub source_url for an item.

    Uses the item's existing source_url if present, otherwise constructs one
    from the path_map and parent repo arguments.

    Args:
        item: Catalog item to resolve URL for.
        path_map: Mapping of item_id to relative file path within source repo.
        bwc_repo: GitHub owner/repo for buildwithclaude.
        cct_repo: GitHub owner/repo for claude-code-templates.

    Returns:
        GitHub URL string, or empty string if unresolvable.
    """
    if item.source_url:
        return item.source_url

    rel_path = path_map.get(item.item_id, "")
    if not rel_path:
        return ""

    prefix = item.item_id.split(":")[0]
    if prefix == "bwc" and bwc_repo:
        return f"https://github.com/{bwc_repo}/blob/main/{rel_path}"
    if prefix == "cct" and cct_repo:
        return f"https://github.com/{cct_repo}/blob/main/{rel_path}"

    return ""


def _get_github_headers() -> dict[str, str]:
    """Build GitHub API request headers with optional auth token.

    Returns:
        Headers dict with Accept and optional Authorization.
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    if not token:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True
        )
        token = result.stdout.strip()
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


_mcp_owner_cache: dict[str, str] = {}


async def _resolve_mcp_repo(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    owner: str,
    slug: str,
) -> str:
    """Resolve an MCP server slug to a full repo name using three-tier strategy.

    1. Direct: Try repos/{owner}/{slug}
    2. Search: Try search/repositories?q={slug}+in:name+user:{owner}
    3. Monorepo: Check if {owner}/servers exists (cached per owner)

    Args:
        client: Async HTTP client.
        sem: Concurrency semaphore.
        owner: GitHub org or user name.
        slug: MCP server slug to match.

    Returns:
        'owner/repo' string or empty string.
    """
    async with sem:
        resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{slug}")
        if resp.status_code == 200:
            return resp.json()["full_name"]

        resp = await client.get(
            f"{GITHUB_API_BASE}/search/repositories",
            params={"q": f"{slug} in:name user:{owner}", "per_page": "3"},
        )
        if resp.status_code == 200:
            search_items = resp.json().get("items", [])
            if search_items:
                return search_items[0]["full_name"]

        if owner in _mcp_owner_cache:
            return _mcp_owner_cache[owner]

        resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/servers")
        if resp.status_code == 200:
            _mcp_owner_cache[owner] = f"{owner}/servers"
            return f"{owner}/servers"

        _mcp_owner_cache[owner] = ""
        return ""


async def _fetch_repo_metadata(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    repo_full_name: str,
) -> dict | None:
    """Fetch metadata for a single GitHub repo.

    Args:
        client: Async HTTP client.
        sem: Concurrency semaphore.
        repo_full_name: 'owner/repo' string.

    Returns:
        Dict with stars, forks, language, license_name, updated_at, or None on failure.
    """
    async with sem:
        resp = await client.get(f"{GITHUB_API_BASE}/repos/{repo_full_name}")
        if resp.status_code != 200:
            return None
        data = resp.json()
        license_obj = data.get("license") or {}
        return {
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "language": data.get("language") or "",
            "license_name": license_obj.get("spdx_id") or "",
            "updated_at": data.get("pushed_at") or "",
        }


async def _enrich_async(
    items: list[CatalogItem],
    path_map: dict[str, str],
    bwc_repo: str | None = None,
    cct_repo: str | None = None,
) -> list[CatalogItem]:
    """Async enrichment pipeline.

    Args:
        items: Catalog items to enrich.
        path_map: Item ID to relative file path mapping.
        bwc_repo: GitHub owner/repo for buildwithclaude.
        cct_repo: GitHub owner/repo for claude-code-templates.

    Returns:
        Enriched items list.
    """
    _mcp_owner_cache.clear()
    headers = _get_github_headers()
    sem = asyncio.Semaphore(ENRICHMENT_CONCURRENCY)

    async with httpx.AsyncClient(
        headers=headers, timeout=ENRICHMENT_TIMEOUT
    ) as client:
        # Phase 1: Resolve URLs and repo_full_name
        for item in items:
            url = _construct_source_url(
                item, path_map, bwc_repo=bwc_repo, cct_repo=cct_repo
            )
            if url:
                item.source_url = url

            repo_name = _extract_repo_full_name(item.source_url)
            if repo_name:
                item.repo_full_name = repo_name

        # Phase 2: Resolve MCP items with org-only URLs
        mcp_to_resolve: list[tuple[int, str, str]] = []
        for idx, item in enumerate(items):
            if item.source_url and not item.repo_full_name:
                path = item.source_url.replace("https://github.com/", "")
                if "/" not in path:
                    slug = item.item_id.split(":")[-1]
                    mcp_to_resolve.append((idx, path, slug))

        if mcp_to_resolve:
            print(f"  Resolving {len(mcp_to_resolve)} MCP org-only URLs...")
            tasks = [
                _resolve_mcp_repo(client, sem, owner, slug)
                for _, owner, slug in mcp_to_resolve
            ]
            results = await asyncio.gather(*tasks)
            resolved = 0
            for (idx, _owner, _slug), repo_name in zip(mcp_to_resolve, results, strict=True):
                if repo_name:
                    items[idx].repo_full_name = repo_name
                    items[idx].source_url = f"https://github.com/{repo_name}"
                    resolved += 1
            print(f"  Resolved {resolved}/{len(mcp_to_resolve)} MCP URLs")

        # Phase 3: Fetch metadata for unique repos
        repo_to_indices: dict[str, list[int]] = {}
        for idx, item in enumerate(items):
            if item.repo_full_name:
                repo_to_indices.setdefault(item.repo_full_name, []).append(idx)

        unique_repos = list(repo_to_indices.keys())
        total_repos = len(unique_repos)
        print(f"  Fetching metadata for {total_repos} unique repos...")

        enriched_count = 0
        fetched_count = 0

        async def _fetch_and_apply(repo_name: str) -> None:
            nonlocal enriched_count, fetched_count
            metadata = await _fetch_repo_metadata(client, sem, repo_name)
            fetched_count += 1
            if fetched_count % 50 == 0 or fetched_count == total_repos:
                print(f"  Enriching: {fetched_count}/{total_repos} repos...")
            if not metadata:
                return
            for idx in repo_to_indices[repo_name]:
                items[idx].stars = metadata["stars"]
                items[idx].forks = metadata["forks"]
                items[idx].language = metadata["language"]
                items[idx].license_name = metadata["license_name"]
                if not items[idx].updated_at and metadata["updated_at"]:
                    items[idx].updated_at = metadata["updated_at"]
            enriched_count += 1

        await asyncio.gather(*[_fetch_and_apply(repo) for repo in unique_repos])

        print(f"  Enriched from {enriched_count}/{total_repos} repos")

    # Phase 4: Recompute popularity from stars
    max_stars = max((item.stars for item in items if item.stars > 0), default=1)
    max_stars = max(max_stars, 1)
    for item in items:
        if item.stars > 0:
            item.popularity = round(
                math.log(1 + item.stars) / math.log(1 + max_stars), 3
            )

    return items


def enrich_from_github(
    items: list[CatalogItem],
    path_map: dict[str, str],
    bwc_repo: str | None = None,
    cct_repo: str | None = None,
) -> list[CatalogItem]:
    """Enrich catalog items with GitHub metadata.

    Resolves source_urls and fetches stars, forks, language, license from
    the GitHub REST API. Requires GITHUB_TOKEN env var or gh CLI auth.

    Args:
        items: Scored catalog items.
        path_map: Mapping of item_id to relative file path within source repo.
        bwc_repo: GitHub owner/repo for buildwithclaude source.
        cct_repo: GitHub owner/repo for claude-code-templates source.

    Returns:
        Items with enriched metadata.
    """
    print("Enriching from GitHub...")
    return asyncio.run(
        _enrich_async(items, path_map, bwc_repo=bwc_repo, cct_repo=cct_repo)
    )
