"""Centralized logging configuration for VibeLens."""

import logging
import os
import sys
from datetime import datetime
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
    """Create a named logger with consistent formatting.

    When *name* is ``"__main__"`` (i.e. the script is run directly),
    the logger name is derived from *filepath* so that output shows
    ``vibelens.ingest.claude_code`` instead of ``__main__``.

    The log level defaults to INFO but can be overridden by setting the
    ``LOG_LEVEL`` environment variable (e.g. ``LOG_LEVEL=DEBUG``).

    Args:
        name: Logger name (typically ``__name__`` of the calling module).
        filepath: Optional ``__file__`` of the calling module. Used to
            derive a readable name when *name* is ``"__main__"``.
        log_dir: Optional directory for log files. When provided, adds
            an append-mode ``{name}.log`` and a timestamped
            ``{name}_{ts}.log`` file handler.

    Returns:
        Configured logger that writes to stderr with timestamp + level.
    """
    if name == "__main__" and filepath:
        name = _module_name_from_path(filepath)

    logger = logging.getLogger(name)
    if not logger.handlers:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, level, logging.INFO)
        logger.setLevel(log_level)

        formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        logger.addHandler(console)

        if log_dir is None:
            log_dir = DEFAULT_LOG_DIR
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        short_name = name.rsplit(".", 1)[-1]

        file_handler = logging.FileHandler(log_dir / f"{short_name}.log")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ts_handler = logging.FileHandler(log_dir / f"{short_name}_{ts}.log")
        ts_handler.setLevel(logging.DEBUG)
        ts_handler.setFormatter(formatter)
        logger.addHandler(ts_handler)

    return logger
