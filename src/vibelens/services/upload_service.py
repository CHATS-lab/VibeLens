"""Upload orchestration — stream, validate, extract, parse, store."""

import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from vibelens.deps import get_settings, get_store
from vibelens.ingest.discovery import discover_session_files
from vibelens.ingest.fingerprint import parse_auto
from vibelens.models.enums import AgentType
from vibelens.models.requests import UploadResult
from vibelens.stores.disk import DiskStore
from vibelens.utils import get_logger
from vibelens.utils.zip import extract_zip, validate_zip

logger = get_logger(__name__)

# Zip commands use `cd` to ensure the archive contains clean relative paths
# (e.g. projects/...) instead of absolute paths (e.g. Users/name/.claude/projects/...).
UPLOAD_COMMANDS: dict[str, dict[str, dict[str, str]]] = {
    AgentType.CLAUDE_CODE: {
        "macos": {
            "command": "cd ~/.claude && zip -r claude-data.zip projects/ -i '*.jsonl'",
            "description": "Output: ~/.claude/claude-data.zip",
        },
        "linux": {
            "command": "cd ~/.claude && zip -r claude-data.zip projects/ -i '*.jsonl'",
            "description": "Output: ~/.claude/claude-data.zip",
        },
        "windows": {
            "command": (
                "cd $env:USERPROFILE\\.claude;"
                " Compress-Archive -Path projects\\*"
                " -DestinationPath claude-data.zip"
            ),
            "description": "Output: ~\\.claude\\claude-data.zip",
        },
    },
    AgentType.CODEX: {
        "macos": {
            "command": "cd ~/.codex && zip -r codex-data.zip sessions/",
            "description": "Output: ~/.codex/codex-data.zip",
        },
        "linux": {
            "command": "cd ~/.codex && zip -r codex-data.zip sessions/",
            "description": "Output: ~/.codex/codex-data.zip",
        },
        "windows": {
            "command": (
                "cd $env:USERPROFILE\\.codex;"
                " Compress-Archive -Path sessions\\*"
                " -DestinationPath codex-data.zip"
            ),
            "description": "Output: ~\\.codex\\codex-data.zip",
        },
    },
    AgentType.GEMINI: {
        "macos": {
            "command": "cd ~/.gemini && zip -r gemini-data.zip tmp/ -i '*.json' -i '.project_root'",
            "description": "Output: ~/.gemini/gemini-data.zip",
        },
        "linux": {
            "command": "cd ~/.gemini && zip -r gemini-data.zip tmp/ -i '*.json' -i '.project_root'",
            "description": "Output: ~/.gemini/gemini-data.zip",
        },
        "windows": {
            "command": (
                "cd $env:USERPROFILE\\.gemini;"
                " Compress-Archive -Path tmp\\*"
                " -DestinationPath gemini-data.zip"
            ),
            "description": "Output: ~\\.gemini\\gemini-data.zip",
        },
    },
}

UPLOAD_ID_TIME_FORMAT = "%Y%m%d%H%M%S"
SHORT_UUID_LENGTH = 4
EXTRACTED_SUBDIR = "_extracted"


def get_upload_command(agent_type: str, os_platform: str) -> dict:
    """Look up the CLI command for zipping an agent's data directory.

    Args:
        agent_type: Agent CLI identifier (claude_code, codex, gemini).
        os_platform: Operating system (macos, linux, windows).

    Returns:
        Dict with 'command' and 'description' keys.

    Raises:
        HTTPException: If agent_type or os_platform is invalid.
    """
    try:
        agent = AgentType(agent_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown agent_type: {agent_type}") from None

    platform_commands = UPLOAD_COMMANDS.get(agent)
    if not platform_commands:
        raise HTTPException(status_code=400, detail=f"No commands for agent: {agent}")

    result = platform_commands.get(os_platform)
    if not result:
        raise HTTPException(status_code=400, detail=f"Unknown os_platform: {os_platform}")
    return result


def generate_upload_id() -> str:
    """Create a unique upload identifier.

    Returns:
        String in format {YYYYMMDDHHMMSS}_{short_uuid}.
    """
    timestamp = datetime.now(UTC).strftime(UPLOAD_ID_TIME_FORMAT)
    short_uuid = uuid4().hex[:SHORT_UUID_LENGTH]
    return f"{timestamp}_{short_uuid}"


async def receive_zip(
    file: UploadFile, root: Path, upload_id: str, max_bytes: int, chunk_size: int
) -> Path:
    """Stream an uploaded zip file to disk.

    Args:
        file: The uploaded file from FastAPI.
        root: Base storage directory.
        upload_id: Unique identifier for this upload.
        max_bytes: Maximum file size allowed.
        chunk_size: Read chunk size in bytes.

    Returns:
        Path to the saved zip file.

    Raises:
        HTTPException: If file exceeds size limit.
    """
    upload_dir = root / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    zip_path = upload_dir / f"{upload_id}.zip"
    total_written = 0

    with open(zip_path, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_written += len(chunk)
            if total_written > max_bytes:
                zip_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400, detail=f"File exceeds {max_bytes // (1024 * 1024)} MB limit"
                )
            f.write(chunk)

    return zip_path


def extract_and_discover(
    zip_path: Path,
    agent_type: str,
    max_zip_bytes: int,
    max_extracted_bytes: int,
    max_file_count: int,
) -> list[Path]:
    """Validate zip, extract contents, and discover session files.

    Args:
        zip_path: Path to the uploaded zip file.
        agent_type: Agent CLI identifier for file discovery.
        max_zip_bytes: Maximum allowed zip file size.
        max_extracted_bytes: Maximum total uncompressed size.
        max_file_count: Maximum number of files in the archive.

    Returns:
        List of discovered session file paths.
    """
    validate_zip(zip_path, max_zip_bytes, max_extracted_bytes, max_file_count)

    extracted_dir = zip_path.parent / EXTRACTED_SUBDIR
    extract_zip(zip_path, extracted_dir)

    return discover_session_files(extracted_dir, agent_type)


def write_upload_metadata(root: Path, upload_id: str, metadata: dict) -> None:
    """Write the upload manifest file.

    Args:
        root: Base storage directory.
        upload_id: Upload identifier (subdirectory name).
        metadata: Upload metadata dict (timestamp, agent_type, sessions, etc.).
    """
    upload_dir = root / upload_id
    meta_path = upload_dir / "metadata.json"
    meta_path.write_text(
        json.dumps(metadata, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )


def cleanup_extraction(root: Path, upload_id: str) -> None:
    """Remove the temporary extraction directory for an upload.

    Args:
        root: Base storage directory.
        upload_id: Upload identifier whose extraction dir to clean up.
    """
    extracted_dir = root / upload_id / EXTRACTED_SUBDIR
    if extracted_dir.exists():
        shutil.rmtree(extracted_dir, ignore_errors=True)


def _require_disk_store() -> DiskStore:
    """Get the current store, asserting it is a DiskStore.

    Returns:
        The DiskStore instance.

    Raises:
        HTTPException: If store is not a DiskStore (uploads not supported).
    """
    store = get_store()
    if not isinstance(store, DiskStore):
        raise HTTPException(status_code=400, detail="Uploads not supported in self-use mode")
    return store


async def process_zip(
    file: UploadFile, agent_type: str, session_token: str | None = None
) -> UploadResult:
    """Full upload orchestration: stream -> validate -> extract -> parse -> store.

    Args:
        file: Uploaded zip file.
        agent_type: Agent CLI identifier.
        session_token: Browser tab token for upload ownership (demo mode).

    Returns:
        UploadResult with counts and any errors.
    """
    settings = get_settings()
    store = _require_disk_store()
    root = store.root

    filename = file.filename or "upload.zip"
    result = UploadResult(files_received=1)
    upload_id = generate_upload_id()

    try:
        zip_path = await receive_zip(
            file, root, upload_id, settings.max_zip_bytes, settings.stream_chunk_size
        )
        session_files = await asyncio.to_thread(
            extract_and_discover,
            zip_path,
            agent_type,
            settings.max_zip_bytes,
            settings.max_extracted_bytes,
            settings.max_file_count,
        )
        logger.info("Discovered %d session files in %s", len(session_files), filename)

        session_details = await asyncio.to_thread(
            _parse_and_store_files, session_files, store, upload_id, result
        )
        metadata = _build_upload_metadata(upload_id, agent_type, filename, session_details, result)
        write_upload_metadata(root, upload_id, metadata)

        if session_token:
            store.register_upload(session_token, upload_id)
    except ValueError as exc:
        result.errors.append({"filename": filename, "error": str(exc)})
    finally:
        cleanup_extraction(root, upload_id)

    return result


def _parse_and_store_files(
    session_files: list[Path], store: DiskStore, upload_id: str, result: UploadResult
) -> list[dict]:
    """Parse discovered session files and persist via the disk store.

    Args:
        session_files: List of session file paths.
        store: DiskStore for persistence.
        upload_id: Upload identifier for storage subdirectory.
        result: UploadResult to update with counts.

    Returns:
        List of per-session detail dicts for the upload metadata.
    """
    session_details: list[dict] = []

    for file_path in session_files:
        try:
            trajectories = parse_auto(file_path)
        except ValueError:
            # Low-confidence or unrecognizable files are empty/metadata-only
            # sessions (e.g. only "progress" or "file-history-snapshot" entries).
            # Count as skipped rather than surfacing as errors.
            result.skipped += 1
            continue

        if not trajectories:
            result.skipped += 1
            continue

        session_id = trajectories[0].session_id
        summary = trajectories[0].to_summary()
        store.save(session_id, trajectories, summary, subdir=upload_id)

        step_count = sum(len(t.steps) for t in trajectories)
        result.sessions_parsed += 1
        result.steps_stored += step_count

        session_details.append(
            {
                "session_id": session_id,
                "trajectory_count": len(trajectories),
                "step_count": step_count,
                "source_file": file_path.name,
            }
        )
        logger.info(
            "Stored %d trajectories from %s (upload %s)",
            len(trajectories),
            file_path.name,
            upload_id,
        )

    return session_details


def _build_upload_metadata(
    upload_id: str,
    agent_type: str,
    filename: str,
    session_details: list[dict],
    result: UploadResult,
) -> dict:
    """Build the upload manifest metadata dict.

    Args:
        upload_id: Unique upload identifier.
        agent_type: Agent CLI identifier.
        filename: Original uploaded filename.
        session_details: Per-session detail dicts.
        result: UploadResult with aggregate counts.

    Returns:
        Metadata dict for writing to metadata.json.
    """
    return {
        "upload_id": upload_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_type": agent_type,
        "original_filename": filename,
        "sessions": session_details,
        "totals": {
            "sessions_parsed": result.sessions_parsed,
            "steps_stored": result.steps_stored,
            "skipped": result.skipped,
            "errors": len(result.errors),
        },
    }
