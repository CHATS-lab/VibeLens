"""Zip archive validation and safe extraction utilities."""

import zipfile
from pathlib import Path

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Extensions safe to extract from user-uploaded zips.
# .project_root is a Gemini CLI marker file that maps hash dirs to projects.
ALLOWED_EXTENSIONS = {".json", ".jsonl", ".project_root", ".txt"}

# Unix file-type mask and symlink value for external_attr inspection
UNIX_FILE_TYPE_MASK = 0o170000
UNIX_SYMLINK_TYPE = 0o120000


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
        if ".." in info.filename or info.filename.startswith("/"):
            raise ValueError(f"Path traversal detected: {info.filename}")

        # Detect symlinks via Unix file type bits in external_attr upper 16 bits
        unix_mode = info.external_attr >> 16
        if (unix_mode & UNIX_FILE_TYPE_MASK) == UNIX_SYMLINK_TYPE:
            raise ValueError(f"Symlink detected: {info.filename}")

        if info.is_dir():
            continue

        # Only count files with parseable extensions toward the budget
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
