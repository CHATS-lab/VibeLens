"""Donation receiver — store incoming ZIP archives and maintain an index.

Used in demo mode to accept donation ZIPs from self-use VibeLens instances,
persist them on disk, and record metadata in an append-only index.
"""

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile

from vibelens.deps import get_settings
from vibelens.services.upload.processor import generate_upload_id
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

INDEX_FILENAME = "index.jsonl"
MANIFEST_FILENAME = "manifest.json"


async def receive_donation(file: UploadFile) -> dict:
    """Receive and store a donated ZIP archive from a self-use instance.

    Streams the ZIP to the donation directory, reads its manifest,
    and appends an entry to the donation index.

    Args:
        file: Uploaded ZIP file from the sender.

    Returns:
        Dict with upload_id and session count on success.

    Raises:
        HTTPException: If the file is not a valid ZIP or exceeds limits.
    """
    settings = get_settings()
    donation_dir = settings.donation_dir
    donation_dir.mkdir(parents=True, exist_ok=True)

    upload_id = generate_upload_id()
    zip_filename = f"{upload_id}.zip"
    zip_path = donation_dir / zip_filename

    # Stream ZIP to disk with bounded memory usage
    total_written = await _stream_to_disk(file, zip_path, settings.max_zip_bytes)

    # Read manifest from the ZIP without full extraction
    manifest = _read_manifest(zip_path)

    # Append entry to the donation index
    index_entry = {
        "upload_id": upload_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "zip_filename": zip_filename,
        "zip_size_bytes": total_written,
        "sessions": manifest.get("sessions", []),
        "vibelens_version": manifest.get("vibelens_version"),
    }
    _append_to_index(donation_dir, index_entry)

    session_count = len(manifest.get("sessions", []))
    logger.info(
        "Received donation %s: %d sessions, %d bytes", upload_id, session_count, total_written
    )
    return {"upload_id": upload_id, "session_count": session_count, "zip_size_bytes": total_written}


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


def _read_manifest(zip_path: Path) -> dict:
    """Read manifest.json from a donation ZIP without full extraction.

    Args:
        zip_path: Path to the ZIP file.

    Returns:
        Parsed manifest dict, or empty dict if manifest is missing.

    Raises:
        HTTPException: If the file is not a valid ZIP.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if MANIFEST_FILENAME not in zf.namelist():
                logger.warning("Donation ZIP %s has no manifest", zip_path.name)
                return {}
            manifest_bytes = zf.read(MANIFEST_FILENAME)
            return json.loads(manifest_bytes.decode("utf-8"))
    except zipfile.BadZipFile:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Invalid manifest in %s: %s", zip_path.name, exc)
        return {}


def _append_to_index(donation_dir: Path, entry: dict) -> None:
    """Append a donation entry to the index.jsonl file.

    Args:
        donation_dir: Directory containing the donation index.
        entry: Donation metadata dict to append.
    """
    index_path = donation_dir / INDEX_FILENAME
    line = json.dumps(entry, default=str, ensure_ascii=False)
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
