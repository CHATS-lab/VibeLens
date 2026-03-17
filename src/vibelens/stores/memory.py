"""In-memory SessionStore with per-token isolation and TTL cleanup.

Used in demo mode to provide ephemeral uploads scoped to each browser
tab. Pre-loaded example sessions live under SHARED_TOKEN and are
visible to all clients.
"""

import logging
import time

from vibelens.models.message import Message
from vibelens.models.session import SessionDetail, SessionSummary, SubAgentSession

logger = logging.getLogger(__name__)

SHARED_TOKEN = "__examples__"


class _SessionEntry:
    """Single session stored in memory."""

    __slots__ = ("summary", "messages", "sub_sessions", "last_access")

    def __init__(
        self,
        summary: SessionSummary,
        messages: list[Message],
        sub_sessions: list[SubAgentSession] | None = None,
    ) -> None:
        self.summary = summary
        self.messages = messages
        self.sub_sessions = sub_sessions or []
        self.last_access = time.monotonic()


class MemorySessionStore:
    """In-memory session store with per-token isolation.

    Data structure: ``{token: {session_id: _SessionEntry}}``.
    Shared example sessions use ``SHARED_TOKEN`` and are visible to all.

    Args:
        ttl_seconds: Seconds before a token bucket is eligible for cleanup.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._buckets: dict[str, dict[str, _SessionEntry]] = {}
        self._ttl_seconds = ttl_seconds

    async def store_session(
        self,
        summary: SessionSummary,
        messages: list[Message],
        token: str,
        sub_sessions: list[SubAgentSession] | None = None,
    ) -> bool:
        """Store a session under the given token bucket.

        Args:
            summary: Session summary to store.
            messages: Messages belonging to the session.
            token: Client isolation token.
            sub_sessions: Optional sub-agent sessions to store alongside.

        Returns:
            True if stored, False if session_id already exists in the bucket.
        """
        bucket = self._buckets.setdefault(token, {})
        if summary.session_id in bucket:
            return False
        bucket[summary.session_id] = _SessionEntry(summary, messages, sub_sessions)
        return True

    async def list_sessions(self, token: str) -> list[SessionSummary]:
        """List shared example sessions plus token-scoped uploads.

        Args:
            token: Client isolation token.

        Returns:
            Combined list of session summaries sorted by timestamp desc.
        """
        seen: set[str] = set()
        result: list[SessionSummary] = []

        # Shared examples first
        for entry in self._buckets.get(SHARED_TOKEN, {}).values():
            seen.add(entry.summary.session_id)
            result.append(entry.summary)

        # Token-scoped uploads
        if token and token != SHARED_TOKEN:
            for entry in self._buckets.get(token, {}).values():
                if entry.summary.session_id not in seen:
                    seen.add(entry.summary.session_id)
                    result.append(entry.summary)
                    entry.last_access = time.monotonic()

        result.sort(key=lambda s: str(s.timestamp or ""), reverse=True)
        return result

    async def get_session(self, session_id: str, token: str) -> SessionDetail | None:
        """Look up a session by ID, checking shared then token bucket.

        Args:
            session_id: The session to retrieve.
            token: Client isolation token.

        Returns:
            SessionDetail if found, None otherwise.
        """
        # Check shared examples first
        shared = self._buckets.get(SHARED_TOKEN, {})
        entry = shared.get(session_id)
        if entry:
            return SessionDetail(
                summary=entry.summary,
                messages=entry.messages,
                sub_sessions=entry.sub_sessions,
            )

        # Check token bucket
        if token and token != SHARED_TOKEN:
            bucket = self._buckets.get(token, {})
            entry = bucket.get(session_id)
            if entry:
                entry.last_access = time.monotonic()
                return SessionDetail(
                    summary=entry.summary,
                    messages=entry.messages,
                    sub_sessions=entry.sub_sessions,
                )

        return None

    async def delete_by_token(self, token: str) -> int:
        """Remove all sessions for a given token.

        Args:
            token: Client isolation token whose sessions to remove.

        Returns:
            Number of sessions deleted.
        """
        bucket = self._buckets.pop(token, {})
        return len(bucket)

    def cleanup_expired(self) -> int:
        """Evict token buckets that have not been accessed within TTL.

        The shared example bucket is never evicted.

        Returns:
            Number of token buckets evicted.
        """
        now = time.monotonic()
        expired_tokens: list[str] = []

        for token, bucket in self._buckets.items():
            if token == SHARED_TOKEN:
                continue
            if not bucket:
                expired_tokens.append(token)
                continue
            # Use the most recent access time in the bucket
            latest = max(e.last_access for e in bucket.values())
            if now - latest > self._ttl_seconds:
                expired_tokens.append(token)

        for token in expired_tokens:
            del self._buckets[token]

        if expired_tokens:
            logger.info("Evicted %d expired token buckets", len(expired_tokens))
        return len(expired_tokens)
