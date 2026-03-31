"""Upload orchestration — stream, validate, extract, parse, store.

Handles the full upload lifecycle:
1. Stream incoming zip to ``{settings.upload_dir}/{upload_id}/{upload_id}.zip``
2. Validate and extract the archive
3. Discover session files using the agent-specific parser
4. Parse and store trajectories into ``{settings.upload_dir}/{upload_id}/``
5. Append upload metadata to ``{settings.upload_dir}/metadata.jsonl``
6. Clean up temporary extraction directory

Everything (zip, parsed trajectories, metadata) lives under
``settings.upload_dir``.  In demo mode the main DiskStore also
points to ``settings.upload_dir`` so uploaded sessions are
discovered automatically via rglob.
"""

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from vibelens.config.anonymize import AnonymizeConfig
from vibelens.deps import get_settings, get_store
from vibelens.ingest.anonymize.rule_anonymizer.anonymizer import RuleAnonymizer
from vibelens.ingest.discovery import discover_session_files, get_parser
from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType
from vibelens.schemas.upload import UploadResult
from vibelens.services.dashboard.loader import (
    invalidate_cache as invalidate_dashboard_cache,
)
from vibelens.services.session.search import invalidate_search_index
from vibelens.storage.conversation.disk import DiskStore
from vibelens.utils import get_logger
from vibelens.utils.json_helpers import locked_jsonl_append
from vibelens.utils.zip import extract_zip, validate_zip

logger = get_logger(__name__)

# Zip commands use `cd` to ensure the archive contains clean relative paths
# (e.g. projects/...) instead of absolute paths (e.g. Users/name/.claude/projects/...).
UPLOAD_COMMANDS: dict[str, dict[str, dict[str, str]]] = {
    AgentType.CLAUDE_CODE: {
        "macos": {
            "command": (
                "cd ~/.claude && zip -r claude-data.zip projects/ -x '**/._*' '**/__MACOSX/*'"
            ),
            "description": "Output: ~/.claude/claude-data.zip",
        },
        "linux": {
            "command": "cd ~/.claude && zip -r claude-data.zip projects/",
            "description": "Output: ~/.claude/claude-data.zip",
        },
        "windows": {
            "command": (
                "cd $env:USERPROFILE\\.claude; Compress-Archive -Path projects\\*"
                " -DestinationPath claude-data.zip"
            ),
            "description": "Output: ~\\.claude\\claude-data.zip",
        },
    },
    AgentType.CODEX: {
        "macos": {
            "command": (
                "cd ~/.codex && zip -r codex-data.zip sessions/ -x '**/._*' '**/__MACOSX/*'"
            ),
            "description": "Output: ~/.codex/codex-data.zip",
        },
        "linux": {
            "command": "cd ~/.codex && zip -r codex-data.zip sessions/",
            "description": "Output: ~/.codex/codex-data.zip",
        },
        "windows": {
            "command": (
                "cd $env:USERPROFILE\\.codex; Compress-Archive -Path sessions\\*"
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
                "cd $env:USERPROFILE\\.gemini; Compress-Archive -Path tmp\\*"
                " -DestinationPath gemini-data.zip"
            ),
            "description": "Output: ~\\.gemini\\gemini-data.zip",
        },
    },
}

UPLOAD_ID_TIME_FORMAT = "%Y%m%d%H%M%S"
SHORT_UUID_LENGTH = 4
EXTRACTED_SUBDIR = "_extracted"
METADATA_FILENAME = "metadata.jsonl"


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
        String in format ``{YYYYMMDDHHMMSS}_{short_uuid}``.
    """
    timestamp = datetime.now(UTC).strftime(UPLOAD_ID_TIME_FORMAT)
    short_uuid = uuid4().hex[:SHORT_UUID_LENGTH]
    return f"{timestamp}_{short_uuid}"


async def receive_zip(
    file: UploadFile, upload_dir: Path, upload_id: str, max_bytes: int, chunk_size: int
) -> Path:
    """Stream an uploaded zip file to disk.

    Writes to ``{upload_dir}/{upload_id}/{upload_id}.zip``, reading in
    fixed-size chunks to keep memory bounded.

    Args:
        file: The uploaded file from FastAPI.
        upload_dir: Base upload storage directory (settings.upload_dir).
        upload_id: Unique identifier for this upload.
        max_bytes: Maximum file size allowed.
        chunk_size: Read chunk size in bytes.

    Returns:
        Path to the saved zip file.

    Raises:
        HTTPException: If file exceeds size limit.
    """
    dest_dir = upload_dir / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dest_dir / f"{upload_id}.zip"
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

    Extraction goes into a ``_extracted`` sibling directory next to the zip.

    Args:
        zip_path: Path to the uploaded zip file.
        agent_type: Agent CLI identifier for file discovery.
        max_zip_bytes: Maximum allowed zip file size.
        max_extracted_bytes: Maximum total uncompressed size.
        max_file_count: Maximum number of files in the archive.

    Returns:
        List of discovered session file paths.
    """
    validate_zip(
        zip_path=zip_path,
        max_zip_bytes=max_zip_bytes,
        max_extracted_bytes=max_extracted_bytes,
        max_file_count=max_file_count,
    )

    extracted_dir = zip_path.parent / EXTRACTED_SUBDIR
    extract_zip(zip_path=zip_path, dest_dir=extracted_dir)

    return discover_session_files(extracted_dir=extracted_dir, agent_type=agent_type)


def cleanup_extraction(upload_dir: Path, upload_id: str) -> None:
    """Remove the temporary extraction directory for an upload.

    The zip file itself is kept as a permanent archive;
    only the ``_extracted/`` subdirectory is removed.

    Args:
        upload_dir: Base upload storage directory (settings.upload_dir).
        upload_id: Upload identifier whose extraction dir to clean up.
    """
    extracted_dir = upload_dir / upload_id / EXTRACTED_SUBDIR
    if extracted_dir.exists():
        shutil.rmtree(extracted_dir, ignore_errors=True)


def _require_disk_store() -> DiskStore:
    """Get the current store, asserting it is a DiskStore.

    Uploads require DiskStore (demo mode). In self-use mode the store
    is a LocalStore which does not support writes.

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

    Everything (zip, parsed trajectories, metadata) goes under
    ``settings.upload_dir``.  The per-upload DiskStore at
    ``{upload_dir}/{upload_id}/`` tags each trajectory with
    ``_upload_id`` for visibility filtering.

    Args:
        file: Uploaded zip file.
        agent_type: Agent CLI identifier.
        session_token: Browser tab token for upload ownership (demo mode).

    Returns:
        UploadResult with counts and any errors.
    """
    settings = get_settings()
    main_store = _require_disk_store()

    filename = file.filename or "upload.zip"
    result = UploadResult(files_received=1)
    upload_id = generate_upload_id()
    token_short = session_token[:8] if session_token else "none"

    logger.info(
        "process_zip START: file=%s agent=%s token=%s upload_id=%s upload_dir=%s",
        filename,
        agent_type,
        token_short,
        upload_id,
        settings.upload_dir,
    )

    try:
        # 1. Stream zip to settings.upload_dir/{upload_id}/{upload_id}.zip
        zip_path = await receive_zip(
            file=file,
            upload_dir=settings.upload_dir,
            upload_id=upload_id,
            max_bytes=settings.max_zip_bytes,
            chunk_size=settings.stream_chunk_size,
        )
        logger.info("Received zip: %s (%d bytes)", zip_path, zip_path.stat().st_size)

        # 2. Validate, extract, and discover session files
        session_files = await asyncio.to_thread(
            extract_and_discover,
            zip_path=zip_path,
            agent_type=agent_type,
            max_zip_bytes=settings.max_zip_bytes,
            max_extracted_bytes=settings.max_extracted_bytes,
            max_file_count=settings.max_file_count,
        )
        logger.info(
            "Discovered %d session files in %s: %s",
            len(session_files),
            filename,
            [f.name for f in session_files[:10]],
        )

        # 3. Parse files and store trajectories under {upload_dir}/{upload_id}/
        #    The _upload_id tag lets the main store enforce visibility filtering.
        tags: dict[str, str] = {"_upload_id": upload_id}
        if session_token:
            tags["_session_token"] = session_token
        upload_store = DiskStore(root=settings.upload_dir / upload_id, default_tags=tags)
        upload_store.initialize()

        parser = get_parser(agent_type=agent_type)
        anonymizer = RuleAnonymizer(AnonymizeConfig(enabled=True))
        session_details = await asyncio.to_thread(
            _parse_and_store_files,
            session_files=session_files,
            parser=parser,
            store=upload_store,
            result=result,
            anonymizer=anonymizer,
        )

        logger.info(
            "Parse complete: sessions_parsed=%d steps_stored=%d skipped=%d errors=%d",
            result.sessions_parsed,
            result.steps_stored,
            result.skipped,
            len(result.errors),
        )

        # 4. Append metadata to the global metadata.jsonl
        metadata = _build_upload_metadata(
            upload_id=upload_id,
            agent_type=agent_type,
            filename=filename,
            session_details=session_details,
            result=result,
            session_token=session_token,
        )
        # Append one upload record to the global metadata.jsonl file
        # (offloaded to thread pool -- file lock can block under contention)
        await asyncio.to_thread(
            locked_jsonl_append, path=settings.upload_dir / METADATA_FILENAME, data=metadata
        )

        # 5. Invalidate caches so the main store picks up new sessions
        main_store.invalidate_index()
        invalidate_search_index()
        invalidate_dashboard_cache()
        logger.info("Invalidated caches for main store at %s", main_store.root)
    except Exception as exc:
        logger.warning("Upload processing failed for %s: %s", filename, exc, exc_info=True)
        result.errors.append({"filename": filename, "error": str(exc)})
    finally:
        # Clean up extraction dir; keep the zip as a permanent archive
        # (offloaded to thread pool -- shutil.rmtree can block on large trees)
        await asyncio.to_thread(
            cleanup_extraction, upload_dir=settings.upload_dir, upload_id=upload_id
        )

    logger.info(
        "process_zip END: upload_id=%s result=parsed=%d stored=%d skipped=%d errors=%d",
        upload_id,
        result.sessions_parsed,
        result.steps_stored,
        result.skipped,
        len(result.errors),
    )
    return result


def _parse_and_store_files(
    session_files: list[Path],
    parser: BaseParser,
    store: DiskStore,
    result: UploadResult,
    anonymizer: RuleAnonymizer,
) -> list[dict]:
    """Parse discovered session files, anonymize, and persist via the disk store.

    Iterates over each discovered file, parses it into trajectories,
    anonymizes them to redact sensitive data, and saves them. Skips files
    that produce no trajectories. Accumulates per-session details for
    the upload metadata manifest.

    Args:
        session_files: List of session file paths from discovery.
        parser: Parser instance for the agent type.
        store: DiskStore for trajectory persistence.
        result: UploadResult to update with counts.
        anonymizer: RuleAnonymizer for redacting sensitive data.

    Returns:
        List of per-session detail dicts for the upload metadata.
    """
    session_details: list[dict] = []

    for file_path in session_files:
        try:
            trajectories = parser.parse_file(file_path=file_path)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", file_path.name, exc)
            result.errors.append({"filename": file_path.name, "error": str(exc)})
            continue

        if not trajectories:
            result.skipped += 1
            continue

        # Find the main trajectory (no parent ref). Skip sub-agent-only files
        # since sub-agents are already included when parsing the main session.
        main = next((t for t in trajectories if not t.parent_trajectory_ref), None)
        if main is None:
            result.skipped += 1
            continue

        # Anonymize all trajectories in the batch before storing
        trajectories = _anonymize_trajectories(
            trajectories=trajectories, anonymizer=anonymizer, result=result
        )

        session_id = main.session_id
        try:
            store.save(trajectories=trajectories)
        except Exception as exc:
            logger.warning("Failed to store %s: %s", file_path.name, exc)
            result.errors.append({"filename": file_path.name, "error": str(exc)})
            continue

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
            store.root.name,
        )

    return session_details


def _anonymize_trajectories(
    trajectories: list, anonymizer: RuleAnonymizer, result: UploadResult
) -> list:
    """Anonymize a batch of trajectories and tag each with redaction metadata.

    Args:
        trajectories: Parsed trajectories from a single session file.
        anonymizer: RuleAnonymizer instance for redacting sensitive data.
        result: UploadResult to accumulate aggregate anonymization stats.

    Returns:
        List of anonymized trajectories with ``extra._anonymized`` and
        ``extra._anonymize_stats`` metadata tags.
    """
    anonymized_results = anonymizer.anonymize_batch(trajectories)
    anonymized_trajectories = []

    for anon_traj, anon_result in anonymized_results:
        if anon_traj.extra is None:
            anon_traj.extra = {}
        anon_traj.extra["_anonymized"] = True
        anon_traj.extra["_anonymize_stats"] = anon_result.model_dump()
        anonymized_trajectories.append(anon_traj)

        # Accumulate into aggregate upload result
        result.secrets_redacted += anon_result.secrets_redacted
        result.paths_anonymized += anon_result.paths_anonymized
        result.pii_redacted += anon_result.pii_redacted

    return anonymized_trajectories


def _build_upload_metadata(
    upload_id: str,
    agent_type: str,
    filename: str,
    session_details: list[dict],
    result: UploadResult,
    session_token: str | None = None,
) -> dict:
    """Build the upload manifest metadata dict.

    Args:
        upload_id: Unique upload identifier.
        agent_type: Agent CLI identifier.
        filename: Original uploaded filename.
        session_details: Per-session detail dicts.
        result: UploadResult with aggregate counts.
        session_token: Browser tab token that owns this upload.

    Returns:
        Metadata dict for appending to metadata.jsonl.
    """
    meta: dict = {
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
            "secrets_redacted": result.secrets_redacted,
            "paths_anonymized": result.paths_anonymized,
            "pii_redacted": result.pii_redacted,
        },
    }
    if session_token:
        meta["session_token"] = session_token
    return meta
