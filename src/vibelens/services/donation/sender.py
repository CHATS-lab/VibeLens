"""Donation sender — collect session files, create ZIP, send to donation server.

Packages raw session files and parsed trajectories into a ZIP archive
and POSTs it to the configured donation server endpoint. Works with
both LocalStore (raw JSONL files available) and DiskStore (only parsed
JSON files available).
"""

import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

from vibelens import __version__
from vibelens.deps import get_settings, get_store
from vibelens.ingest.parsers.base import BaseParser
from vibelens.schemas.session import DonateResult
from vibelens.services.session.store_resolver import load_from_stores
from vibelens.storage.conversation.base import TrajectoryStore
from vibelens.storage.conversation.local import LocalStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

DONATION_RECEIVE_PATH = "/api/donation/receive"
MANIFEST_FILENAME = "manifest.json"
HTTP_TIMEOUT_SECONDS = 120


async def send_donation(session_ids: list[str], session_token: str | None = None) -> DonateResult:
    """Package selected sessions into a ZIP and send to the donation server.

    Collects raw session files (when available) and parsed trajectory
    JSON for each session, bundles them into a ZIP with a manifest, and
    POSTs the ZIP to the configured donation server.

    Args:
        session_ids: Pre-validated session IDs to donate.
        session_token: Browser tab token (unused here, kept for interface symmetry).

    Returns:
        DonateResult with counts and per-session errors.
    """
    settings = get_settings()
    stores = _active_stores()

    sessions_data = _collect_sessions(stores, session_ids)
    if not sessions_data.valid_sessions:
        return DonateResult(total=len(session_ids), donated=0, errors=sessions_data.errors)

    zip_path = _create_donation_zip(sessions_data)
    try:
        donation_url = f"{settings.donation_url.rstrip('/')}{DONATION_RECEIVE_PATH}"
        await _send_zip(zip_path, donation_url)
        donated = len(sessions_data.valid_sessions)
    except httpx.HTTPError as exc:
        logger.warning("Donation upload failed: %s", exc)
        sessions_data.errors.append({"error": f"Upload failed: {exc}"})
        donated = 0
    finally:
        zip_path.unlink(missing_ok=True)

    return DonateResult(total=len(session_ids), donated=donated, errors=sessions_data.errors)


class _SessionCollectionResult:
    """Intermediate result from collecting session data for ZIP creation."""

    def __init__(self) -> None:
        self.valid_sessions: list[_SessionData] = []
        self.errors: list[dict] = []


class _SessionData:
    """Data for a single session to include in the donation ZIP."""

    def __init__(
        self,
        session_id: str,
        agent_type: str,
        raw_files: list[tuple[Path, str]],
        parsed_json: str,
        trajectory_count: int,
        step_count: int,
    ) -> None:
        self.session_id = session_id
        self.agent_type = agent_type
        # List of (absolute_path, relative_path_in_zip) tuples
        self.raw_files = raw_files
        self.parsed_json = parsed_json
        self.trajectory_count = trajectory_count
        self.step_count = step_count


def _active_stores() -> list[TrajectoryStore]:
    """Return all active trajectory stores (primary + example in demo mode)."""
    from vibelens.deps import get_example_store, is_demo_mode

    stores: list[TrajectoryStore] = [get_store()]
    if is_demo_mode():
        stores.append(get_example_store())
    return stores


def _find_session_in_stores(
    stores: list[TrajectoryStore], session_id: str
) -> tuple[TrajectoryStore, tuple] | None:
    """Find a session across multiple stores.

    Args:
        stores: Stores to search in order.
        session_id: Session to find.

    Returns:
        Tuple of (store, session_source) or None.
    """
    for store in stores:
        source = store.get_session_source(session_id)
        if source:
            return store, source
    return None


def _collect_sessions(
    stores: list[TrajectoryStore], session_ids: list[str]
) -> _SessionCollectionResult:
    """Gather raw files and parsed data for each session.

    Args:
        stores: Active trajectory stores to search across.
        session_ids: Session IDs to collect (already visibility-checked).

    Returns:
        Collection result with valid sessions and any errors.
    """
    result = _SessionCollectionResult()

    for session_id in session_ids:
        found = _find_session_in_stores(stores, session_id)
        if not found:
            result.errors.append({"session_id": session_id, "error": "Source file not found"})
            continue

        store, source = found
        filepath, parser = source
        raw_files = _resolve_raw_files(store, filepath, parser)

        trajectories = load_from_stores(session_id)
        if not trajectories:
            result.errors.append({"session_id": session_id, "error": "Failed to load session"})
            continue

        parsed_json = json.dumps(
            [t.model_dump(mode="json") for t in trajectories],
            indent=2,
            default=str,
            ensure_ascii=False,
        )
        step_count = sum(len(t.steps) for t in trajectories)

        result.valid_sessions.append(
            _SessionData(
                session_id=session_id,
                agent_type=parser.AGENT_TYPE.value,
                raw_files=raw_files,
                parsed_json=parsed_json,
                trajectory_count=len(trajectories),
                step_count=step_count,
            )
        )

    return result


def _resolve_raw_files(
    store: TrajectoryStore, filepath: Path, parser: BaseParser
) -> list[tuple[Path, str]]:
    """Resolve raw session files and compute their relative ZIP paths.

    For LocalStore, uses get_data_dir() to compute paths relative to
    the agent data directory (e.g. ~/.claude). For other stores, uses
    the filename only.

    Args:
        store: Active trajectory store.
        filepath: Absolute path to the main session file.
        parser: Parser that owns this session.

    Returns:
        List of (absolute_path, zip_relative_path) tuples.
    """
    session_files = parser.get_session_files(filepath)

    # LocalStore has agent data dirs for computing relative paths
    data_dir = None
    if isinstance(store, LocalStore):
        data_dir = store.get_data_dir(parser) or parser.LOCAL_DATA_DIR

    raw_files: list[tuple[Path, str]] = []
    for f in session_files:
        if not f.exists():
            continue
        rel = f.relative_to(data_dir) if data_dir and f.is_relative_to(data_dir) else Path(f.name)
        zip_path = f"raw/{parser.AGENT_TYPE.value}/{rel}"
        raw_files.append((f, zip_path))

    return raw_files


def _create_donation_zip(sessions_data: _SessionCollectionResult) -> Path:
    """Create a ZIP archive containing raw files, parsed JSON, and a manifest.

    ZIP structure:
        raw/{agent_type}/{relative_path}  — original session files
        parsed/{session_id}.json          — parsed trajectory groups
        manifest.json                     — metadata about all sessions

    Args:
        sessions_data: Collected session data to package.

    Returns:
        Path to the created temporary ZIP file.
    """
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = Path(tmp.name)

    manifest_sessions = []

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for session in sessions_data.valid_sessions:
            raw_zip_paths = []
            for abs_path, rel_zip_path in session.raw_files:
                zf.write(abs_path, rel_zip_path)
                raw_zip_paths.append(rel_zip_path)

            parsed_path = f"parsed/{session.session_id}.json"
            zf.writestr(parsed_path, session.parsed_json)

            manifest_sessions.append(
                {
                    "session_id": session.session_id,
                    "agent_type": session.agent_type,
                    "trajectory_count": session.trajectory_count,
                    "step_count": session.step_count,
                    "raw_files": raw_zip_paths,
                }
            )

        manifest = {
            "timestamp": datetime.now(UTC).isoformat(),
            "vibelens_version": __version__,
            "sessions": manifest_sessions,
        }
        zf.writestr(MANIFEST_FILENAME, json.dumps(manifest, indent=2, ensure_ascii=False))

    return zip_path


async def _send_zip(zip_path: Path, url: str) -> None:
    """POST the donation ZIP to the donation server.

    Args:
        zip_path: Path to the ZIP file to upload.
        url: Full URL of the donation receive endpoint.

    Raises:
        httpx.HTTPError: If the request fails.
    """
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        with open(zip_path, "rb") as f:
            response = await client.post(
                url, files={"file": ("donation.zip", f, "application/zip")}
            )
            response.raise_for_status()
    logger.info("Donation uploaded successfully to %s", url)
