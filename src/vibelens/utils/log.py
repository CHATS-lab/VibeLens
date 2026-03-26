"""Centralized logging configuration for VibeLens.

Two-tier logging architecture:
  - **Overall logger**: ``vibelens`` root logger writes ALL messages to
    ``logs/vibelens.log`` and stderr — a single place to see everything.
  - **Category loggers**: Specific modules get additional file handlers
    that aggregate related output into category log files.

Category log files:
  - ``parsers.log`` — all parser modules under ``vibelens.ingest.parsers.*``
  - ``analysis-friction.log`` — friction analysis and friction store
  - ``analysis-skill.log`` — skill analysis and skill analysis store
"""

import logging
import os
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(name)s:%(lineno)d | %(levelname)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[3] / "logs"

# Maps logger name prefix → log filename. Order matters: first match wins.
# Prefix matching allows grouping related modules into one log file.
CATEGORY_LOG_FILES: dict[str, str] = {
    "vibelens.ingest.parsers.": "parsers.log",
    "vibelens.services.friction.": "analysis-friction.log",
    "vibelens.services.skill.analysis": "analysis-skill.log",
}

_root_configured = False
_category_handlers: dict[str, logging.FileHandler] = {}


def _get_log_level() -> int:
    """Read log level from LOG_LEVEL env var, defaulting to INFO."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def _build_formatter() -> logging.Formatter:
    """Create the shared log formatter."""
    return logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)


def _ensure_root_logger(log_dir: Path) -> None:
    """Configure the ``vibelens`` root logger once.

    Adds a stderr console handler and a single ``vibelens.log`` file
    handler so every child logger's output is captured in one place.

    Args:
        log_dir: Directory for the overall log file.
    """
    global _root_configured
    if _root_configured:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    log_level = _get_log_level()
    formatter = _build_formatter()

    root = logging.getLogger("vibelens")
    root.setLevel(log_level)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(log_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    overall_file = logging.FileHandler(log_dir / "vibelens.log", mode="a")
    overall_file.setLevel(log_level)
    overall_file.setFormatter(formatter)
    root.addHandler(overall_file)

    _root_configured = True


def _resolve_category_log(name: str) -> str | None:
    """Find the category log filename for a logger name, if any."""
    for prefix, filename in CATEGORY_LOG_FILES.items():
        if name.startswith(prefix):
            return filename
    return None


def _get_category_handler(log_dir: Path, filename: str) -> logging.FileHandler:
    """Get or create a shared file handler for a category log file.

    Multiple modules sharing the same category (e.g. all parsers → parsers.log)
    reuse a single FileHandler to avoid duplicate writes.

    Args:
        log_dir: Directory for log files.
        filename: Category log filename (e.g. "parsers.log").

    Returns:
        Shared FileHandler for the category.
    """
    if filename in _category_handlers:
        return _category_handlers[filename]

    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / filename, mode="a")
    handler.setLevel(_get_log_level())
    handler.setFormatter(_build_formatter())
    _category_handlers[filename] = handler
    return handler


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
    """Create a named logger under the ``vibelens`` hierarchy.

    All loggers propagate to the ``vibelens`` root logger which writes
    to stderr and ``logs/vibelens.log``. Modules matching a category
    prefix in CATEGORY_LOG_FILES additionally write to a shared
    category log file (e.g. ``logs/parsers.log``).

    Args:
        name: Logger name (typically ``__name__`` of the calling module).
        filepath: Optional ``__file__`` of the calling module. Used to
            derive a readable name when *name* is ``"__main__"``.
        log_dir: Directory for log files. Defaults to ``logs/`` next
            to the project root.

    Returns:
        Configured logger that writes to stderr and the overall log file,
        plus a category file for matched modules.
    """
    if name == "__main__" and filepath:
        name = _module_name_from_path(filepath)

    resolved_log_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    _ensure_root_logger(resolved_log_dir)

    logger = logging.getLogger(name)

    category_file = _resolve_category_log(name)
    if category_file and not logger.handlers:
        handler = _get_category_handler(resolved_log_dir, category_file)
        logger.addHandler(handler)

    return logger
