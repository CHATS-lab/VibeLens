"""Centralized logging configuration for VibeLens.

Two-phase design:
  - ``get_logger`` is safe at import time. First call attaches a stderr
    handler to the ``vibelens`` root logger so early logs appear somewhere.
  - ``configure_logging(LoggingConfig)`` runs once from the app entry point
    and attaches file handlers (``vibelens.log``, ``errors.log``), per-domain
    handlers (``{domain}.log``), applies per-domain level overrides, and
    emits a startup summary.

Domain routing is driven by ``DOMAIN_PREFIXES``: first matching prefix wins.
"""

import logging
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibelens.config.settings import LoggingConfig

# Format string for all log handlers
LOG_FORMAT = "%(asctime)s | %(name)s:%(lineno)d | %(levelname)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_analysis_id_var: ContextVar[str | None] = ContextVar("analysis_id", default=None)


# Domain -> prefixes that route to logs/{domain}.log.
# Order matters: more specific prefixes first.
DOMAIN_PREFIXES: dict[str, tuple[str, ...]] = {
    "parsers": ("vibelens.ingest.parsers.",),
    "ingest": ("vibelens.ingest.",),
    "creation": ("vibelens.services.creation.", "vibelens.api.creation"),
    "evolution": ("vibelens.services.evolution.", "vibelens.api.evolution"),
    "recommendation": ("vibelens.services.recommendation.", "vibelens.api.recommendation"),
    "personalization": ("vibelens.services.personalization.",),
    "friction": ("vibelens.services.friction.", "vibelens.api.friction"),
    "donation": (
        "vibelens.services.donation.",
        "vibelens.api.donation",
        "vibelens.services.session.donation",
    ),
    "upload": (
        "vibelens.services.upload.",
        "vibelens.api.upload",
        "vibelens.storage.conversation.disk",
    ),
    "extensions": (
        "vibelens.services.extensions.",
        "vibelens.storage.extension.",
        "vibelens.api.hook",
        "vibelens.api.skill",
        "vibelens.api.command",
        "vibelens.api.subagent",
        "vibelens.api.extensions",
    ),
    "dashboard": ("vibelens.services.dashboard.", "vibelens.api.dashboard"),
    "session": (
        "vibelens.services.session.",
        "vibelens.api.sessions",
        "vibelens.api.shares",
        "vibelens.storage.trajectory.",
    ),
    "llm": ("vibelens.llm.",),
}

_bootstrapped: bool = False
_configured: bool = False
_domain_handlers: dict[str, logging.Handler] = {}
_pending_loggers: set[str] = set()
_per_domain_levels: dict[str, int] = {}

# Rotation parameters read by handler builders; updated by configure_logging.
_current_max_bytes: int = 10 * 1024 * 1024
_current_backup_count: int = 3


class _AnalysisIdFormatter(logging.Formatter):
    """Formatter that prepends ``[analysis_id] `` when an analysis is running."""

    def format(self, record: logging.LogRecord) -> str:
        """Inject the active analysis_id into the message before formatting."""
        aid = _analysis_id_var.get(None)
        if aid:
            record.msg = f"[{aid}] {record.msg}"
        return super().format(record)


def set_analysis_id(analysis_id: str) -> None:
    """Set the current analysis_id for log correlation."""
    _analysis_id_var.set(analysis_id)


def clear_analysis_id() -> None:
    """Clear the current analysis_id after an analysis run completes."""
    _analysis_id_var.set(None)


def _build_formatter() -> logging.Formatter:
    """Create the shared log formatter with analysis_id injection."""
    return _AnalysisIdFormatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)


def _resolve_domain(name: str) -> str | None:
    """Return the domain for a logger name, or None if no domain matches.

    First match wins. Callers rely on DOMAIN_PREFIXES insertion order.
    """
    for domain, prefixes in DOMAIN_PREFIXES.items():
        for prefix in prefixes:
            if name.startswith(prefix):
                return domain
    return None


def _bootstrap_root() -> None:
    """Phase 1 — attach a stderr handler to the ``vibelens`` root once.

    Called lazily by ``get_logger`` so import-time logs still appear somewhere
    before ``configure_logging`` runs.
    """
    global _bootstrapped
    if _bootstrapped:
        return

    root = logging.getLogger("vibelens")
    root.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(_build_formatter())
    console._vl_bootstrap = True  # type: ignore[attr-defined]
    root.addHandler(console)

    _bootstrapped = True


def _find_bootstrap_stderr_handler() -> logging.Handler | None:
    """Return the bootstrap-tagged stderr handler on the root, or None."""
    root = logging.getLogger("vibelens")
    for handler in root.handlers:
        if getattr(handler, "_vl_bootstrap", False):
            return handler
    return None


def _handler_filename(handler: logging.Handler) -> str | None:
    """Return the basename of a handler's target file, or None if it has none."""
    base = getattr(handler, "baseFilename", None)
    if base is None:
        return None
    return Path(base).name


def _ensure_root_file_handlers(log_dir: Path, level: int) -> None:
    """Attach vibelens.log and errors.log to the root (idempotent by filename)."""
    root = logging.getLogger("vibelens")
    existing_files = {_handler_filename(h) for h in root.handlers}
    formatter = _build_formatter()

    if "vibelens.log" not in existing_files:
        overall = RotatingFileHandler(
            log_dir / "vibelens.log",
            maxBytes=_current_max_bytes,
            backupCount=_current_backup_count,
        )
        overall.setLevel(level)
        overall.setFormatter(formatter)
        root.addHandler(overall)

    if "errors.log" not in existing_files:
        errors = RotatingFileHandler(
            log_dir / "errors.log",
            maxBytes=_current_max_bytes,
            backupCount=_current_backup_count,
        )
        errors.setLevel(logging.WARNING)
        errors.setFormatter(formatter)
        root.addHandler(errors)


def _build_domain_handler(log_dir: Path, domain: str, level: int) -> logging.Handler:
    """Create and cache a ``{domain}.log`` rotating handler."""
    if domain in _domain_handlers:
        return _domain_handlers[domain]
    handler = RotatingFileHandler(
        log_dir / f"{domain}.log",
        maxBytes=_current_max_bytes,
        backupCount=_current_backup_count,
    )
    handler.setLevel(level)
    handler.setFormatter(_build_formatter())
    _domain_handlers[domain] = handler
    return handler


def _attach_domain_handler_for(logger: logging.Logger) -> None:
    """Attach the matched domain handler to ``logger`` and apply level override."""
    if getattr(logger, "_vl_domain_attached", False):
        return
    domain = _resolve_domain(logger.name)
    if domain is None:
        return
    handler = _domain_handlers.get(domain)
    if handler is None:
        return
    logger.addHandler(handler)
    logger._vl_domain_attached = True  # type: ignore[attr-defined]
    override = _per_domain_levels.get(domain)
    if override is not None:
        logger.setLevel(override)


def configure_logging(config: "LoggingConfig") -> None:
    """Phase 2 — attach file handlers, apply per-domain levels, emit summary.

    Idempotent: repeat calls update levels but do not duplicate handlers.
    Safe to call after any number of ``get_logger`` calls; pending loggers
    are retroactively wired.

    Args:
        config: Active logging configuration loaded from settings.
    """
    global _configured, _current_max_bytes, _current_backup_count

    _bootstrap_root()
    log_dir = Path(config.dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    level = logging.getLevelName(config.level)
    assert isinstance(level, int), f"Invalid log level: {config.level}"
    _current_max_bytes = config.max_bytes
    _current_backup_count = config.backup_count

    root = logging.getLogger("vibelens")
    root.setLevel(level)

    bootstrap_handler = _find_bootstrap_stderr_handler()
    if bootstrap_handler is not None:
        bootstrap_handler.setLevel(level)

    _ensure_root_file_handlers(log_dir, level)

    _per_domain_levels.clear()
    for domain, level_name in config.per_domain.items():
        _per_domain_levels[domain] = logging.getLevelName(level_name)

    for domain in DOMAIN_PREFIXES:
        handler_level = _per_domain_levels.get(domain, level)
        _build_domain_handler(log_dir, domain, handler_level)
        # If the handler already existed from a prior call, update its level.
        _domain_handlers[domain].setLevel(handler_level)

    # Retroactively wire loggers obtained before configure_logging ran.
    for name in list(_pending_loggers):
        logger = logging.getLogger(name)
        _attach_domain_handler_for(logger)
    _pending_loggers.clear()

    _configured = True
    _emit_startup_summary(config=config, log_dir=log_dir, level=level)


def _emit_startup_summary(config: "LoggingConfig", log_dir: Path, level: int) -> None:
    """Log one INFO line summarizing the active configuration."""
    overrides = ", ".join(f"{d}={lv}" for d, lv in config.per_domain.items()) or "none"
    size_mb = config.max_bytes // (1024 * 1024)
    summary = (
        f"Logging configured: level={logging.getLevelName(level)} "
        f"dir={log_dir} rotation={size_mb}MB x{config.backup_count} "
        f"domains={len(DOMAIN_PREFIXES)} overrides={overrides}"
    )
    logging.getLogger("vibelens").info(summary)


def _module_name_from_path(filepath: str) -> str:
    """Derive a dotted module name from a file path under ``src/``.

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


def get_logger(name: str, filepath: str | None = None) -> logging.Logger:
    """Return a logger under the ``vibelens.*`` hierarchy.

    Safe to call at import time. Before ``configure_logging`` runs, logs go to
    stderr only; after, each matching domain logger also writes to
    ``{domain}.log`` in the configured directory.

    Args:
        name: Logger name (typically ``__name__`` of the calling module).
        filepath: Optional ``__file__`` of the caller. Used to derive a
            readable name when ``name`` is ``"__main__"``.

    Returns:
        Configured logger. Propagates to the ``vibelens`` root.
    """
    if name == "__main__" and filepath:
        name = _module_name_from_path(filepath)

    _bootstrap_root()
    logger = logging.getLogger(name)

    if _configured:
        _attach_domain_handler_for(logger)
    elif _resolve_domain(name) is not None:
        _pending_loggers.add(name)

    return logger
