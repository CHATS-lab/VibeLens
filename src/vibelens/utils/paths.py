"""Path and project-name utilities."""

from pathlib import Path

DEFAULT_PROJECT_NAME = "Unknown"


def extract_project_name(project_path: str) -> str:
    """Extract a human-readable project name from an absolute path.

    Args:
        project_path: Absolute path string (e.g. ``/Users/me/my-project``).

    Returns:
        Last path component, or ``"Unknown"`` if empty.
    """
    if not project_path:
        return DEFAULT_PROJECT_NAME
    return Path(project_path).name or DEFAULT_PROJECT_NAME


def encode_project_path(project_path: str) -> str:
    """Encode a project path to a filesystem-safe directory name.

    Replaces ``/`` with ``-`` and strips the leading dash,
    matching the Claude Code ``projects/`` naming convention.

    Args:
        project_path: Absolute path string.

    Returns:
        Encoded path string, or empty string if input is empty.
    """
    if not project_path:
        return ""
    return project_path.replace("/", "-").lstrip("-")


def ensure_dir(path: Path) -> Path:
    """Create a directory (and parents) if it does not exist.

    Args:
        path: Directory path to create.

    Returns:
        The same path, for chaining convenience.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
