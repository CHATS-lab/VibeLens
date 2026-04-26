"""Two-tier session search index with weighted per-field BM25.

Tier 1 (metadata) is built synchronously at startup from
``list_all_metadata()``. It only covers ``session_id`` + the session's
``first_message`` preview, so it cannot answer queries that target
``agent_messages`` or ``tool_calls``. Tier 1 exists to keep search
responsive during the ~24 s Tier 2 build.

Tier 2 (full text) loads every session's trajectory, extracts lowercased
per-field text, tokenizes, and inserts into the shared
:class:`~vibelens.services.search.InvertedIndex`. The trajectory is
released as soon as extraction finishes so memory stays proportional to
extracted text, not raw parsed structure.

All mutating operations swap state under ``threading.Lock`` so concurrent
search requests observe a consistent view.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory
from vibelens.models.trajectories.content import ContentPart
from vibelens.services.search import InvertedIndex, tokenize
from vibelens.services.session.search.scorer import RankableView, score_query
from vibelens.services.session.store_resolver import list_all_metadata, load_from_stores
from vibelens.utils import get_logger, log_duration_summary
from vibelens.utils.timestamps import monotonic_ms, parse_iso_timestamp

logger = get_logger(__name__)

# Threads for parallel session loading during Tier 2 index build.
MAX_PARALLEL_WORKERS = 8
# Max chars for tool argument values stored in the search index.
ARG_VALUE_MAX_LENGTH = 500
# Max chars for observation text stored in the search index.
OBSERVATION_MAX_LENGTH = 200

# Per-field BM25 weights. Starting point; tuned offline against
# ``scripts/eval_session_search.py`` before ship.
FIELD_WEIGHTS: dict[str, float] = {
    "session_id": 8.0,
    "user_prompts": 4.0,
    "agent_messages": 2.0,
    "tool_calls": 1.0,
}


@dataclass(slots=True)
class _SessionEntry:
    """Per-session searchable text + metadata tied to one doc index.

    Populated during Tier 2 build and retained for the life of the index
    (or until the session is removed). Tier 1 entries use the same class
    with empty agent_messages / tool_calls strings.
    """

    session_id: str
    # Lowercased extracted text per field. Kept for Tier 1 fallback
    # substring search and for re-tokenization on rebuild.
    user_prompts: str
    agent_messages: str
    tool_calls: str
    session_id_lower: str
    # Tokens used to insert into the inverted index. Kept so incremental
    # add_sessions can rebuild the index without re-parsing every session.
    tokens_per_field: dict[str, list[str]] = field(default_factory=dict)
    # Last-activity timestamp (``updated_at``), used as the final tiebreaker (desc).
    # Falls back to ``created_at`` when the session has no recorded activity time.
    # None for entries that lack any metadata timestamp.
    timestamp: datetime | None = None


class SessionSearchIndex:
    """Two-tier index: metadata (Tier 1) + full text BM25F (Tier 2)."""

    def __init__(self) -> None:
        # Tier 1: populated from metadata only. Covers session_id +
        # first_message. Agent/tool fields are empty strings.
        self._metadata_entries: dict[str, _SessionEntry] = {}
        # Tier 2: full-text entries plus a parallel InvertedIndex
        # covering all four fields.
        self._full_entries: dict[str, _SessionEntry] = {}
        # Maps a session_id to its position in the inverted-index arrays.
        self._full_order: list[str] = []
        self._full_inverted: InvertedIndex | None = None
        # Parallel float array of session timestamps for the tie-breaker.
        # Index i holds the epoch seconds of session _full_order[i], or
        # -inf if the session lacks a timestamp.
        self._full_ts: np.ndarray = np.empty(0, dtype=np.float64)
        self._lock = threading.Lock()
        self._full_building = False

    def has_full(self) -> bool:
        """True when Tier 2 is built and able to score queries."""
        return self._full_inverted is not None and bool(self._full_entries)

    def search_full(self, query: str, top_k: int | None = None) -> list[tuple[str, float]] | None:
        """Return BM25F-ranked ``(session_id, score)`` pairs from Tier 2.

        Returns ``None`` when Tier 2 is not ready so the caller can fall
        back to Tier 1. An empty query returns ``None`` as well — the
        API layer shortcuts that earlier.
        """
        if not query.strip():
            return None
        inverted = self._full_inverted
        if inverted is None or inverted.num_docs == 0:
            return None

        # Capture references for the closure so the lookup remains stable
        # for the duration of this query even if a swap_in_full mutates
        # state mid-call. Mutations rebind the attributes; closures over
        # the local names see the snapshot we captured here.
        entries = self._full_entries
        order = self._full_order

        def raw_text_lookup(doc_idx: int, field: str) -> str:
            entry = entries.get(order[doc_idx])
            return getattr(entry, field, "") if entry else ""

        view = RankableView(
            inverted=inverted,
            order=order,
            timestamps=self._full_ts,
            id_exact=self._full_id_exact(),
            id_prefix=self._full_id_prefix(),
            raw_text_lookup=raw_text_lookup,
        )
        return score_query(view, query, top_k)

    def search_metadata(self, query: str) -> list[tuple[str, float]]:
        """Case-insensitive substring search over Tier 1 entries.

        Matches against session_id and lowercased first_message
        (stored as user_prompts on metadata-only entries). Returns
        results in metadata-dict insertion order with score=0.0.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        results: list[tuple[str, float]] = []
        for entry in self._metadata_entries.values():
            if needle in entry.session_id_lower or needle in entry.user_prompts:
                results.append((entry.session_id, 0.0))
        return results

    # ---- Tier 1 build ------------------------------------------------------
    def build_from_metadata(self, session_token: str | None) -> None:
        """Build Tier 1 from cached metadata. No disk I/O beyond that."""
        new_entries = {
            sid: entry
            for sid, entry in (
                (s.get("session_id", ""), _tier1_entry_from_summary(s))
                for s in list_all_metadata(session_token)
            )
            if sid
        }
        with self._lock:
            self._metadata_entries = new_entries
        logger.info("Search index Tier 1 built: %d entries from metadata", len(new_entries))

    # ---- Tier 2 build ------------------------------------------------------
    def build_full(self, session_token: str | None) -> None:
        """Parse every session, extract text, tokenize, rebuild Tier 2."""
        if self._full_building:
            logger.info("Full index build already in progress, skipping")
            return
        self._full_building = True
        try:
            summaries = list_all_metadata(session_token)
            meta_by_id = {s.get("session_id", ""): s for s in summaries if s.get("session_id")}
            logger.info("Building full search index for %d sessions", len(meta_by_id))

            build_start = monotonic_ms()
            new_entries, per_session_ms = _parse_entries_parallel(
                meta_by_id.keys(), session_token, meta_by_id
            )
            self._swap_in_full(new_entries)

            log_duration_summary(
                logger,
                "build_full_search_index_per_session",
                per_session_ms,
                total_ms=monotonic_ms() - build_start,
                loaded=len(new_entries),
            )
        finally:
            self._full_building = False

    # ---- Incremental ops ---------------------------------------------------
    def add_sessions(self, session_ids: list[str], session_token: str | None) -> None:
        """Incrementally ingest newly-uploaded sessions into both tiers."""
        if not session_ids:
            return
        summaries = list_all_metadata(session_token)
        meta_by_id = {s.get("session_id", ""): s for s in summaries}

        with self._lock:
            for sid in session_ids:
                self._metadata_entries[sid] = _tier1_entry_from_summary(meta_by_id.get(sid) or {})

        if not self._full_entries:
            return

        parsed, _ = _parse_entries_parallel(session_ids, session_token, meta_by_id)
        self._swap_in_full({**self._full_entries, **parsed})
        logger.info("Incrementally added %d sessions to search index", len(session_ids))

    def refresh(self, session_token: str | None) -> None:
        """Diff-refresh: add new sessions, drop sessions that no longer exist."""
        summaries = list_all_metadata(session_token)
        current_ids = {s.get("session_id", "") for s in summaries} - {""}

        self.build_from_metadata(session_token)
        if not self._full_entries:
            return

        existing_ids = set(self._full_entries.keys())
        new_ids = current_ids - existing_ids
        stale_ids = existing_ids - current_ids
        if not new_ids and not stale_ids:
            return

        kept = {sid: entry for sid, entry in self._full_entries.items() if sid not in stale_ids}
        meta_by_id = {s.get("session_id", ""): s for s in summaries}
        parsed, _ = _parse_entries_parallel(new_ids, session_token, meta_by_id)
        self._swap_in_full({**kept, **parsed})
        if stale_ids:
            logger.info("Removed %d stale sessions from search index", len(stale_ids))
        if new_ids:
            logger.info("Added %d new sessions to search index", len(new_ids))

    def invalidate(self) -> None:
        """Clear Tier 2 only. Tier 1 stays populated from metadata."""
        with self._lock:
            self._full_entries = {}
            self._full_order = []
            self._full_inverted = None
            self._full_ts = np.empty(0, dtype=np.float64)
        logger.info("Search index Tier 2 invalidated (Tier 1 preserved)")

    def _swap_in_full(self, new_entries: dict[str, _SessionEntry]) -> None:
        """Rebuild the inverted index and swap state atomically.

        Runs outside the lock because building the ``InvertedIndex`` is
        CPU-bound and self-contained; only the final assignment is
        protected so searches never see a half-installed state.
        """
        order = sorted(new_entries.keys())
        corpus = [new_entries[sid].tokens_per_field for sid in order]
        inverted = InvertedIndex(corpus, FIELD_WEIGHTS)
        timestamps = np.fromiter(
            (_ts_to_epoch(new_entries[sid].timestamp) for sid in order),
            count=len(order),
            dtype=np.float64,
        )
        with self._lock:
            self._full_entries = new_entries
            self._full_order = order
            self._full_inverted = inverted
            self._full_ts = timestamps

    def _full_id_exact(self) -> dict[str, int]:
        """Map lowercased session_id → doc index for exact-tier lookup."""
        return {sid.lower(): i for i, sid in enumerate(self._full_order)}

    def _full_id_prefix(self) -> dict[str, list[int]]:
        """Map first dash-delimited segment → doc indices for prefix tier."""
        prefixes: dict[str, list[int]] = {}
        for i, sid in enumerate(self._full_order):
            head = sid.split("-", 1)[0].lower()
            if head:
                prefixes.setdefault(head, []).append(i)
        return prefixes


def _ts_to_epoch(dt: datetime | None) -> float:
    """Convert a tz-aware datetime to epoch seconds, or -inf if missing.

    -inf ensures entries without a timestamp sort last under a descending
    recency tiebreaker.
    """
    if dt is None:
        return float("-inf")
    return dt.timestamp()


def _tier1_entry_from_summary(summary: dict) -> _SessionEntry:
    """Build a Tier 1 entry from a session metadata summary.

    Covers only session_id + lowercased first_message — the agent_messages
    and tool_calls fields stay empty until Tier 2 parses the trajectory.
    """
    sid = summary.get("session_id", "") or ""
    first_msg = (summary.get("first_message", "") or "").lower()
    return _SessionEntry(
        session_id=sid,
        session_id_lower=sid.lower(),
        user_prompts=first_msg,
        agent_messages="",
        tool_calls="",
        timestamp=parse_iso_timestamp(
            summary.get("updated_at") or summary.get("created_at")
        ),
    )


def _parse_entries_parallel(
    session_ids, session_token: str | None, meta_by_id: dict[str, dict]
) -> tuple[dict[str, _SessionEntry], list[int]]:
    """Parse each session in a thread pool and return ``(entries, durations)``.

    Timestamps are pulled from ``meta_by_id[sid]``; a missing entry means
    the session has no metadata timestamp and will sort last under the
    recency tiebreaker. Failures are logged at DEBUG inside
    :func:`_build_entry` and elided from the result dict.
    """
    entries: dict[str, _SessionEntry] = {}
    durations: list[int] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as pool:
        futures = [
            pool.submit(
                _build_entry,
                sid,
                session_token,
                parse_iso_timestamp(
                    (meta_by_id.get(sid) or {}).get("updated_at")
                    or (meta_by_id.get(sid) or {}).get("created_at")
                ),
            )
            for sid in session_ids
        ]
        for future in futures:
            entry, duration_ms = future.result()
            durations.append(duration_ms)
            if entry is not None:
                entries[entry.session_id] = entry
    return entries, durations


def _build_entry(
    session_id: str, session_token: str | None, timestamp: datetime | None
) -> tuple[_SessionEntry | None, int]:
    """Load + extract + tokenize one session. Released trajectories on return.

    Returns ``(entry, duration_ms)``. ``entry`` is ``None`` when the
    session cannot be loaded or parsing raises; ``duration_ms`` is
    always set so the caller can aggregate timings.
    """
    start = monotonic_ms()
    try:
        trajectories = load_from_stores(session_id, session_token)
        if not trajectories:
            return None, monotonic_ms() - start
        user_prompts = _extract_user_prompts(trajectories)
        agent_messages = _extract_agent_messages(trajectories)
        tool_calls = _extract_tool_calls(trajectories)
        sid_lower = session_id.lower()
        # session_id participates in BM25 too — tokenize its dash-delimited
        # segments so partial sid searches can get BM25 credit.
        tokens = {
            "session_id": tokenize(sid_lower.replace("-", " ")),
            "user_prompts": tokenize(user_prompts),
            "agent_messages": tokenize(agent_messages),
            "tool_calls": tokenize(tool_calls),
        }
        entry = _SessionEntry(
            session_id=session_id,
            session_id_lower=sid_lower,
            user_prompts=user_prompts,
            agent_messages=agent_messages,
            tool_calls=tool_calls,
            tokens_per_field=tokens,
            timestamp=timestamp,
        )
        return entry, monotonic_ms() - start
    except Exception:
        logger.debug("Failed to load session %s for search index", session_id)
        return None, monotonic_ms() - start


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
    parts: list[str] = []
    for value in arguments.values():
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)
