"""Two-tier in-memory search index for full-text session search.

Tier 1 (metadata): Built instantly from list_all_metadata() — provides
session_id and first_message (user_prompts) search with zero disk I/O.

Tier 2 (full text): Built asynchronously via ThreadPoolExecutor — provides
deep search across all user_prompts, agent_messages, and tool_calls.
Never blocks search requests.

Search always returns from the best available tier. While Tier 2 builds,
searches on agent_messages/tool_calls return no results, but session_id
and first_message matches work immediately.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory
from vibelens.models.trajectories.content import ContentPart
from vibelens.services.session.store_resolver import list_all_metadata, load_from_stores
from vibelens.utils import get_logger

logger = get_logger(__name__)

# Threads for parallel session loading during Tier 2 index build
MAX_PARALLEL_WORKERS = 8
# Max chars for tool argument values stored in the search index
ARG_VALUE_MAX_LENGTH = 500
# Max chars for observation text stored in the search index
OBSERVATION_MAX_LENGTH = 200


@dataclass
class _SearchEntry:
    """Pre-extracted, lowercased text for a single session."""

    session_id: str
    user_prompts: str
    agent_messages: str
    tool_calls: str


class _SearchIndex:
    """Two-tier search index: metadata (instant) + full text (background).

    Tier 1 (_metadata_entries) is built from cached metadata and provides
    session_id + first_message search. Tier 2 (_full_entries) loads full
    trajectories for deep text search. Dict reference swaps are atomic
    under the GIL, but the lock protects multi-step read-modify-write
    sequences during incremental updates.
    """

    def __init__(self) -> None:
        self._metadata_entries: dict[str, _SearchEntry] = {}
        self._full_entries: dict[str, _SearchEntry] = {}
        self._lock = threading.Lock()
        self._full_building = False

    def search(self, query: str, sources: list[str]) -> list[str]:
        """Search using the best available tier. Never blocks.

        Args:
            query: Lowercased search string.
            sources: Source fields to search.

        Returns:
            List of matching session IDs.
        """
        # Prefer full entries when available, fall back to metadata
        entries = self._full_entries if self._full_entries else self._metadata_entries
        matches: list[str] = []
        for entry in entries.values():
            if _entry_matches(entry, query, sources):
                matches.append(entry.session_id)
        return matches

    def build_from_metadata(self, session_token: str | None) -> None:
        """Build Tier 1 from list_all_metadata() — fast, no disk I/O.

        Populates user_prompts with first_message text. Other fields
        are left empty until Tier 2 completes.

        Args:
            session_token: Browser tab token for upload scoping.
        """
        summaries = list_all_metadata(session_token)
        new_entries: dict[str, _SearchEntry] = {}

        for summary in summaries:
            session_id = summary.get("session_id", "")
            if not session_id:
                continue
            first_msg = summary.get("first_message", "") or ""
            new_entries[session_id] = _SearchEntry(
                session_id=session_id,
                user_prompts=first_msg.lower(),
                agent_messages="",
                tool_calls="",
            )

        with self._lock:
            self._metadata_entries = new_entries

        logger.info("Search index Tier 1 built: %d entries from metadata", len(new_entries))

    def build_full(self, session_token: str | None) -> None:
        """Build Tier 2 by loading all trajectories in parallel.

        Uses ThreadPoolExecutor to load sessions concurrently. Results
        are collected and swapped atomically so searches are never
        interrupted by a partial build.

        Args:
            session_token: Browser tab token for upload scoping.
        """
        if self._full_building:
            logger.info("Full index build already in progress, skipping")
            return

        self._full_building = True
        try:
            summaries = list_all_metadata(session_token)
            session_ids = [s.get("session_id", "") for s in summaries if s.get("session_id")]
            logger.info("Building full search index for %d sessions", len(session_ids))

            new_entries: dict[str, _SearchEntry] = {}
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as pool:
                futures = {
                    pool.submit(_load_session_entry, sid, session_token): sid for sid in session_ids
                }
                for future in futures:
                    entry = future.result()
                    if entry:
                        new_entries[entry.session_id] = entry

            with self._lock:
                self._full_entries = new_entries

            logger.info("Search index Tier 2 built: %d entries (full text)", len(new_entries))
        finally:
            self._full_building = False

    def add_sessions(self, session_ids: list[str], session_token: str | None) -> None:
        """Incrementally add new sessions to both tiers.

        Args:
            session_ids: Session IDs to add.
            session_token: Browser tab token for upload scoping.
        """
        if not session_ids:
            return

        # Update Tier 1 from metadata
        summaries = list_all_metadata(session_token)
        meta_by_id = {s.get("session_id", ""): s for s in summaries}

        with self._lock:
            for sid in session_ids:
                summary = meta_by_id.get(sid, {})
                first_msg = summary.get("first_message", "") or ""
                self._metadata_entries[sid] = _SearchEntry(
                    session_id=sid,
                    user_prompts=first_msg.lower(),
                    agent_messages="",
                    tool_calls="",
                )

        # Update Tier 2 if it has been built
        if not self._full_entries:
            return

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as pool:
            futures = {
                pool.submit(_load_session_entry, sid, session_token): sid for sid in session_ids
            }
            for future in futures:
                entry = future.result()
                if entry:
                    with self._lock:
                        self._full_entries[entry.session_id] = entry

        logger.info("Incrementally added %d sessions to search index", len(session_ids))

    def refresh(self, session_token: str | None) -> None:
        """Incremental diff-based refresh: add new, remove stale sessions.

        Compares current metadata session IDs against the full index
        and only loads sessions that are new. Runs in <1s for typical
        refreshes (0-5 new sessions).

        Args:
            session_token: Browser tab token for upload scoping.
        """
        summaries = list_all_metadata(session_token)
        current_ids = {s.get("session_id", "") for s in summaries} - {""}

        # Refresh Tier 1 (cheap — just re-read metadata)
        self.build_from_metadata(session_token)

        # Refresh Tier 2 incrementally if it exists
        if not self._full_entries:
            return

        existing_ids = set(self._full_entries.keys())
        new_ids = current_ids - existing_ids
        stale_ids = existing_ids - current_ids

        # Remove stale entries
        if stale_ids:
            with self._lock:
                for sid in stale_ids:
                    self._full_entries.pop(sid, None)
            logger.info("Removed %d stale sessions from search index", len(stale_ids))

        # Load new entries in parallel
        if new_ids:
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as pool:
                futures = {
                    pool.submit(_load_session_entry, sid, session_token): sid for sid in new_ids
                }
                for future in futures:
                    entry = future.result()
                    if entry:
                        with self._lock:
                            self._full_entries[entry.session_id] = entry
            logger.info("Added %d new sessions to search index", len(new_ids))

    def invalidate(self) -> None:
        """Clear Tier 2 only. Tier 1 is preserved from metadata."""
        with self._lock:
            self._full_entries = {}
        logger.info("Search index Tier 2 invalidated (Tier 1 preserved)")


_index = _SearchIndex()


def build_search_index(session_token: str | None = None) -> None:
    """Build Tier 1 (metadata) search index. Fast, for startup."""
    _index.build_from_metadata(session_token)


def build_full_search_index(session_token: str | None = None) -> None:
    """Build Tier 2 (full text) search index. Slow, for background."""
    _index.build_full(session_token)


def search_sessions(query: str, sources: list[str], session_token: str | None = None) -> list[str]:
    """Search sessions by query across selected text sources.

    Args:
        query: Search string (case-insensitive substring match).
        sources: List of source names to search
            (user_prompts, agent_messages, tool_calls, session_id).
        session_token: Browser tab token for upload scoping.

    Returns:
        List of matching session IDs.
    """
    if not query:
        return []
    return _index.search(query.lower(), sources)


def invalidate_search_index() -> None:
    """Clear Tier 2, preserving Tier 1 metadata index."""
    _index.invalidate()


def add_sessions_to_index(session_ids: list[str], session_token: str | None = None) -> None:
    """Incrementally add new sessions to the search index after upload.

    Args:
        session_ids: Session IDs to add.
        session_token: Browser tab token for upload scoping.
    """
    _index.add_sessions(session_ids, session_token)


def refresh_search_index(session_token: str | None = None) -> None:
    """Incremental diff-based refresh for periodic background task.

    Args:
        session_token: Browser tab token for upload scoping.
    """
    _index.refresh(session_token)


def _load_session_entry(session_id: str, session_token: str | None) -> _SearchEntry | None:
    """Load a single session's trajectories and extract searchable text.

    Called by ThreadPoolExecutor workers during parallel index builds.

    Args:
        session_id: Session to load.
        session_token: Browser tab token for upload scoping.

    Returns:
        Search entry or None if session cannot be loaded.
    """
    try:
        trajectories = load_from_stores(session_id, session_token)
        if not trajectories:
            return None
        return _SearchEntry(
            session_id=session_id,
            user_prompts=_extract_user_prompts(trajectories),
            agent_messages=_extract_agent_messages(trajectories),
            tool_calls=_extract_tool_calls(trajectories),
        )
    except Exception:
        logger.debug("Failed to load session %s for search index", session_id)
        return None


def _entry_matches(entry: _SearchEntry, query: str, sources: list[str]) -> bool:
    """Check if a search entry matches the query in any of the selected sources."""
    for source in sources:
        if source == "user_prompts" and query in entry.user_prompts:
            return True
        if source == "agent_messages" and query in entry.agent_messages:
            return True
        if source == "tool_calls" and query in entry.tool_calls:
            return True
        if source == "session_id" and query in entry.session_id.lower():
            return True
    return False


def _extract_user_prompts(trajectories: list[Trajectory]) -> str:
    """Concatenate all user step messages, lowercased."""
    parts: list[str] = []
    for traj in trajectories:
        for step in traj.steps:
            if step.source != StepSource.USER:
                continue
            text = _extract_message_text(step.message)
            if text:
                parts.append(text)
    return " ".join(parts).lower()


def _extract_agent_messages(trajectories: list[Trajectory]) -> str:
    """Extract agent text messages (no tool data)."""
    parts: list[str] = []
    for traj in trajectories:
        for step in traj.steps:
            if step.source != StepSource.AGENT:
                continue
            text = _extract_message_text(step.message)
            if text:
                parts.append(text)
    return " ".join(parts).lower()


def _extract_tool_calls(trajectories: list[Trajectory]) -> str:
    """Extract tool names, arguments, and truncated observations."""
    parts: list[str] = []
    for traj in trajectories:
        for step in traj.steps:
            if step.source != StepSource.AGENT:
                continue

            for tc in step.tool_calls:
                parts.append(tc.function_name)
                arg_text = _extract_readable_args(tc.arguments)
                if arg_text:
                    parts.append(arg_text[:ARG_VALUE_MAX_LENGTH])

            if step.observation:
                for result in step.observation.results:
                    obs_text = _extract_message_text(result.content)
                    if obs_text:
                        parts.append(obs_text[:OBSERVATION_MAX_LENGTH])

    return " ".join(parts).lower()


def _extract_message_text(message: str | list[ContentPart] | None) -> str:
    """Extract plain text from a string or ContentPart list."""
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    # list[ContentPart]
    texts: list[str] = []
    for part in message:
        if part.text:
            texts.append(part.text)
    return " ".join(texts)


def _extract_readable_args(arguments: dict | str | None) -> str:
    """Extract string values from tool call arguments."""
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    # dict — extract string-valued entries
    parts: list[str] = []
    for value in arguments.values():
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)
