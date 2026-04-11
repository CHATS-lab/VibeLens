"""Unique identifier generation utilities.

Provides timestamped ID generation (upload/donation pipelines) and
deterministic content-addressed IDs (parser step/tool-call dedup).
"""

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

# strftime format for the time-prefix portion of timestamped IDs
TIMESTAMPED_ID_FORMAT = "%Y%m%d%H%M%S"
# Hex chars from uuid4 appended after the timestamp for uniqueness
SHORT_UUID_LENGTH = 4


def generate_timestamped_id(uuid_length: int = SHORT_UUID_LENGTH) -> str:
    """Create a unique time-prefixed identifier.

    Format: ``{YYYYMMDDHHMMSS}_{short_uuid}`` — sortable by creation time
    with a random suffix to avoid collisions.

    Args:
        uuid_length: Number of hex characters for the random suffix.

    Returns:
        Identifier string, e.g. ``20260408143012_a1b2``.
    """
    timestamp = datetime.now(timezone.utc).strftime(TIMESTAMPED_ID_FORMAT)
    short_uuid = uuid4().hex[:uuid_length]
    return f"{timestamp}_{short_uuid}"


def deterministic_id(namespace: str, *components: str) -> str:
    """Generate a repeatable identifier from a namespace and components.

    Uses SHA-256 of the concatenated parts, truncated to 24 hex chars
    with a namespace prefix for readability (e.g. ``msg-a1b2c3...``).
    Parsing the same file twice always yields the same IDs, enabling
    caching and deduplication.

    Args:
        namespace: Short prefix (e.g. "msg", "tc").
        *components: Strings hashed together to form the unique part.

    Returns:
        Deterministic identifier string.
    """
    raw = "|".join(components)
    hex_digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"{namespace}-{hex_digest}"
