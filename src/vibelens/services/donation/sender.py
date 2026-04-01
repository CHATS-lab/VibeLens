"""Donation sender — collect session files, create ZIP, send to donation server.

Packages raw session files, parsed trajectories, and git bundles into
a ZIP archive and POSTs it to the configured donation server endpoint.
Works with both LocalStore (raw JSONL files available) and DiskStore
(only parsed JSON files available).

When sessions were uploaded (DiskStore with _upload_id tag), the original
upload ZIP is included in sessions/raw/ instead of the parsed JSON duplicate.
"""

import asyncio
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from vibelens import __version__
from vibelens.deps import get_settings, get_store
from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.trajectories.trajectory import Trajectory
from vibelens.schemas.session import DonateResult
from vibelens.services.session.store_resolver import load_from_stores
from vibelens.services.upload.processor import generate_upload_id
from vibelens.storage.conversation.base import TrajectoryStore
from vibelens.storage.conversation.local import LocalStore
from vibelens.utils.git import compute_repo_hash, create_git_bundle, resolve_git_root
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
        session_token: Browser tab token for upload store resolution.

    Returns:
        DonateResult with counts and per-session errors.
    """
    settings = get_settings()
    stores = _active_stores(session_token)

    sessions_data = _collect_sessions(stores, session_ids, session_token)
    if not sessions_data.valid_sessions:
        return DonateResult(total=len(session_ids), donated=0, errors=sessions_data.errors)

    donation_id = generate_upload_id()
    bundle_dir = Path(tempfile.mkdtemp(prefix="vibelens_bundles_"))
    try:
        repo_bundles, repo_hash_map = await asyncio.to_thread(
            _resolve_repo_bundles, sessions_data.valid_sessions, bundle_dir
        )
        for session in sessions_data.valid_sessions:
            session.repo_hash = repo_hash_map.get(session.session_id)
        zip_path = _create_donation_zip(sessions_data, donation_id, repo_bundles)
        try:
            donation_url = f"{settings.donation_url.rstrip('/')}{DONATION_RECEIVE_PATH}"
            await _send_zip(zip_path, donation_url, donation_id)
            donated = len(sessions_data.valid_sessions)
        except httpx.HTTPError as exc:
            logger.warning("Donation upload failed: %s", exc)
            sessions_data.errors.append({"error": f"Upload failed: {exc}"})
            donated = 0
        finally:
            zip_path.unlink(missing_ok=True)
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)

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
        source_upload_id: str | None = None,
        project_path: str | None = None,
        repo_hash: str | None = None,
        git_branch: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.agent_type = agent_type
        # List of (absolute_path, relative_path_in_zip) tuples
        self.raw_files = raw_files
        self.parsed_json = parsed_json
        self.trajectory_count = trajectory_count
        self.step_count = step_count
        # Set when session was uploaded — points to the original upload ZIP
        self.source_upload_id = source_upload_id
        self.project_path = project_path
        self.repo_hash = repo_hash
        self.git_branch = git_branch


@dataclass
class _RepoBundle:
    """A successfully created git bundle for a single repository."""

    repo_hash: str
    bundle_path: Path
    bundle_size: int = field(default=0)
    session_ids: list[str] = field(default_factory=list)


def _active_stores(session_token: str | None = None) -> list[TrajectoryStore]:
    """Return all active trajectory stores visible to the given token.

    In demo mode, includes per-user upload stores so that newly uploaded
    sessions are discoverable for donation.

    Args:
        session_token: Browser tab UUID for per-user isolation.

    Returns:
        Ordered list of stores to search.
    """
    from vibelens.deps import get_example_store, get_upload_stores, is_demo_mode

    stores: list[TrajectoryStore] = [get_store()]
    if is_demo_mode():
        stores.extend(get_upload_stores(session_token))
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
    stores: list[TrajectoryStore],
    session_ids: list[str],
    session_token: str | None = None,
) -> _SessionCollectionResult:
    """Gather raw files and parsed data for each session.

    Args:
        stores: Active trajectory stores to search across.
        session_ids: Session IDs to collect (already visibility-checked).
        session_token: Browser tab token for upload store resolution.

    Returns:
        Collection result with valid sessions and any errors.
    """
    result = _SessionCollectionResult()

    for session_id in session_ids:
        try:
            _collect_single_session(
                stores, session_id, session_token, result
            )
        except Exception as exc:
            logger.warning(
                "Donation: unexpected error collecting session %s: %s",
                session_id,
                exc,
                exc_info=True,
            )
            result.errors.append(
                {"session_id": session_id, "error": f"Collection error: {exc}"}
            )

    return result


def _collect_single_session(
    stores: list[TrajectoryStore],
    session_id: str,
    session_token: str | None,
    result: _SessionCollectionResult,
) -> None:
    """Collect data for a single session, appending to *result*.

    Raises on unexpected errors so the caller can catch per-session.

    Args:
        stores: Stores to search.
        session_id: Session to collect.
        session_token: Browser tab token for upload store resolution.
        result: Mutable accumulator for valid sessions and errors.
    """
    found = _find_session_in_stores(stores, session_id)
    if not found:
        store_names = [type(s).__name__ for s in stores]
        logger.warning(
            "Donation: source file not found for %s (searched %d stores: %s)",
            session_id,
            len(stores),
            store_names,
        )
        result.errors.append({"session_id": session_id, "error": "Source file not found"})
        return

    store, source = found
    filepath, parser = source

    # Check if this session came from an upload (DiskStore with _upload_id tag)
    meta = store.get_metadata(session_id)
    source_upload_id = meta.get("_upload_id") if meta else None

    raw_files = _resolve_raw_files(store, filepath, parser, source_upload_id)

    trajectories = load_from_stores(session_id, session_token)
    if not trajectories:
        logger.warning(
            "Donation: failed to load session %s (store=%s, file=%s, parser=%s)",
            session_id,
            type(store).__name__,
            filepath,
            type(parser).__name__,
        )
        result.errors.append({"session_id": session_id, "error": "Failed to load session"})
        return

    parsed_json = json.dumps(
        [t.model_dump(mode="json") for t in trajectories],
        indent=2,
        default=str,
        ensure_ascii=False,
    )
    step_count = sum(len(t.steps) for t in trajectories)

    main_trajectory = _find_main_trajectory(trajectories)
    project_path = main_trajectory.project_path if main_trajectory else None
    git_branch = _extract_git_branch(main_trajectory) if main_trajectory else None

    # For uploaded sessions (DiskStore), parser is ParsedTrajectoryParser
    # with generic "parsed" type — get the real agent type from metadata
    meta_agent = meta.get("agent", {}).get("name") if meta else None
    agent_type = meta_agent or parser.AGENT_TYPE.value

    result.valid_sessions.append(
        _SessionData(
            session_id=session_id,
            agent_type=agent_type,
            raw_files=raw_files,
            parsed_json=parsed_json,
            trajectory_count=len(trajectories),
            step_count=step_count,
            source_upload_id=source_upload_id,
            project_path=project_path,
            git_branch=git_branch,
        )
    )


def _resolve_raw_files(
    store: TrajectoryStore,
    filepath: Path,
    parser: BaseParser,
    source_upload_id: str | None = None,
) -> list[tuple[Path, str]]:
    """Resolve raw session files and compute their relative ZIP paths.

    For uploaded sessions (source_upload_id set), returns the original
    upload ZIP instead of parsed JSON duplicates. For LocalStore, uses
    get_data_dir() to compute paths relative to the agent data directory.

    Args:
        store: Active trajectory store.
        filepath: Absolute path to the main session file.
        parser: Parser that owns this session.
        source_upload_id: Upload ID if this session came from an upload.

    Returns:
        List of (absolute_path, zip_relative_path) tuples.
    """
    # Uploaded sessions: include the original upload ZIP in sessions/raw/
    if source_upload_id:
        upload_zip = _locate_upload_zip(source_upload_id)
        if upload_zip:
            zip_path = f"sessions/raw/{source_upload_id}.zip"
            return [(upload_zip, zip_path)]
        logger.warning(
            "Upload ZIP not found for %s, falling back to session files", source_upload_id
        )

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
        zip_path = f"sessions/raw/{parser.AGENT_TYPE.value}/{rel}"
        raw_files.append((f, zip_path))

    return raw_files


def _locate_upload_zip(upload_id: str) -> Path | None:
    """Find the original upload ZIP on disk.

    Args:
        upload_id: Upload identifier (e.g. "20260329143012_a1b2").

    Returns:
        Path to the upload ZIP, or None if not found.
    """
    settings = get_settings()
    zip_path = settings.upload_dir / upload_id / f"{upload_id}.zip"
    if zip_path.exists():
        return zip_path
    return None


def _find_main_trajectory(trajectories: list[Trajectory]) -> Trajectory | None:
    """Return the main (non-sub-agent) trajectory from a group.

    The main trajectory has no ``parent_trajectory_ref``.  Falls back to the
    first trajectory if all are sub-agents.

    Args:
        trajectories: Parsed trajectory group for a session.

    Returns:
        The main trajectory, or None if the list is empty.
    """
    if not trajectories:
        return None
    for traj in trajectories:
        if traj.parent_trajectory_ref is None:
            return traj
    return trajectories[0]


def _extract_git_branch(trajectory: Trajectory) -> str | None:
    """Extract the primary git branch from trajectory extra metadata.

    Args:
        trajectory: Main trajectory to inspect.

    Returns:
        First git branch string, or None if unavailable.
    """
    if not trajectory.extra:
        return None
    branches = trajectory.extra.get("git_branches")
    if branches and isinstance(branches, list):
        return branches[0]
    return None


def _resolve_repo_bundles(
    sessions: list[_SessionData], bundle_dir: Path
) -> tuple[list[_RepoBundle], dict[str, str]]:
    """Create git bundles for repos referenced by sessions.

    Deduplicates by both ``project_path`` string (avoids redundant
    ``git rev-parse`` calls) and resolved git root (avoids duplicate bundles
    when different paths resolve to the same repo).

    Args:
        sessions: Sessions with ``project_path`` populated.
        bundle_dir: Temporary directory for bundle files.

    Returns:
        Tuple of (bundles, repo_hash_map) where repo_hash_map is
        ``{session_id: repo_hash}`` for sessions that matched a repo.
    """
    # Cache resolve_git_root results by project_path string
    path_to_root: dict[str, Path | None] = {}
    root_to_hash: dict[Path, str] = {}
    root_to_session_ids: dict[Path, list[str]] = {}

    for session in sessions:
        if not session.project_path:
            continue

        # Avoid redundant subprocess calls for the same project_path
        if session.project_path not in path_to_root:
            path_to_root[session.project_path] = resolve_git_root(Path(session.project_path))

        git_root = path_to_root[session.project_path]
        if not git_root:
            logger.warning("No git repo found for project_path %s", session.project_path)
            continue

        if git_root not in root_to_hash:
            root_to_hash[git_root] = compute_repo_hash(git_root)
            root_to_session_ids[git_root] = []
        root_to_session_ids[git_root].append(session.session_id)

    bundles: list[_RepoBundle] = []
    repo_hash_map: dict[str, str] = {}

    for git_root, repo_hash in root_to_hash.items():
        output_path = bundle_dir / f"{repo_hash}.bundle"
        if not create_git_bundle(git_root, output_path):
            logger.warning("Failed to bundle repo %s (hash %s)", git_root, repo_hash)
            continue

        session_ids = root_to_session_ids[git_root]
        bundle_size = output_path.stat().st_size
        bundle = _RepoBundle(
            repo_hash=repo_hash,
            bundle_path=output_path,
            bundle_size=bundle_size,
            session_ids=session_ids,
        )
        bundles.append(bundle)

        for sid in session_ids:
            repo_hash_map[sid] = repo_hash

    return bundles, repo_hash_map


def _create_donation_zip(
    sessions_data: _SessionCollectionResult,
    donation_id: str,
    repo_bundles: list[_RepoBundle] | None = None,
) -> Path:
    """Create a ZIP archive containing raw files, parsed JSON, git bundles, and a manifest.

    All entries are prefixed with ``{donation_id}/`` so unzipping creates
    a single wrapping directory. Upload ZIPs shared by multiple sessions
    are deduplicated (written once).

    Args:
        sessions_data: Collected session data to package.
        donation_id: Unique donation identifier used as wrapping directory.
        repo_bundles: Git bundles to include in repos/ directory.

    Returns:
        Path to the created temporary ZIP file.
    """
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = Path(tmp.name)

    manifest_sessions = []
    # Track written raw files to deduplicate upload ZIPs shared across sessions
    written_raw_paths: set[str] = set()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for session in sessions_data.valid_sessions:
            raw_zip_paths = []
            for abs_path, rel_zip_path in session.raw_files:
                prefixed_path = f"{donation_id}/{rel_zip_path}"
                # Deduplicate: multiple sessions from the same upload share one ZIP
                if prefixed_path not in written_raw_paths:
                    zf.write(abs_path, prefixed_path)
                    written_raw_paths.add(prefixed_path)
                raw_zip_paths.append(prefixed_path)

            parsed_path = f"{donation_id}/sessions/parsed/{session.session_id}.json"
            zf.writestr(parsed_path, session.parsed_json)

            session_entry: dict = {
                "session_id": session.session_id,
                "agent_type": session.agent_type,
                "trajectory_count": session.trajectory_count,
                "step_count": session.step_count,
                "raw_files": raw_zip_paths,
            }
            if session.source_upload_id:
                session_entry["source_upload_id"] = session.source_upload_id
            if session.repo_hash:
                session_entry["repo_hash"] = session.repo_hash
            if session.git_branch:
                session_entry["git_branch"] = session.git_branch
            manifest_sessions.append(session_entry)

        # Write git bundles into repos/
        bundles = repo_bundles or []
        for bundle in bundles:
            bundle_zip_path = f"{donation_id}/repos/{bundle.repo_hash}.bundle"
            zf.write(bundle.bundle_path, bundle_zip_path)

        manifest_repos = [
            {
                "repo_hash": b.repo_hash,
                "bundle_file": f"repos/{b.repo_hash}.bundle",
                "bundle_size_bytes": b.bundle_size,
                "session_ids": b.session_ids,
            }
            for b in bundles
        ]
        manifest: dict = {
            "donation_id": donation_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "vibelens_version": __version__,
            "sessions": manifest_sessions,
        }
        if manifest_repos:
            manifest["repos"] = manifest_repos
        manifest_path = f"{donation_id}/{MANIFEST_FILENAME}"
        zf.writestr(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False))

    return zip_path


async def _send_zip(zip_path: Path, url: str, donation_id: str) -> None:
    """POST the donation ZIP to the donation server.

    Args:
        zip_path: Path to the ZIP file to upload.
        url: Full URL of the donation receive endpoint.
        donation_id: Used as the upload filename.

    Raises:
        httpx.HTTPError: If the request fails.
    """
    filename = f"{donation_id}.zip"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        with open(zip_path, "rb") as f:
            response = await client.post(url, files={"file": (filename, f, "application/zip")})
            response.raise_for_status()
    logger.info("Donation uploaded successfully to %s", url)
