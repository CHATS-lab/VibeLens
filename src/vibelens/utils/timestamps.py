"""Timestamp parsing and formatting utilities."""

from datetime import UTC, datetime


def parse_ms_timestamp(value: int | str | None) -> datetime | None:
    """Convert a millisecond-epoch timestamp to a UTC datetime.

    Args:
        value: Millisecond epoch as int or numeric string, or None.

    Returns:
        UTC-aware datetime, or None if parsing fails.
    """
    if value is None:
        return None
    try:
        ms = int(value)
        return datetime.fromtimestamp(ms / 1000, tz=UTC)
    except (ValueError, TypeError, OSError):
        return None


def parse_iso_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string to a UTC datetime.

    Adds UTC timezone if the parsed datetime is naive.

    Args:
        value: ISO-8601 formatted string, or None.

    Returns:
        UTC-aware datetime, or None if parsing fails.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None


def format_isoformat(dt: datetime | None) -> str | None:
    """Format a datetime to ISO-8601 string.

    Args:
        dt: Datetime to format, or None.

    Returns:
        ISO-8601 string, or None if input is None.
    """
    if dt is None:
        return None
    return dt.isoformat()
