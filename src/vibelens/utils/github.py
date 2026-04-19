"""GitHub URL parsing and download utilities."""

import os
import re
from pathlib import Path

import httpx

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

GITHUB_TREE_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<ref>[^/]+)/(?P<path>.+)"
)

GITHUB_BLOB_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)"
)

# Bare repo URL ("https://github.com/owner/repo" with optional trailing slash
# or ``.git`` suffix). Many catalog plugin items use this shape instead of a
# tree URL; callers that want to walk the repo root need to handle it.
GITHUB_REPO_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/?#]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> tuple[str, str, str, str] | None:
    """Normalize any supported GitHub URL to ``(owner, repo, ref, path)``.

    Accepts:
        * ``https://github.com/{owner}/{repo}`` -> (owner, repo, ``"HEAD"``, ``""``)
        * ``https://github.com/{owner}/{repo}/tree/{ref}/{path}``
        * ``https://github.com/{owner}/{repo}/blob/{ref}/{path}``

    Returns None for any other shape.
    """
    tree = GITHUB_TREE_RE.match(url)
    if tree:
        return tree.group("owner"), tree.group("repo"), tree.group("ref"), tree.group("path")
    blob = GITHUB_BLOB_RE.match(url)
    if blob:
        return blob.group("owner"), blob.group("repo"), blob.group("ref"), blob.group("path")
    repo = GITHUB_REPO_RE.match(url)
    if repo:
        return repo.group("owner"), repo.group("repo"), "HEAD", ""
    return None

GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 30

# Known file extensions that indicate a single-file GitHub tree URL. Kept
# narrow on purpose: a mere dot in the last segment would false-positive on
# dotted directory names like ``v1.2.3`` or ``my.plugin``.
_SINGLE_FILE_TREE_EXTENSIONS = frozenset(
    {
        ".md",
        ".mdx",
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".sh",
        ".bash",
        ".zsh",
        ".txt",
    }
)


def is_github_single_file_tree(url: str) -> bool:
    """True when ``url`` is a tree URL pointing at a single known-file type.

    Matches only when the last path segment ends in a known source/text
    extension. This avoids false positives on dotted directory names (e.g.
    ``.../tree/main/plugins/my.plugin``).
    """
    match = GITHUB_TREE_RE.match(url)
    if not match:
        return False
    last_segment = match.group("path").rsplit("/", 1)[-1].lower()
    dot_index = last_segment.rfind(".")
    if dot_index <= 0:
        return False
    return last_segment[dot_index:] in _SINGLE_FILE_TREE_EXTENSIONS


def _github_headers() -> dict[str, str]:
    """Build HTTP headers for GitHub API requests.

    Uses GITHUB_TOKEN env var for authentication when available,
    raising the rate limit from 60 to 5000 requests/hour.

    Returns:
        Headers dict with Accept and optional Authorization.
    """
    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_tree_to_raw_url(tree_url: str, filename: str) -> str | None:
    """Convert a GitHub tree URL to a raw.githubusercontent.com URL for a file.

    Args:
        tree_url: GitHub tree URL like
            https://github.com/{owner}/{repo}/tree/{ref}/{path}
        filename: File name to append (e.g. "SKILL.md").

    Returns:
        Raw content URL, or None if tree_url doesn't match the pattern.
    """
    match = GITHUB_TREE_RE.match(tree_url)
    if not match:
        return None
    owner = match.group("owner")
    repo = match.group("repo")
    ref = match.group("ref")
    path = match.group("path")
    return f"{GITHUB_RAW_BASE}/{owner}/{repo}/{ref}/{path}/{filename}"


def github_blob_to_raw_url(blob_url: str) -> str | None:
    """Convert a GitHub blob URL to a raw.githubusercontent.com URL.

    Args:
        blob_url: GitHub blob URL like
            https://github.com/{owner}/{repo}/blob/{ref}/{path}

    Returns:
        Raw content URL, or None if blob_url doesn't match the pattern.
    """
    match = GITHUB_BLOB_RE.match(blob_url)
    if not match:
        return None
    owner = match.group("owner")
    repo = match.group("repo")
    ref = match.group("ref")
    path = match.group("path")
    return f"{GITHUB_RAW_BASE}/{owner}/{repo}/{ref}/{path}"


def github_tree_file_to_raw_url(tree_url: str) -> str | None:
    """Convert a GitHub tree URL that already points at a single file.

    Unlike :func:`github_tree_to_raw_url`, this does NOT append a filename -
    it treats the tree path itself as the file path.

    Args:
        tree_url: GitHub tree URL whose path points to a file
            (e.g. ``https://github.com/owner/repo/tree/main/agents/x.md``).

    Returns:
        Raw content URL, or None if the URL is not a tree URL.
    """
    match = GITHUB_TREE_RE.match(tree_url)
    if not match:
        return None
    return (
        f"{GITHUB_RAW_BASE}/{match.group('owner')}/{match.group('repo')}/"
        f"{match.group('ref')}/{match.group('path')}"
    )


def download_file(source_url: str, target_path: Path) -> bool:
    """Download a single file from a GitHub tree or blob URL.

    Converts ``source_url`` to a ``raw.githubusercontent.com`` URL and writes
    the content to ``target_path``. The parent directory is created if
    missing.

    Args:
        source_url: GitHub tree or blob URL pointing at a single file
            (e.g. ``https://github.com/owner/repo/tree/main/agents/x.md``).
        target_path: Local file path to write.

    Returns:
        True on success, False if the URL is unparseable or the request fails.
    """
    raw_url = github_blob_to_raw_url(blob_url=source_url) or github_tree_file_to_raw_url(
        tree_url=source_url
    )
    if raw_url is None:
        logger.warning("Cannot parse GitHub URL: %s", source_url)
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers=_github_headers(),
        ) as client:
            response = client.get(raw_url)
            response.raise_for_status()
            target_path.write_bytes(response.content)
        logger.debug("Downloaded %s to %s", raw_url, target_path)
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to download %s: %s", raw_url, exc)
        return False


def download_directory(source_url: str, target_dir: Path) -> bool:
    """Download a complete directory from any supported GitHub URL.

    Accepts tree URLs (``.../tree/<ref>/<path>``) and bare repo URLs
    (``https://github.com/<owner>/<repo>``); the latter walks from the
    default branch root. Fetches files recursively via the Contents API
    and writes them under ``target_dir`` preserving structure.

    Args:
        source_url: GitHub tree URL or bare repo URL.
        target_dir: Local directory to write files into.

    Returns:
        True if at least one file was downloaded successfully.
    """
    parsed = parse_github_url(source_url)
    if parsed is None:
        logger.warning("Cannot parse GitHub URL: %s", source_url)
        return False
    owner, repo, ref, path = parsed

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers=_github_headers(),
        ) as client:
            downloaded = _fetch_directory_recursive(client, owner, repo, ref, path, target_dir)
        logger.debug(
            "Downloaded %d files from %s/%s/%s to %s", downloaded, owner, repo, path, target_dir
        )
        return downloaded > 0
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            logger.error(
                "GitHub API rate limit exceeded. Set GITHUB_TOKEN env var to increase limit."
            )
        else:
            logger.error("GitHub API request failed: %s", exc)
        return False
    except httpx.HTTPError as exc:
        logger.error("GitHub API request failed: %s", exc)
        return False


def _fetch_directory_recursive(
    client: httpx.Client, owner: str, repo: str, ref: str, path: str, local_dir: Path
) -> int:
    """Recursively fetch all files from a GitHub directory via the Contents API.

    Args:
        client: Reusable httpx client with auth headers.
        owner: Repository owner.
        repo: Repository name.
        ref: Git ref (branch/tag).
        path: Directory path within the repo.
        local_dir: Local directory to write into.

    Returns:
        Number of files downloaded.
    """
    api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={ref}"

    response = client.get(api_url)
    response.raise_for_status()
    entries = response.json()

    if not isinstance(entries, list):
        logger.warning("Expected directory listing from %s, got single file", api_url)
        return 0

    downloaded = 0
    for entry in entries:
        entry_name = entry["name"]
        entry_type = entry["type"]

        if entry_type == "file":
            raw_url = entry.get("download_url", "")
            if not raw_url:
                raw_url = f"{GITHUB_RAW_BASE}/{owner}/{repo}/{ref}/{entry['path']}"
            downloaded += _fetch_file(client, raw_url, local_dir / entry_name)

        elif entry_type == "dir":
            sub_dir = local_dir / entry_name
            sub_dir.mkdir(parents=True, exist_ok=True)
            downloaded += _fetch_directory_recursive(
                client, owner, repo, ref, entry["path"], sub_dir
            )

    return downloaded


def _fetch_file(client: httpx.Client, url: str, local_path: Path) -> int:
    """Download a single file from a URL.

    Args:
        client: Reusable httpx client.
        url: Raw file download URL.
        local_path: Local file path to write.

    Returns:
        1 on success, 0 on failure.
    """
    try:
        response = client.get(url)
        response.raise_for_status()
        local_path.write_bytes(response.content)
        return 1
    except httpx.HTTPError as exc:
        logger.warning("Failed to download %s: %s", url, exc)
        return 0


def list_github_tree(source_url: str, max_entries: int = 500) -> tuple[list[dict], bool]:
    """Walk a GitHub tree URL via the Contents API and return file entries.

    Returns a flat list of ``{path, kind, size}`` dicts (paths relative to
    the source tree root) plus a ``truncated`` flag if the walk hit
    ``max_entries``. For a single-file ``tree/.../x.md`` URL, the sole entry
    is the file itself. Returns ``([], False)`` on any HTTP failure.
    """
    parsed = parse_github_url(source_url)
    if parsed is None:
        return [], False
    owner, repo, ref, path = parsed
    entries: list[dict] = []
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS, headers=_github_headers()
        ) as client:
            truncated = _collect_tree_entries(
                client=client,
                owner=owner,
                repo=repo,
                ref=ref,
                remote_path=path,
                rel_prefix="",
                out=entries,
                max_entries=max_entries,
            )
        entries.sort(key=lambda e: e["path"])
        return entries, truncated
    except httpx.HTTPError as exc:
        logger.error("Failed to list GitHub tree %s: %s", source_url, exc)
        return [], False


def fetch_github_tree_file(source_url: str, relative: str) -> str | None:
    """Fetch one file from a GitHub tree at ``source_url`` + ``relative`` path.

    Args:
        source_url: Tree URL rooting the lookup
            (e.g. ``https://github.com/owner/repo/tree/main/skills/foo``).
        relative: Relative path within the tree, posix-style.

    Returns:
        UTF-8 text content, or None on failure.
    """
    parsed = parse_github_url(source_url)
    if parsed is None:
        return None
    owner, repo, ref, path = parsed
    base_path = path.rstrip("/")
    remote_path = f"{base_path}/{relative}".strip("/") if relative else base_path
    raw_url = f"{GITHUB_RAW_BASE}/{owner}/{repo}/{ref}/{remote_path}".rstrip("/")
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS, headers=_github_headers()
        ) as client:
            response = client.get(raw_url)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch %s: %s", raw_url, exc)
        return None


def _collect_tree_entries(
    *,
    client: httpx.Client,
    owner: str,
    repo: str,
    ref: str,
    remote_path: str,
    rel_prefix: str,
    out: list[dict],
    max_entries: int,
) -> bool:
    """Recurse into the Contents API, filling ``out`` with entries.

    Returns True if the ``max_entries`` cap was hit (truncated).
    """
    api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{remote_path}?ref={ref}"
    response = client.get(api_url)
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, list):
        if isinstance(payload, dict) and payload.get("type") == "file":
            if len(out) >= max_entries:
                return True
            out.append(
                {
                    "path": rel_prefix + payload["name"],
                    "kind": "file",
                    "size": payload.get("size"),
                }
            )
        return False

    for entry in payload:
        if len(out) >= max_entries:
            return True
        name = entry["name"]
        kind = "dir" if entry["type"] == "dir" else "file"
        rel = rel_prefix + name
        if kind == "dir":
            out.append({"path": rel, "kind": "dir", "size": None})
            if _collect_tree_entries(
                client=client,
                owner=owner,
                repo=repo,
                ref=ref,
                remote_path=entry["path"],
                rel_prefix=f"{rel}/",
                out=out,
                max_entries=max_entries,
            ):
                return True
        else:
            out.append({"path": rel, "kind": "file", "size": entry.get("size")})
    return False
