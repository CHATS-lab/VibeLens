"""Version check service.

Fetches the latest stable release from PyPI, compares against the running
version, and assembles the payload used by ``GET /api/version``.
"""

import json
import os
import sys
from dataclasses import dataclass
from importlib import metadata

import httpx
from cachetools import TTLCache
from packaging.version import InvalidVersion, Version

from vibelens.schemas.system import InstallCommands, InstallMethod, VersionInfo
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

PYPI_URL = "https://pypi.org/pypi/vibelens/json"
PYPI_TIMEOUT_SECONDS = 3.0
CACHE_TTL_SECONDS = 3600
DISABLE_ENV_VAR = "VIBELENS_DISABLE_UPDATE_CHECK"

_LATEST_CACHE: TTLCache = TTLCache(maxsize=1, ttl=CACHE_TTL_SECONDS)
_CACHE_KEY = "latest"


@dataclass(frozen=True)
class VersionComparison:
    """Outcome of comparing a current version string to a latest string."""

    update_available: bool
    is_dev_build: bool


def compare_versions(current: str, latest: str | None) -> VersionComparison:
    """Compare ``current`` against ``latest`` using PEP 440 semantics.

    Args:
        current: Version string of the running process.
        latest: Latest stable release on PyPI, or None if unknown.

    Returns:
        VersionComparison with ``update_available`` and ``is_dev_build`` flags.
    """
    if latest is None:
        return VersionComparison(update_available=False, is_dev_build=False)
    try:
        current_v = Version(current)
        latest_v = Version(latest)
    except InvalidVersion:
        return VersionComparison(update_available=False, is_dev_build=False)
    return VersionComparison(
        update_available=latest_v > current_v,
        is_dev_build=current_v > latest_v,
    )


def _is_disabled() -> bool:
    raw = os.environ.get(DISABLE_ENV_VAR, "").strip().lower()
    return raw in {"1", "true", "yes"}


def fetch_latest_version() -> str | None:
    """Fetch the latest stable, non-yanked vibelens version from PyPI.

    Filters out pre-releases and yanked releases. Caches the result in-process
    for ``CACHE_TTL_SECONDS``. Returns None when the opt-out env var is set,
    when PyPI is unreachable, or when no stable releases exist.

    Returns:
        Latest stable version string, or None.
    """
    if _is_disabled():
        return None
    cached = _LATEST_CACHE.get(_CACHE_KEY)
    if cached is not None:
        return cached or None
    try:
        resp = httpx.get(PYPI_URL, timeout=PYPI_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("PyPI version check failed: %s", exc)
        _LATEST_CACHE[_CACHE_KEY] = ""
        return None

    releases = payload.get("releases") or {}
    stable: list[Version] = []
    for raw_version, files in releases.items():
        try:
            parsed = Version(raw_version)
        except InvalidVersion:
            continue
        if parsed.is_prerelease:
            continue
        if files and all(bool(f.get("yanked")) for f in files):
            continue
        stable.append(parsed)

    if not stable:
        _LATEST_CACHE[_CACHE_KEY] = ""
        return None

    highest = max(stable)
    latest_str = str(highest)
    _LATEST_CACHE[_CACHE_KEY] = latest_str
    return latest_str


INSTALL_COMMANDS = InstallCommands(
    uv="uv tool upgrade vibelens",
    pip="pip install -U vibelens",
    npx="npm install -g @chats-lab/vibelens@latest",
)


def _is_editable_install() -> bool:
    """Return True when the running distribution is an editable/dev install."""
    try:
        dist = metadata.distribution("vibelens")
    except metadata.PackageNotFoundError:
        return False
    direct_url = dist.read_text("direct_url.json")
    if not direct_url:
        return False
    try:
        data = json.loads(direct_url)
    except ValueError:
        return False
    return bool(data.get("dir_info", {}).get("editable"))


def _has_distribution() -> bool:
    try:
        metadata.distribution("vibelens")
    except metadata.PackageNotFoundError:
        return False
    return True


def detect_install_method() -> InstallMethod:
    """Detect how the running ``vibelens`` process was installed."""
    if _is_editable_install():
        return "source"
    if os.environ.get("UV_TOOL_BIN_DIR") or "/uv/tools/vibelens/" in sys.prefix:
        return "uv"
    if os.environ.get("NPM_CONFIG_PREFIX") or os.environ.get("npm_config_user_agent"):  # noqa: SIM112
        return "npx"
    if _has_distribution():
        return "pip"
    return "unknown"


def get_version_info(current: str) -> VersionInfo:
    """Assemble the full ``VersionInfo`` payload for ``GET /api/version``.

    Args:
        current: Currently running VibeLens version (``vibelens.__version__``).

    Returns:
        Populated VersionInfo.
    """
    latest = fetch_latest_version()
    comparison = compare_versions(current=current, latest=latest)
    return VersionInfo(
        current=current,
        latest=latest,
        update_available=comparison.update_available,
        is_dev_build=comparison.is_dev_build,
        install_method=detect_install_method(),
        install_commands=INSTALL_COMMANDS,
    )
