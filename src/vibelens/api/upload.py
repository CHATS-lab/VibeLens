"""File upload endpoints for importing agent conversation files."""

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Form, Header, HTTPException, UploadFile

from vibelens.api.deps import get_session_store, is_demo_mode
from vibelens.config import load_settings

if TYPE_CHECKING:
    from vibelens.config.settings import Settings

from vibelens.db import get_connection, insert_messages, insert_session
from vibelens.ingest.fingerprint import FormatMatch, fingerprint_file, parse_auto
from vibelens.ingest.parsers.claude_code import ClaudeCodeParser
from vibelens.ingest.zip_extractor import (
    discover_session_files,
    extract_zip,
    validate_zip,
)
from vibelens.models.enums import AgentType, DataSourceType
from vibelens.models.message import Message
from vibelens.models.requests import UploadResult
from vibelens.models.session import SessionSummary
from vibelens.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["upload"])

# Shell commands for each agent+OS combination, served by GET /upload/commands.
# The wizard frontend displays these so users know how to zip their data.
UPLOAD_COMMANDS: dict[str, dict[str, dict[str, str]]] = {
    AgentType.CLAUDE_CODE: {
        "macos": {
            "command": "zip -r claude-data.zip ~/.claude/projects/ -i '*.jsonl'",
            "description": "Zip all Claude Code session JSONL files.",
        },
        "linux": {
            "command": "zip -r claude-data.zip ~/.claude/projects/ -i '*.jsonl'",
            "description": "Zip all Claude Code session JSONL files.",
        },
        "windows": {
            "command": (
                "Compress-Archive"
                ' -Path "$env:USERPROFILE\\.claude\\projects\\*"'
                " -DestinationPath claude-data.zip"
            ),
            "description": "Zip all Claude Code session JSONL files.",
        },
    },
    AgentType.CODEX: {
        "macos": {
            "command": "zip -r codex-data.zip ~/.codex/sessions/",
            "description": "Zip all Codex CLI session rollout files.",
        },
        "linux": {
            "command": "zip -r codex-data.zip ~/.codex/sessions/",
            "description": "Zip all Codex CLI session rollout files.",
        },
        "windows": {
            "command": (
                "Compress-Archive"
                ' -Path "$env:USERPROFILE\\.codex\\sessions\\*"'
                " -DestinationPath codex-data.zip"
            ),
            "description": "Zip all Codex CLI session rollout files.",
        },
    },
    AgentType.GEMINI: {
        "macos": {
            "command": ("zip -r gemini-data.zip ~/.gemini/tmp/ -i '*.json' -i '.project_root'"),
            "description": "Zip all Gemini CLI session JSON files.",
        },
        "linux": {
            "command": ("zip -r gemini-data.zip ~/.gemini/tmp/ -i '*.json' -i '.project_root'"),
            "description": "Zip all Gemini CLI session JSON files.",
        },
        "windows": {
            "command": (
                "Compress-Archive"
                ' -Path "$env:USERPROFILE\\.gemini\\tmp\\*"'
                " -DestinationPath gemini-data.zip"
            ),
            "description": "Zip all Gemini CLI session JSON files.",
        },
    },
}


@router.post("/upload")
async def upload_files(
    files: list[UploadFile], x_session_token: str = Header(default="")
) -> UploadResult:
    """Upload conversation files for parsing and storage.

    Accepts .json and .jsonl files from any supported agent format.
    Auto-detects format, parses sessions, and stores in the active store.

    Args:
        files: List of uploaded files.
        x_session_token: Client isolation token for demo mode.

    Returns:
        UploadResult with counts and any errors.
    """
    settings = load_settings()
    result = UploadResult(files_received=len(files))
    tmp_dir = Path(tempfile.mkdtemp(prefix="vibelens_upload_"))

    try:
        saved_files = await _save_uploaded_files(files, tmp_dir, result, settings)
        if not saved_files:
            return result

        root_files, has_subagents = _classify_files(saved_files, settings)
        if has_subagents:
            _reconstruct_subagent_layout(saved_files, tmp_dir, settings)

        await _parse_and_store(root_files, has_subagents, result, settings, x_session_token)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


@router.get("/upload/commands")
async def get_upload_commands(agent_type: str, os_platform: str) -> dict:
    """Return a CLI command for zipping the agent's data directory.

    Args:
        agent_type: Agent CLI identifier (claude_code, codex, gemini).
        os_platform: Operating system (macos, linux, windows).

    Returns:
        Dict with 'command' and 'description' keys.
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
        raise HTTPException(
            status_code=400,
            detail=f"Unknown os_platform: {os_platform}",
        )
    return result


@router.post("/upload/zip")
async def upload_zip(
    file: UploadFile,
    agent_type: str = Form(...),
    x_session_token: str = Header(default=""),
) -> UploadResult:
    """Upload a zip archive of agent conversation data.

    Validates, extracts, parses, and stores sessions from the zip file.
    The zip is saved persistently so sessions survive restarts.

    Args:
        file: Uploaded zip file.
        agent_type: Agent CLI identifier (claude_code, codex, gemini).
        x_session_token: Client isolation token for demo mode.

    Returns:
        UploadResult with counts and any errors.
    """
    settings = load_settings()
    filename = file.filename or "upload.zip"

    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    try:
        AgentType(agent_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown agent_type: {agent_type}") from None

    upload_id = str(uuid.uuid4())
    result = UploadResult(files_received=1)

    demo = is_demo_mode()
    skip_persist = demo and not settings.demo_persist_uploads

    # Use a temp directory for extraction; optionally persist the zip
    extract_dir = Path(tempfile.mkdtemp(prefix="vibelens_zip_")) / upload_id

    if skip_persist:
        zip_path = Path(tempfile.mkdtemp(prefix="vibelens_zip_src_")) / f"{upload_id}.zip"
    else:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        zip_path = settings.upload_dir / f"{upload_id}.zip"

    try:
        await _stream_upload_to_disk(
            file, zip_path, settings.max_zip_bytes, settings.stream_chunk_size
        )
        validate_zip(
            zip_path,
            max_zip_bytes=settings.max_zip_bytes,
            max_extracted_bytes=settings.max_extracted_bytes,
            max_file_count=settings.max_file_count,
        )
        extract_zip(zip_path, extract_dir)

        session_files = discover_session_files(extract_dir, agent_type)
        logger.info("Discovered %d session files in %s", len(session_files), upload_id)

        await _parse_and_store_zip_files(
            session_files, upload_id, filename, result, settings, x_session_token
        )
    except ValueError as exc:
        result.errors.append({"filename": filename, "error": str(exc)})
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if skip_persist:
            zip_path.unlink(missing_ok=True)
            zip_path.parent.rmdir()

    return result


async def _stream_upload_to_disk(
    file: UploadFile, dest: Path, max_bytes: int, chunk_size: int
) -> None:
    """Stream an uploaded file to disk in chunks.

    Args:
        file: The uploaded file.
        dest: Destination path on disk.
        max_bytes: Maximum file size allowed.
        chunk_size: Read chunk size in bytes.

    Raises:
        HTTPException: If file exceeds size limit.
    """
    total_written = 0
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_written += len(chunk)
            if total_written > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400,
                    detail=f"File exceeds {max_bytes // (1024 * 1024)} MB limit",
                )
            f.write(chunk)


async def _parse_and_store_zip_files(
    session_files: list[Path],
    upload_id: str,
    zip_filename: str,
    result: UploadResult,
    settings: "Settings",
    token: str = "",
) -> None:
    """Parse discovered session files and store via the active store.

    Args:
        session_files: List of session file paths.
        upload_id: UUID of this upload for source_name.
        zip_filename: Original zip filename.
        result: UploadResult to update with counts.
        settings: Application settings.
        token: Client isolation token for demo mode.
    """
    for file_path in session_files:
        try:
            parsed = _parse_file(file_path, has_subagents=False, settings=settings)
        except ValueError as exc:
            result.errors.append({"filename": file_path.name, "error": str(exc)})
            continue

        relative_path = file_path.name
        for summary, messages in parsed:
            summary.source_type = DataSourceType.UPLOAD
            summary.source_name = f"{upload_id}.zip:{relative_path}"
            stored = await _store_session(summary, messages, token)
            if stored:
                result.sessions_parsed += 1
                result.messages_stored += len(messages)
            else:
                result.skipped += 1


@router.delete("/upload/sessions")
async def delete_uploaded_sessions() -> dict:
    """Delete all sessions imported via file upload.

    Returns:
        Dict with count of deleted sessions.
    """
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT session_id FROM sessions WHERE source_type = ?",
            (DataSourceType.UPLOAD.value,),
        )
        session_ids = [row[0] for row in await cursor.fetchall()]
        if not session_ids:
            return {"deleted": 0}

        placeholders = ",".join("?" * len(session_ids))
        await conn.execute(
            f"DELETE FROM messages WHERE session_id IN ({placeholders})",
            session_ids,
        )
        await conn.execute(
            f"DELETE FROM sessions WHERE session_id IN ({placeholders})",
            session_ids,
        )
        await conn.commit()
        return {"deleted": len(session_ids)}
    finally:
        await conn.close()


async def _save_uploaded_files(
    files: list[UploadFile], tmp_dir: Path, result: UploadResult, settings: "Settings"
) -> list[tuple[str, Path]]:
    """Validate and save uploaded files to the temp directory.

    Args:
        files: Uploaded files from the request.
        tmp_dir: Temporary directory to write files into.
        result: UploadResult to record errors.
        settings: Application settings.

    Returns:
        List of (original_filename, saved_path) tuples.
    """
    allowed = {ext.strip() for ext in settings.upload_allowed_extensions.split(",")}
    max_bytes = settings.max_file_size_bytes

    saved: list[tuple[str, Path]] = []
    for upload_file in files:
        filename = upload_file.filename or "unknown"
        suffix = Path(filename).suffix.lower()

        if suffix not in allowed:
            result.errors.append({"filename": filename, "error": "Unsupported file type"})
            continue

        content = await upload_file.read()
        if len(content) > max_bytes:
            limit_mb = max_bytes // (1024 * 1024)
            result.errors.append(
                {"filename": filename, "error": f"File exceeds {limit_mb} MB limit"}
            )
            continue

        dest = tmp_dir / filename
        dest.write_bytes(content)
        saved.append((filename, dest))

    return saved


def _classify_files(
    saved_files: list[tuple[str, Path]], settings: "Settings"
) -> tuple[list[tuple[str, Path]], bool]:
    """Separate root files from sub-agent files.

    Args:
        saved_files: List of (filename, path) tuples.
        settings: Application settings.

    Returns:
        Tuple of (root_files, has_subagents).
    """
    prefix = settings.subagent_file_prefix
    has_subagents = any(Path(name).stem.startswith(prefix) for name, _ in saved_files)
    root_files = [
        (name, path) for name, path in saved_files if not Path(name).stem.startswith(prefix)
    ]
    return root_files, has_subagents


def _reconstruct_subagent_layout(
    saved_files: list[tuple[str, Path]], tmp_dir: Path, settings: "Settings"
) -> None:
    """Reconstruct Claude Code directory layout for sub-agent parsing.

    Creates {session_id}/subagents/agent-*.jsonl structure so that
    ClaudeCodeParser.parse_session_with_subagents() can discover them.

    Args:
        saved_files: All saved files including sub-agent files.
        tmp_dir: Temp directory containing the files.
        settings: Application settings.
    """
    prefix = settings.subagent_file_prefix
    main_file: Path | None = None
    agent_files: list[Path] = []

    for name, path in saved_files:
        if Path(name).stem.startswith(prefix):
            agent_files.append(path)
        else:
            main_file = path

    if not main_file or not agent_files:
        return

    session_id = main_file.stem
    subagent_dir = tmp_dir / session_id / "subagents"
    subagent_dir.mkdir(parents=True, exist_ok=True)

    for agent_path in agent_files:
        dest = subagent_dir / agent_path.name
        shutil.move(str(agent_path), str(dest))


async def _parse_and_store(
    root_files: list[tuple[str, Path]],
    has_subagents: bool,
    result: UploadResult,
    settings: "Settings",
    token: str = "",
) -> None:
    """Parse each root file and store sessions.

    Args:
        root_files: List of (filename, path) for non-agent files.
        has_subagents: Whether sub-agent files were uploaded alongside.
        result: UploadResult to update with counts.
        settings: Application settings.
        token: Client isolation token for demo mode.
    """
    for filename, file_path in root_files:
        try:
            parsed = _parse_file(file_path, has_subagents, settings)
        except ValueError as exc:
            result.errors.append({"filename": filename, "error": str(exc)})
            continue

        for summary, messages in parsed:
            summary.source_type = DataSourceType.UPLOAD
            summary.source_name = filename
            stored = await _store_session(summary, messages, token)
            if stored:
                result.sessions_parsed += 1
                result.messages_stored += len(messages)
            else:
                result.skipped += 1


def _parse_file(
    file_path: Path, has_subagents: bool, settings: "Settings"
) -> list[tuple[SessionSummary, list[Message]]]:
    """Parse a file using auto-detection, with sub-agent support for Claude Code.

    Args:
        file_path: Path to the file to parse.
        has_subagents: Whether to attempt sub-agent parsing.
        settings: Application settings.

    Returns:
        List of (SessionSummary, messages) tuples.

    Raises:
        ValueError: If format cannot be detected.
    """
    matches = fingerprint_file(file_path)
    if not matches or matches[0].confidence < settings.min_confidence:
        _raise_detection_error(file_path, matches)

    best_match = matches[0]
    is_claude_code = best_match.format_name == "claude_code"

    if is_claude_code and has_subagents:
        return _parse_claude_code_with_subagents(file_path)

    return parse_auto(file_path)


def _raise_detection_error(file_path: Path, matches: list[FormatMatch]) -> None:
    """Raise a ValueError with format detection details.

    Args:
        file_path: Path that failed detection.
        matches: Any partial matches found.
    """
    best = f"{matches[0].format_name} ({matches[0].confidence:.2f})" if matches else "none"
    raise ValueError(f"Cannot auto-detect format for {file_path.name}: best match {best}")


def _parse_claude_code_with_subagents(
    file_path: Path,
) -> list[tuple[SessionSummary, list[Message]]]:
    """Parse a Claude Code file with sub-agent support.

    Args:
        file_path: Path to the main session .jsonl file.

    Returns:
        Single-element list of (SessionSummary, messages).
    """
    parser = ClaudeCodeParser()
    return parser.parse_file(file_path)


async def _store_session(
    summary: SessionSummary, messages: list[Message], token: str = ""
) -> bool:
    """Store a parsed session via the active session store.

    In demo mode, routes through the SessionStore (memory or sqlite).
    In self-use mode, uses SQLite directly for backward compatibility.

    Args:
        summary: Session summary to store.
        messages: Messages belonging to the session.
        token: Client isolation token for demo mode.

    Returns:
        True if stored, False if skipped (duplicate).
    """
    if is_demo_mode():
        store = get_session_store()
        return await store.store_session(summary, messages, token)

    conn = await get_connection()
    try:
        inserted = await insert_session(conn, summary)
        if not inserted:
            return False
        await insert_messages(conn, messages)
        await conn.commit()
        return True
    finally:
        await conn.close()
