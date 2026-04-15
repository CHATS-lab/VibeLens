"""GitHub URL parsing utilities."""

import re

GITHUB_TREE_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<ref>[^/]+)/(?P<path>.+)"
)

GITHUB_RAW_BASE = "https://raw.githubusercontent.com"


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
