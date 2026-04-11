"""Timestamp parsing and formatting utilities."""

import math
import time
from datetime import UTC, datetime

# Numeric values above this threshold are treated as millisecond-epoch;
# below it they are treated as second-epoch.  The boundary corresponds
# roughly to 2001-09-09 in seconds but 1970-01-12 in milliseconds.
EPOCH_MS_THRESHOLD = 1_000_000_000_000

# No AI coding agent existed before 2015; timestamps before this are bogus.
MIN_VALID_EPOCH = 1_420_070_400  # 2015-01-01T00:00:00Z

# Timestamps beyond 2035 are almost certainly malformed data.
MAX_VALID_EPOCH = 2_051_222_400  # 2035-01-01T00:00:00Z


def _validate_range(dt: datetime) -> datetime | None:
    """Return dt only if it falls within the valid agent-era range.

    Args:
        dt: Datetime to validate.

    Returns:
        The datetime if in range, or None if out of bounds.
    """
    epoch = dt.timestamp()
    if epoch < MIN_VALID_EPOCH or epoch > MAX_VALID_EPOCH:
        return None
    return dt


def _is_finite(value: int | float) -> bool:
    """Check whether a numeric value is finite (not inf, -inf, or NaN).

    Args:
        value: Numeric value to check.

    Returns:
        True if value is finite.
    """
    return not (math.isinf(value) or math.isnan(value))


def parse_iso_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string to a UTC datetime.

    Adds UTC timezone if the parsed datetime is naive.

    Args:
        value: ISO-8601 formatted string, or None.

    Returns:
        UTC-aware datetime, or None if parsing fails or out of range.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return _validate_range(dt)
    except (ValueError, TypeError):
        return None


def normalize_timestamp(value: int | float | str | None) -> datetime | None:
    """Auto-detect and parse a timestamp from any common format.

    Handles None, ISO-8601 strings, millisecond-epoch, and second-epoch
    numeric values. Numeric values above ``EPOCH_MS_THRESHOLD`` are treated
    as milliseconds; below it as seconds.

    Args:
        value: Timestamp in any supported format, or None.

    Returns:
        UTC-aware datetime, or None if parsing fails or out of range.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return parse_iso_timestamp(value)
    try:
        numeric = float(value)
        if not _is_finite(numeric) or numeric < 0:
            return None
        if numeric >= EPOCH_MS_THRESHOLD:
            dt = datetime.fromtimestamp(numeric / 1000, tz=UTC)
        else:
            dt = datetime.fromtimestamp(numeric, tz=UTC)
        return _validate_range(dt)
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def parse_metadata_timestamp(meta: dict) -> datetime | None:
    """Extract and parse a timestamp from a metadata dict.

    Handles datetime objects directly and delegates string values
    to ``parse_iso_timestamp``. Ensures the result is timezone-aware
    (naive datetimes are assumed UTC).

    Args:
        meta: Metadata dict potentially containing a "timestamp" key.

    Returns:
        Timezone-aware datetime, or None if missing or unparseable.
    """
    ts = meta.get("timestamp")
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def monotonic_ms() -> int:
    """Return current monotonic time in milliseconds.

    Uses time.monotonic() for duration measurements that are immune
    to wall-clock adjustments.

    Returns:
        Monotonic time in integer milliseconds.
    """
    return int(time.monotonic() * 1000)


def utc_now_iso() -> str:
    """Return current UTC time as an ISO-8601 string.

    Replaces the common ``datetime.now(UTC).isoformat()`` pattern
    with a single call.

    Returns:
        ISO-8601 timestamp string with UTC timezone.
    """
    return datetime.now(UTC).isoformat()
