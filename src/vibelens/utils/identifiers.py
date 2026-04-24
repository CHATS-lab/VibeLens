"""Unique identifier generation utilities.

Provides timestamped ID generation (analysis/upload/donation pipelines)
and deterministic content-addressed IDs (parser step/tool-call dedup).
"""

import hashlib
import secrets
from datetime import datetime, timezone

# Bytes of CSPRNG randomness for the suffix. 6 bytes -> 8 url-safe base64 chars.
SUFFIX_BYTES = 6


def generate_timestamped_id() -> str:
    """Create a sortable, URL-safe identifier.

    Format: ``{YYYYMMDDTHHMMSS}-{8url-safe}``, e.g. ``20260423T171405-sJtL_vC1``.
    Lexicographic sort equals chronological sort, so directory listings
    sort by creation time. Safe as a filesystem path segment and inside URLs.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = secrets.token_urlsafe(SUFFIX_BYTES)
    return f"{timestamp}-{suffix}"


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
