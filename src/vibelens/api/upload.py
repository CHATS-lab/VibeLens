"""File upload endpoints for importing agent conversation files."""

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile

from vibelens.db import (
    get_connection,
    insert_messages,
    insert_session,
)
from vibelens.ingest.fingerprint import FormatMatch, fingerprint_file, parse_auto
from vibelens.ingest.parsers.claude_code import ClaudeCodeParser
from vibelens.models.message import Message
from vibelens.models.requests import UploadResult
from vibelens.models.session import DataSourceType, SessionSummary
from vibelens.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["upload"])

ALLOWED_EXTENSIONS = {".json", ".jsonl"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
SUBAGENT_FILE_PREFIX = "agent-"
MIN_CONFIDENCE = 0.5


@router.post("/upload")
async def upload_files(files: list[UploadFile]) -> UploadResult:
    """Upload conversation files for parsing and storage.

    Accepts .json and .jsonl files from any supported agent format.
    Auto-detects format, parses sessions, and stores in SQLite.

    Args:
        files: List of uploaded files.

    Returns:
        UploadResult with counts and any errors.
    """
    result = UploadResult(files_received=len(files))
    tmp_dir = Path(tempfile.mkdtemp(prefix="vibelens_upload_"))

    try:
        saved_files = await _save_uploaded_files(files, tmp_dir, result)
        if not saved_files:
            return result

        root_files, has_subagents = _classify_files(saved_files)
        if has_subagents:
            _reconstruct_subagent_layout(saved_files, tmp_dir)

        await _parse_and_store(root_files, has_subagents, result)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


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
    files: list[UploadFile], tmp_dir: Path, result: UploadResult
) -> list[tuple[str, Path]]:
    """Validate and save uploaded files to the temp directory.

    Args:
        files: Uploaded files from the request.
        tmp_dir: Temporary directory to write files into.
        result: UploadResult to record errors.

    Returns:
        List of (original_filename, saved_path) tuples.
    """
    saved: list[tuple[str, Path]] = []
    for upload_file in files:
        filename = upload_file.filename or "unknown"
        suffix = Path(filename).suffix.lower()

        if suffix not in ALLOWED_EXTENSIONS:
            result.errors.append({"filename": filename, "error": "Unsupported file type"})
            continue

        content = await upload_file.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            result.errors.append({"filename": filename, "error": "File exceeds 50 MB limit"})
            continue

        dest = tmp_dir / filename
        dest.write_bytes(content)
        saved.append((filename, dest))

    return saved


def _classify_files(
    saved_files: list[tuple[str, Path]],
) -> tuple[list[tuple[str, Path]], bool]:
    """Separate root files from sub-agent files.

    Args:
        saved_files: List of (filename, path) tuples.

    Returns:
        Tuple of (root_files, has_subagents).
    """
    has_subagents = any(
        Path(name).stem.startswith(SUBAGENT_FILE_PREFIX)
        for name, _ in saved_files
    )
    root_files = [
        (name, path)
        for name, path in saved_files
        if not Path(name).stem.startswith(SUBAGENT_FILE_PREFIX)
    ]
    return root_files, has_subagents


def _reconstruct_subagent_layout(
    saved_files: list[tuple[str, Path]], tmp_dir: Path
) -> None:
    """Reconstruct Claude Code directory layout for sub-agent parsing.

    Creates {session_id}/subagents/agent-*.jsonl structure so that
    ClaudeCodeParser.parse_session_with_subagents() can discover them.

    Args:
        saved_files: All saved files including sub-agent files.
        tmp_dir: Temp directory containing the files.
    """
    # Find the main session file (non-agent file)
    main_file: Path | None = None
    agent_files: list[Path] = []

    for name, path in saved_files:
        if Path(name).stem.startswith(SUBAGENT_FILE_PREFIX):
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
    root_files: list[tuple[str, Path]], has_subagents: bool, result: UploadResult
) -> None:
    """Parse each root file and store sessions in SQLite.

    Args:
        root_files: List of (filename, path) for non-agent files.
        has_subagents: Whether sub-agent files were uploaded alongside.
        result: UploadResult to update with counts.
    """
    for filename, file_path in root_files:
        try:
            parsed = _parse_file(file_path, has_subagents)
        except ValueError as exc:
            result.errors.append({"filename": filename, "error": str(exc)})
            continue

        for summary, messages in parsed:
            summary.source_type = DataSourceType.UPLOAD
            summary.source_name = filename
            stored = await _store_session(summary, messages)
            if stored:
                result.sessions_parsed += 1
                result.messages_stored += len(messages)
            else:
                result.skipped += 1


def _parse_file(
    file_path: Path, has_subagents: bool
) -> list[tuple[SessionSummary, list[Message]]]:
    """Parse a file using auto-detection, with sub-agent support for Claude Code.

    Args:
        file_path: Path to the file to parse.
        has_subagents: Whether to attempt sub-agent parsing.

    Returns:
        List of (SessionSummary, messages) tuples.

    Raises:
        ValueError: If format cannot be detected.
    """
    matches = fingerprint_file(file_path)
    if not matches or matches[0].confidence < MIN_CONFIDENCE:
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


async def _store_session(summary: SessionSummary, messages: list[Message]) -> bool:
    """Store a parsed session and its messages in SQLite.

    Args:
        summary: Session summary to store.
        messages: Messages belonging to the session.

    Returns:
        True if stored, False if skipped (duplicate).
    """
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
