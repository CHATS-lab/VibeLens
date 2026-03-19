"""Centralized logging configuration for VibeLens."""

import logging
import os
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(name)s:%(lineno)d | %(levelname)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[3] / "logs"


def _module_name_from_path(filepath: str) -> str:
    """Derive a dotted module name from a file path.

    Strips the ``src/`` prefix and ``.py`` suffix so that
    ``src/vibelens/ingest/claude_code.py`` becomes
    ``vibelens.ingest.claude_code``.
    """
    p = Path(filepath).resolve()
    parts = p.with_suffix("").parts
    try:
        src_idx = parts.index("src")
        parts = parts[src_idx + 1 :]
    except ValueError:
        pass
    return ".".join(parts[-3:]) if len(parts) > 3 else ".".join(parts)


def get_logger(
    name: str, filepath: str | None = None, log_dir: str | Path | None = None
) -> logging.Logger:
    """Create a named logger with a single per-module log file.

    Each module gets one log file (e.g. ``logs/disk.log``) that is
    overwritten on each server restart to prevent unbounded growth.

    Args:
        name: Logger name (typically ``__name__`` of the calling module).
        filepath: Optional ``__file__`` of the calling module. Used to
            derive a readable name when *name* is ``"__main__"``.
        log_dir: Directory for log files. Defaults to ``logs/`` next
            to the project root.

    Returns:
        Configured logger that writes to stderr and a per-module file.
    """
    if name == "__main__" and filepath:
        name = _module_name_from_path(filepath)

    logger = logging.getLogger(name)
    if not logger.handlers:
        level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, level_name, logging.INFO)
        logger.setLevel(log_level)

        formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        logger.addHandler(console)

        log_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        short_name = name.rsplit(".", 1)[-1]

        # Single file per module, overwritten each run
        file_handler = logging.FileHandler(log_dir / f"{short_name}.log", mode="w")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
