"""Zip archive validation, extraction, and session file discovery."""

import zipfile
from pathlib import Path

from vibelens.models.enums import AgentType
from vibelens.utils import get_logger

logger = get_logger(__name__)

# Extensions safe to extract from user-uploaded zips.
# .project_root is a Gemini CLI marker file that maps hash dirs to projects.
ALLOWED_EXTENSIONS = {".json", ".jsonl", ".project_root", ".txt"}

# Claude Code names sub-agent session files with this prefix
# (e.g. agent-0.jsonl, agent-1.jsonl). These are discovered by
# ClaudeCodeParser from directory layout, not listed as root sessions.
SUBAGENT_FILE_PREFIX = "agent-"


def validate_zip(
    zip_path: Path, max_zip_bytes: int, max_extracted_bytes: int, max_file_count: int
) -> None:
    """Validate a zip archive for size, safety, and content constraints.

    Checks file size on disk, scans for path traversal and symlinks,
    enforces total extracted size and file count limits, and filters
    by extension allowlist.

    Args:
        zip_path: Path to the zip file.
        max_zip_bytes: Maximum allowed zip file size.
        max_extracted_bytes: Maximum total uncompressed size.
        max_file_count: Maximum number of files in the archive.

    Raises:
        ValueError: If any validation check fails.
    """
    file_size = zip_path.stat().st_size
    if file_size > max_zip_bytes:
        raise ValueError(f"Zip file exceeds size limit: {file_size} bytes > {max_zip_bytes} bytes")

    if not zipfile.is_zipfile(zip_path):
        raise ValueError("File is not a valid zip archive")

    with zipfile.ZipFile(zip_path, "r") as zf:
        _check_zip_entries(zf, max_extracted_bytes, max_file_count)


def _check_zip_entries(zf: zipfile.ZipFile, max_extracted_bytes: int, max_file_count: int) -> None:
    """Scan zip entries for safety and size constraints.

    Args:
        zf: Open ZipFile to inspect.
        max_extracted_bytes: Maximum total uncompressed size.
        max_file_count: Maximum file count.

    Raises:
        ValueError: On path traversal, symlinks, size, or count violations.
    """
    total_size = 0
    file_count = 0

    for info in zf.infolist():
        # Guard against zip-slip: reject paths that escape the extraction root
        # via ".." segments or absolute paths starting with "/"
        if ".." in info.filename or info.filename.startswith("/"):
            raise ValueError(f"Path traversal detected: {info.filename}")

        # Detect symlinks by inspecting the Unix file type bits stored in
        # external_attr. The upper 16 bits hold the Unix st_mode; masking
        # with 0o170000 isolates the file-type nibble, and 0o120000 = symlink.
        unix_mode = info.external_attr >> 16
        is_symlink = (unix_mode & 0o170000) == 0o120000
        if is_symlink:
            raise ValueError(f"Symlink detected: {info.filename}")

        if info.is_dir():
            continue

        # Only count files with parseable extensions toward the size/count
        # budget; other files are silently skipped during extraction too.
        suffix = Path(info.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            continue

        total_size += info.file_size
        file_count += 1

    if total_size > max_extracted_bytes:
        raise ValueError(
            f"Extracted size exceeds limit: {total_size} bytes > {max_extracted_bytes} bytes"
        )

    if file_count > max_file_count:
        raise ValueError(f"Too many files: {file_count} > {max_file_count}")


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract a validated zip archive to the destination directory.

    Only extracts files with allowed extensions, skipping others.

    Args:
        zip_path: Path to the zip file.
        dest_dir: Directory to extract into.

    Returns:
        The destination directory path.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in ALLOWED_EXTENSIONS:
                continue
            zf.extract(info, dest_dir)

    logger.info("Extracted zip to %s", dest_dir)
    return dest_dir


def discover_session_files(extracted_dir: Path, agent_type: str) -> list[Path]:
    """Walk extracted directory and return parseable session file paths.

    Filters files based on agent-specific naming conventions.
    Sub-agent files (agent-*.jsonl) are excluded since parsers
    discover them from the directory layout.

    Args:
        extracted_dir: Root of the extracted zip contents.
        agent_type: One of AgentType values.

    Returns:
        List of paths to parseable session files.
    """
    agent = AgentType(agent_type)

    if agent == AgentType.CLAUDE_CODE:
        return _discover_claude_code(extracted_dir)
    if agent == AgentType.CODEX:
        return _discover_codex(extracted_dir)
    return _discover_gemini(extracted_dir)


def _discover_claude_code(extracted_dir: Path) -> list[Path]:
    """Find Claude Code session files, excluding sub-agent files."""
    files = sorted(extracted_dir.rglob("*.jsonl"))
    return [f for f in files if not f.stem.startswith(SUBAGENT_FILE_PREFIX)]


def _discover_codex(extracted_dir: Path) -> list[Path]:
    """Find Codex rollout session files."""
    return sorted(f for f in extracted_dir.rglob("*.jsonl") if f.stem.startswith("rollout-"))


def _discover_gemini(extracted_dir: Path) -> list[Path]:
    """Find Gemini session files inside chats/ directories."""
    return sorted(f for f in extracted_dir.rglob("session-*.json") if "chats" in f.parts)
