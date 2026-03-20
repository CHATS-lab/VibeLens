"""Path and project-name utilities."""

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

DEFAULT_PROJECT_NAME = "Unknown"
LAST_N_SEGMENTS = 2

# Heuristic: paths starting with a drive letter (e.g. C:\) are Windows
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\\/]")


def _split_path_segments(project_path: str) -> list[str]:
    """Split a path into segments, handling both Unix and Windows paths.

    Args:
        project_path: Absolute path string (Unix or Windows).

    Returns:
        List of non-empty path segments.
    """
    if _WINDOWS_PATH_RE.match(project_path):
        return list(PureWindowsPath(project_path).parts[1:])
    return list(PurePosixPath(project_path).parts[1:])


def extract_project_name(project_path: str) -> str:
    """Extract the last two path segments as a human-readable project name.

    Handles both Unix (``/Users/me/project``) and Windows
    (``C:\\Users\\me\\project``) paths.

    Args:
        project_path: Absolute path string.

    Returns:
        Last two path components joined by ``/``, or ``"Unknown"`` if empty.
    """
    if not project_path:
        return DEFAULT_PROJECT_NAME
    segments = _split_path_segments(project_path)
    if not segments:
        return DEFAULT_PROJECT_NAME
    tail = segments[-LAST_N_SEGMENTS:]
    return "/".join(tail)


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
