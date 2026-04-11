"""Git utilities for donation pipeline — repo resolution, bundling, hashing."""

import hashlib
import subprocess
from pathlib import Path

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Timeout for `git rev-parse --show-toplevel` repo root detection
GIT_RESOLVE_TIMEOUT_SECONDS = 10
# Timeout for `git bundle create` (large repos can be slow)
BUNDLE_TIMEOUT_SECONDS = 300


def resolve_git_root(path: Path) -> Path | None:
    """Run ``git rev-parse --show-toplevel`` to find the repo root.

    Args:
        path: Directory to check (need not be the repo root itself).

    Returns:
        Resolved Path to the git repo root, or None if *path* is not
        inside a git repository or git is not available.
    """
    if not path.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=GIT_RESOLVE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return None
        return Path(result.stdout.strip()).resolve()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("resolve_git_root failed for %s: %s", path, exc)
        return None


def create_git_bundle(repo_root: Path, output_path: Path) -> bool:
    """Create a full git bundle (all refs) at *output_path*.

    Args:
        repo_root: Root directory of the git repository.
        output_path: Destination path for the ``.bundle`` file.

    Returns:
        True if the bundle was created successfully, False otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "bundle", "create", str(output_path), "--all"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=BUNDLE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            logger.warning("git bundle failed for %s: %s", repo_root, result.stderr.strip())
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("git bundle error for %s: %s", repo_root, exc)
        return False


def compute_repo_hash(repo_root: Path) -> str:
    """Deterministic 8-char hex hash of the resolved repo root path.

    Used to deduplicate bundles when multiple sessions share the same repo.

    Args:
        repo_root: Resolved absolute path to the git repo root.

    Returns:
        First 8 hex characters of SHA-256(str(repo_root.resolve())).
    """
    digest = hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()
    return digest[:8]
