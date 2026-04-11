"""Donation receiver — store incoming ZIP archives and maintain an index.

Used in demo mode to accept donation ZIPs from self-use VibeLens instances,
persist them on disk, and record metadata in an append-only index.

Supports both new-format ZIPs (wrapping directory with manifest inside)
and legacy ZIPs (root-level manifest.json) for backward compatibility.
"""

import asyncio
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile

from vibelens.deps import get_settings
from vibelens.utils.identifiers import generate_timestamped_id
from vibelens.utils.json import locked_jsonl_append
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Append-only log of received donations in the donation directory
INDEX_FILENAME = "index.jsonl"
# Metadata file inside each donated ZIP describing its contents
MANIFEST_FILENAME = "manifest.json"


async def receive_donation(file: UploadFile) -> dict:
    """Receive and store a donated ZIP archive from a self-use instance.

    Streams the ZIP to a temp path, reads the manifest to extract the
    donation_id (falling back to a generated ID for legacy ZIPs), renames
    to ``{donation_id}.zip``, and appends an entry to the donation index.

    Args:
        file: Uploaded ZIP file from the sender.

    Returns:
        Dict with donation_id and session count on success.

    Raises:
        HTTPException: If the file is not a valid ZIP or exceeds limits.
    """
    settings = get_settings()
    donation_dir = settings.donation_dir
    donation_dir.mkdir(parents=True, exist_ok=True)

    # Stream to a temp path first, then rename after reading manifest
    temp_id = generate_timestamped_id()
    temp_path = donation_dir / f"_tmp_{temp_id}.zip"

    total_written = await _stream_to_disk(file, temp_path, settings.max_zip_bytes)

    # Offloaded to thread pool -- ZIP reading is blocking I/O
    manifest = await asyncio.to_thread(_read_manifest, temp_path)

    # Use donation_id from manifest if present (new format), else generate one
    donation_id = manifest.get("donation_id") or generate_timestamped_id()
    zip_filename = f"{donation_id}.zip"
    zip_path = donation_dir / zip_filename

    # Rename temp file to final path
    temp_path.rename(zip_path)

    index_entry = {
        "donation_id": donation_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "zip_filename": zip_filename,
        "zip_size_bytes": total_written,
        "sessions": manifest.get("sessions", []),
        "vibelens_version": manifest.get("vibelens_version"),
    }
    # Append a donation entry to the index.jsonl file
    # (offloaded to thread pool -- file lock can block under contention)
    await asyncio.to_thread(
        locked_jsonl_append, path=donation_dir / INDEX_FILENAME, data=index_entry
    )

    session_count = len(manifest.get("sessions", []))
    logger.info(
        "Received donation %s: %d sessions, %d bytes", donation_id, session_count, total_written
    )
    return {
        "donation_id": donation_id,
        "session_count": session_count,
        "zip_size_bytes": total_written,
    }


async def _stream_to_disk(file: UploadFile, dest: Path, max_bytes: int) -> int:
    """Stream uploaded file to disk with size limits.

    Args:
        file: Uploaded file.
        dest: Destination file path.
        max_bytes: Maximum allowed file size.

    Returns:
        Total bytes written.

    Raises:
        HTTPException: If file exceeds size limit.
    """
    CHUNK_SIZE = 64 * 1024
    total_written = 0

    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total_written += len(chunk)
            if total_written > max_bytes:
                dest.unlink(missing_ok=True)
                max_mb = max_bytes // (1024 * 1024)
                raise HTTPException(
                    status_code=400, detail=f"Donation ZIP exceeds {max_mb} MB limit"
                )
            f.write(chunk)

    return total_written


def _find_manifest_in_zip(names: list[str]) -> str | None:
    """Find manifest.json in a ZIP, checking both root and one-level deep.

    Supports new-format ZIPs (``{donation_id}/manifest.json``) and
    legacy ZIPs (root ``manifest.json``).

    Args:
        names: List of file names in the ZIP archive.

    Returns:
        The manifest path within the ZIP, or None if not found.
    """
    # Root-level manifest (legacy format)
    if MANIFEST_FILENAME in names:
        return MANIFEST_FILENAME

    # One-level deep manifest (new wrapping directory format)
    for name in names:
        parts = name.split("/")
        if len(parts) == 2 and parts[1] == MANIFEST_FILENAME:
            return name

    return None


def _read_manifest(zip_path: Path) -> dict:
    """Read manifest.json from a donation ZIP without full extraction.

    Searches for manifest at both root level and one directory deep
    for backward compatibility with legacy donation ZIPs.

    Args:
        zip_path: Path to the ZIP file.

    Returns:
        Parsed manifest dict, or empty dict if manifest is missing.

    Raises:
        HTTPException: If the file is not a valid ZIP.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest_path = _find_manifest_in_zip(zf.namelist())
            if not manifest_path:
                logger.warning("Donation ZIP %s has no manifest", zip_path.name)
                return {}
            manifest_bytes = zf.read(manifest_path)
            return json.loads(manifest_bytes.decode("utf-8"))
    except zipfile.BadZipFile:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Invalid manifest in %s: %s", zip_path.name, exc)
        return {}
