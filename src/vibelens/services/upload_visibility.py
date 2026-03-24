"""Upload visibility state and filtering.

Owns the mapping of browser session tokens to upload directories.
The storage layer tags metadata with _upload_id; this module provides
filter_visible() and is_session_visible() for service-layer callers
to enforce visibility without circular imports.
"""

# Upload ownership: maps browser session token -> set of upload_ids
_token_uploads: dict[str, set[str]] = {}


def register_upload(session_token: str, upload_id: str) -> None:
    """Associate an upload subdirectory with a browser session token.

    Args:
        session_token: Browser tab UUID from X-Session-Token header.
        upload_id: Upload subdirectory name.
    """
    _token_uploads.setdefault(session_token, set()).add(upload_id)


def filter_visible(summaries: list[dict], session_token: str | None) -> list[dict]:
    """Filter metadata summaries to those visible to the given token.

    Root-level sessions (_upload_id absent) are always visible.
    Upload sessions require the token to own the upload.

    Args:
        summaries: List of trajectory summary dicts.
        session_token: Browser tab token, or None.

    Returns:
        Filtered list of visible summaries.
    """
    allowed = _token_uploads.get(session_token, set()) if session_token else set()
    return [s for s in summaries if not s.get("_upload_id") or s.get("_upload_id") in allowed]


def is_session_visible(meta: dict | None, session_token: str | None) -> bool:
    """Check if a single session is visible to the given token.

    Args:
        meta: Session metadata dict (may contain _upload_id).
        session_token: Browser tab token, or None.

    Returns:
        True if the session is visible.
    """
    if not meta:
        return False
    upload_id = meta.get("_upload_id")
    if not upload_id:
        return True
    if not session_token:
        return False
    return upload_id in _token_uploads.get(session_token, set())
