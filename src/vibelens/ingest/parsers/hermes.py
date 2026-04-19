"""Hermes Agent session file parser.

Parses ~/.hermes/sessions/*.jsonl (gateway transcript stream) and
session_*.json (CLI / run_agent snapshot) into ATIF Trajectory objects.
Enriches with token and cost data from ~/.hermes/state.db when available,
and Slack/CLI origin metadata from ~/.hermes/sessions/sessions.json.

Hermes writes two session formats:

- ``<session_id>.jsonl`` — appended by the gateway (Slack, Telegram, etc.)
  with role-tagged records (``session_meta``, ``user``, ``assistant``,
  ``tool``), per-record timestamps, and ``finish_reason`` on assistant
  turns.
- ``session_<session_id>.json`` — overwritten by the CLI agent each turn
  with the full in-memory state: ``session_id``, ``model``, ``base_url``,
  ``platform``, ``session_start``, ``last_updated``, ``system_prompt``,
  ``tools``, ``messages``. Has no per-message timestamps.

Not every session has both files: gateway sessions have jsonl + snapshot;
pure CLI sessions have only the snapshot. The parser picks the jsonl as
primary when present (richer per-record data), falls back to the snapshot
otherwise, and enriches with the paired snapshot for ``base_url`` and
``system_prompt`` which are absent from the stream.

Token and cost data (``input_tokens``, ``output_tokens``,
``cache_read_tokens``, ``cache_write_tokens``, ``estimated_cost_usd``)
live in state.db at session level only — per-message ``token_count`` is
always 0 in observed data. The db totals are attached both to
``Trajectory.final_metrics`` (for direct access) and as a synthetic
``Metrics`` on the last assistant step (for the dashboard aggregator,
which sums per-step metrics rather than reading ``final_metrics``).
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser
from vibelens.llm.normalizer import normalize_model_name
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import (
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.utils import get_logger, parse_iso_timestamp

logger = get_logger(__name__)

# Session filename: 20260418_192555_4077bccc or 20260418_203756_06db65
# (varying hex length observed in practice). Matches both the jsonl
# stem and the suffix of a session_*.json snapshot.
_SESSION_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]+$")

_SNAPSHOT_PREFIX = "session_"

# Columns pulled from state.db. Kept as a constant so discover_session_files
# and _load_state_db stay in sync.
_STATE_DB_COLUMNS = (
    "started_at",
    "ended_at",
    "end_reason",
    "title",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "estimated_cost_usd",
    "actual_cost_usd",
    "cost_status",
    "cost_source",
    "billing_provider",
    "billing_base_url",
    "parent_session_id",
    "source",
)


class HermesParser(BaseParser):
    """Parser for Hermes Agent session files.

    Selects one primary file per unique session_id (preferring jsonl)
    and enriches it with the paired snapshot, state.db, and sessions.json
    index when those sources are available.

    Note on ``parse_session_index``: Hermes stores rich per-session
    metadata in ``state.db`` (tokens, cost, parent_session_id) and
    ``sessions/sessions.json`` (chat origin), but neither caches the
    first user message. A skeleton Trajectory without a first_message
    gives a poor listing experience, and reading one line per JSONL to
    recover it would already be most of a full parse. We keep the
    default (return None) and let index_builder fall through to
    full-file parsing, which is acceptable at the volumes Hermes sees.
    """

    AGENT_TYPE = AgentType.HERMES
    LOCAL_DATA_DIR: Path | None = Path.home() / ".hermes"

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Return one file per unique Hermes session_id, excluding stale snapshots.

        Hermes periodically rewrites ``session_<id>.json`` during an active
        session with a new session_id but the same underlying conversation.
        When the session is interrupted (or the agent reconnects) these
        intermediate snapshots stay on disk forever, each looking like a
        shorter prefix of the canonical session. They have no paired
        ``.jsonl`` and no row in ``state.db`` — that's the signal we use
        to filter them out.

        Dedup rules:
          1. If ``<id>.jsonl`` exists, use the jsonl (pairs with the
             ``session_<id>.json`` snapshot implicitly; the snapshot is
             read only for enrichment).
          2. Otherwise, keep ``session_<id>.json`` only if ``state.db``
             has a matching sessions row. No row => stale intermediate
             snapshot; drop it.
          3. If ``state.db`` is not available at all (e.g. parsing an
             extracted archive without the db), fall back to keeping
             every snapshot-only file — better to over-report than
             silently drop standalone sessions.

        Args:
            data_dir: Root ``.hermes`` directory (or an extracted copy).

        Returns:
            Sorted list of primary session file paths.
        """
        sessions_dir = data_dir / "sessions" if (data_dir / "sessions").is_dir() else data_dir
        jsonl_ids: dict[str, Path] = {}
        snapshot_ids: dict[str, Path] = {}
        for path in sessions_dir.iterdir():
            if not path.is_file():
                continue
            if path.suffix == ".jsonl" and _SESSION_ID_RE.match(path.stem):
                jsonl_ids[path.stem] = path
            elif (
                path.suffix == ".json"
                and path.stem.startswith(_SNAPSHOT_PREFIX)
                and _SESSION_ID_RE.match(path.stem[len(_SNAPSHOT_PREFIX) :])
            ):
                snapshot_ids[path.stem[len(_SNAPSHOT_PREFIX) :]] = path

        known_db_ids = _list_state_db_sessions(sessions_dir)
        primary: list[Path] = list(jsonl_ids.values())
        for session_id, snap_path in snapshot_ids.items():
            if session_id in jsonl_ids:
                continue
            if known_db_ids is not None and session_id not in known_db_ids:
                logger.debug(
                    "Hermes: dropping stale snapshot %s (no .jsonl and no state.db row)",
                    session_id,
                )
                continue
            primary.append(snap_path)
        return sorted(primary)

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse a single Hermes session file into one Trajectory.

        Args:
            content: Raw file content (jsonl stream or snapshot JSON).
            source_path: Original file path, used to locate paired files
                and to derive the session_id from the filename.

        Returns:
            Single-element list with the Trajectory, or empty list if
            the content is malformed or empty.
        """
        if not source_path:
            return []
        path = Path(source_path)
        session_id = _session_id_from_path(path)
        if not session_id:
            return []

        collector = DiagnosticsCollector()
        sessions_dir = path.parent

        if path.suffix == ".jsonl":
            records = _parse_jsonl(content, collector)
            if not records:
                return []
            steps, session_model, session_tools = _build_steps_from_jsonl(records, collector)
            snapshot = _load_snapshot(sessions_dir, session_id)
            base_url = snapshot.get("base_url") if snapshot else None
            system_prompt = snapshot.get("system_prompt") if snapshot else None
            platform = _first_nonnull(
                _session_meta_value(records, "platform"),
                snapshot.get("platform") if snapshot else None,
            )
            model = _first_nonnull(
                session_model,
                snapshot.get("model") if snapshot else None,
            )
            tools = session_tools or (snapshot.get("tools") if snapshot else None)
            session_start = parse_iso_timestamp(snapshot.get("session_start")) if snapshot else None
        else:
            snapshot = _parse_snapshot(content)
            if not snapshot:
                return []
            steps = _build_steps_from_snapshot(snapshot, collector)
            base_url = snapshot.get("base_url")
            system_prompt = snapshot.get("system_prompt")
            platform = snapshot.get("platform")
            model = snapshot.get("model")
            tools = snapshot.get("tools")
            session_start = parse_iso_timestamp(snapshot.get("session_start"))

        if not steps:
            return []

        db_row = _load_state_db(sessions_dir, session_id)
        origin = _load_index_entry(sessions_dir, session_id)

        model = _canonical_model_name(model)
        agent = self.build_agent(version=None, model=model)
        agent.tool_definitions = tools if isinstance(tools, list) else None
        for step in steps:
            if step.model_name:
                step.model_name = _canonical_model_name(step.model_name)

        _attach_session_metrics_to_last_assistant(steps, db_row, model)
        final_metrics = _build_final_metrics(steps, db_row, session_start)

        extra = _build_trajectory_extra(
            platform=platform,
            base_url=base_url,
            system_prompt=system_prompt,
            db_row=db_row,
            origin=origin,
            diagnostics=self.build_diagnostics_extra(collector),
        )

        parent_ref = None
        if db_row and db_row.get("parent_session_id"):
            parent_ref = TrajectoryRef(session_id=db_row["parent_session_id"])

        project_path = _derive_project_path(platform, origin, db_row)

        trajectory = self.assemble_trajectory(
            session_id=session_id,
            agent=agent,
            steps=steps,
            project_path=project_path,
            parent_trajectory_ref=parent_ref,
            extra=extra,
        )
        if final_metrics:
            trajectory.final_metrics = final_metrics
        return [trajectory]


# Hermes records model versions with dots (``claude-opus-4.7``) but
# VibeLens's pricing / normalizer expects dashes (``claude-opus-4-7``).
def _canonical_model_name(raw: str | None) -> str | None:
    """Canonicalise a raw Hermes model name via the shared llm normalizer.

    Hermes emits Anthropic models with dotted versions
    (``anthropic/claude-opus-4.7``). The shared ``llm.normalize_model_name``
    understands this form. When the model is unknown to the pricing catalog
    we keep the raw string so it still surfaces in the UI — losing it
    would silently drop model information for any wrapper not yet mapped.
    """
    if not raw:
        return raw
    return normalize_model_name(raw) or raw


def _session_id_from_path(path: Path) -> str | None:
    """Extract the canonical session_id from a jsonl or snapshot path."""
    if path.suffix == ".jsonl" and _SESSION_ID_RE.match(path.stem):
        return path.stem
    if path.suffix == ".json" and path.stem.startswith(_SNAPSHOT_PREFIX):
        candidate = path.stem[len(_SNAPSHOT_PREFIX) :]
        if _SESSION_ID_RE.match(candidate):
            return candidate
    return None


def _parse_jsonl(content: str, diagnostics: DiagnosticsCollector) -> list[dict]:
    """Parse line-delimited JSON into a list of record dicts."""
    return list(BaseParser.iter_jsonl_safe(content, diagnostics=diagnostics))


def _parse_snapshot(content: str) -> dict | None:
    """Parse a snapshot JSON string into a dict."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.debug("Invalid JSON in Hermes snapshot")
        return None
    if not isinstance(data, dict):
        return None
    return data


def _load_snapshot(sessions_dir: Path, session_id: str) -> dict | None:
    """Load the paired snapshot for a jsonl session, if it exists."""
    snap_path = sessions_dir / f"{_SNAPSHOT_PREFIX}{session_id}.json"
    if not snap_path.is_file():
        return None
    try:
        return _parse_snapshot(snap_path.read_text(encoding="utf-8"))
    except OSError:
        return None


def _session_meta_value(records: list[dict], key: str) -> Any:
    """Return ``key`` from the first ``session_meta`` record, if any."""
    for rec in records:
        if rec.get("role") == "session_meta":
            return rec.get(key)
    return None


def _first_nonnull(*values: Any) -> Any:
    """Return the first non-None, non-empty argument, or None."""
    for value in values:
        if value:
            return value
    return None


def _build_steps_from_jsonl(
    records: list[dict], diagnostics: DiagnosticsCollector
) -> tuple[list[Step], str | None, list | None]:
    """Build Step objects from jsonl records.

    Pairs each assistant tool_call with its matching tool record by
    tool_call_id. Returns the steps along with the session-level model
    and tool list pulled from the ``session_meta`` record.
    """
    tool_results_by_id = _collect_tool_results(records, diagnostics)
    session_model = _session_meta_value(records, "model")
    session_tools = _session_meta_value(records, "tools")

    steps: list[Step] = []
    for rec in records:
        role = rec.get("role")
        if role in (None, "session_meta", "tool"):
            continue
        timestamp = parse_iso_timestamp(rec.get("timestamp"))
        if role == "user":
            steps.append(
                Step(
                    step_id=str(uuid4()),
                    source=StepSource.USER,
                    message=rec.get("content", "") or "",
                    timestamp=timestamp,
                )
            )
        elif role == "assistant":
            steps.append(_build_assistant_step(rec, timestamp, session_model, tool_results_by_id))
    return steps, session_model, session_tools if isinstance(session_tools, list) else None


def _collect_tool_results(
    records: list[dict], diagnostics: DiagnosticsCollector
) -> dict[str, dict]:
    """Index tool records by ``tool_call_id`` for later pairing."""
    results: dict[str, dict] = {}
    for rec in records:
        if rec.get("role") != "tool":
            continue
        tool_call_id = rec.get("tool_call_id")
        if not tool_call_id:
            diagnostics.record_orphaned_result("")
            continue
        results[tool_call_id] = rec
        diagnostics.record_tool_result()
    return results


def _build_assistant_step(
    rec: dict,
    timestamp: datetime | None,
    session_model: str | None,
    tool_results_by_id: dict[str, dict],
) -> Step:
    """Build a single assistant Step, including any tool calls and results."""
    raw_tool_calls = rec.get("tool_calls") or []
    tool_calls, observation = _build_tool_calls_and_observation(raw_tool_calls, tool_results_by_id)
    reasoning = rec.get("reasoning")
    finish_reason = rec.get("finish_reason")
    step_extra: dict[str, Any] = {}
    if finish_reason:
        step_extra["finish_reason"] = finish_reason
    return Step(
        step_id=str(uuid4()),
        source=StepSource.AGENT,
        message=rec.get("content", "") or "",
        reasoning_content=reasoning or None,
        model_name=session_model or None,
        timestamp=timestamp,
        tool_calls=tool_calls,
        observation=observation,
        extra=step_extra or None,
    )


def _build_steps_from_snapshot(snapshot: dict, diagnostics: DiagnosticsCollector) -> list[Step]:
    """Build Step objects from a snapshot's ``messages`` array.

    Snapshot messages have no per-message timestamps; all steps share
    the session-level ``session_start`` as their coarse timestamp.
    Tool results appear as ``role=tool`` messages linked to the
    preceding assistant's tool_calls by ``tool_call_id``.
    """
    messages = snapshot.get("messages", [])
    if not isinstance(messages, list):
        return []
    diagnostics.total_lines = len(messages)
    fallback_ts = parse_iso_timestamp(snapshot.get("session_start"))
    session_model = snapshot.get("model")

    tool_results_by_id: dict[str, dict] = {}
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "tool":
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id:
                tool_results_by_id[tool_call_id] = {"content": msg.get("content", "")}
                diagnostics.record_tool_result()

    steps: list[Step] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "user":
            steps.append(
                Step(
                    step_id=str(uuid4()),
                    source=StepSource.USER,
                    message=msg.get("content", "") or "",
                    timestamp=fallback_ts,
                )
            )
            diagnostics.parsed_lines += 1
        elif role == "assistant":
            steps.append(_build_assistant_step(msg, fallback_ts, session_model, tool_results_by_id))
            diagnostics.parsed_lines += 1
        elif role == "tool":
            diagnostics.parsed_lines += 1
    return steps


def _build_tool_calls_and_observation(
    raw_tool_calls: list, tool_results_by_id: dict[str, dict]
) -> tuple[list[ToolCall], Observation | None]:
    """Turn a list of raw tool_call dicts into ToolCall + Observation."""
    if not raw_tool_calls:
        return [], None
    calls: list[ToolCall] = []
    results: list[ObservationResult] = []
    for raw in raw_tool_calls:
        if not isinstance(raw, dict):
            continue
        tool_call_id = raw.get("id") or raw.get("call_id") or ""
        function = raw.get("function") or {}
        function_name = function.get("name", "unknown")
        arguments = _parse_tool_arguments(function.get("arguments"))
        tc_extra: dict[str, Any] = {}
        if raw.get("response_item_id"):
            tc_extra["response_item_id"] = raw["response_item_id"]
        calls.append(
            ToolCall(
                tool_call_id=tool_call_id,
                function_name=function_name,
                arguments=arguments,
                extra=tc_extra or None,
            )
        )
        result = tool_results_by_id.get(tool_call_id)
        if result is not None:
            results.append(
                ObservationResult(
                    source_call_id=tool_call_id,
                    content=result.get("content", "") or "",
                )
            )
    observation = Observation(results=results) if results else None
    return calls, observation


def _parse_tool_arguments(raw: Any) -> dict | str | None:
    """Decode a tool_call arguments JSON string into a dict.

    Hermes follows the OpenAI convention and serialises ``arguments``
    as a JSON string. If decoding fails we keep the raw string so no
    data is lost.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(parsed, dict):
            return parsed
        return raw
    return None


def _list_state_db_sessions(sessions_dir: Path) -> set[str] | None:
    """Return the set of session ids known to state.db, or None if absent.

    Used by ``discover_session_files`` to filter out stale intermediate
    snapshots — files Hermes rewrote during an active session that never
    made it into the canonical state.db.  Returning ``None`` (not an empty
    set) distinguishes "db is missing, don't filter" from "db is present
    but empty, drop every snapshot-only file".
    """
    db_path = sessions_dir.parent / "state.db"
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute("SELECT id FROM sessions")
        ids = {row[0] for row in cursor if row[0]}
        conn.close()
    except sqlite3.Error as exc:
        logger.debug("state.db session list read failed: %s", exc)
        return None
    return ids


def _load_state_db(sessions_dir: Path, session_id: str) -> dict | None:
    """Read the single sessions row for a session_id, if present.

    state.db is at ``~/.hermes/state.db``; when the parser is invoked
    against an extracted archive the file may be missing or located in
    a different place. Opening read-only avoids any write contention
    with a running Hermes process.
    """
    db_path = sessions_dir.parent / "state.db"
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Column names are a module-level constant tuple, not user input,
        # so there is no SQL-injection surface here.
        cols = ", ".join(_STATE_DB_COLUMNS)
        cursor = conn.execute(
            f"SELECT {cols} FROM sessions WHERE id = ?",  # noqa: S608
            (session_id,),
        )
        row = cursor.fetchone()
        conn.close()
    except sqlite3.Error as exc:
        logger.debug("state.db read failed for %s: %s", session_id, exc)
        return None
    if not row:
        return None
    return {col: row[col] for col in _STATE_DB_COLUMNS}


def _load_index_entry(sessions_dir: Path, session_id: str) -> dict | None:
    """Find the origin metadata for a session_id in sessions.json."""
    index_path = sessions_dir / "sessions.json"
    if not index_path.is_file():
        return None
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(index, dict):
        return None
    for entry in index.values():
        if isinstance(entry, dict) and entry.get("session_id") == session_id:
            return entry
    return None


def _attach_session_metrics_to_last_assistant(
    steps: list[Step], db_row: dict | None, session_model: str | None
) -> None:
    """Fold state.db session-level token totals onto the last assistant step.

    Hermes tracks tokens at session level only, but VibeLens's dashboard
    aggregator (``services/dashboard/stats.py`` and ``pricing.py``) reads
    from ``Step.metrics`` per-step rather than from ``Trajectory.final_metrics``.
    Attaching the session totals as a single ``Metrics`` record on the last
    assistant step lets those aggregators see real tokens and compute cost
    via the pricing table, without duplicating totals across multiple steps.
    The step also needs ``model_name`` populated so ``compute_step_cost``
    can look up pricing.
    """
    if not db_row:
        return
    input_tokens = db_row.get("input_tokens") or 0
    output_tokens = db_row.get("output_tokens") or 0
    if input_tokens == 0 and output_tokens == 0:
        return

    for step in reversed(steps):
        if step.source != StepSource.AGENT:
            continue
        cache_read = db_row.get("cache_read_tokens") or 0
        cache_write = db_row.get("cache_write_tokens") or 0
        # Total prompt tokens as reported by Hermes already include
        # cached reads; combine for the Metrics.prompt_tokens convention.
        step.metrics = Metrics(
            prompt_tokens=input_tokens + cache_read,
            completion_tokens=output_tokens,
            cached_tokens=cache_read,
            cache_creation_tokens=cache_write,
        )
        if not step.model_name and session_model:
            step.model_name = session_model
        return


def _build_final_metrics(
    steps: list[Step], db_row: dict | None, session_start: datetime | None
) -> FinalMetrics | None:
    """Compute FinalMetrics, overlaying real token/cost data from state.db.

    When a state.db row exists, its session-level totals override the
    step-aggregated zeros that ``_compute_final_metrics`` produces
    (hermes has no per-step metrics). Duration comes from
    ``ended_at - started_at`` when available, else from step timestamps.
    """
    tool_call_count = sum(len(s.tool_calls) for s in steps)
    total_steps = len(steps)
    duration = _compute_duration(steps)

    if db_row:
        started = db_row.get("started_at")
        ended = db_row.get("ended_at")
        if started is not None and ended is not None:
            duration = max(int(ended - started), 0)
        cost = db_row.get("actual_cost_usd") or db_row.get("estimated_cost_usd")
        reasoning_tokens = db_row.get("reasoning_tokens") or 0
        extra: dict[str, Any] = {}
        if reasoning_tokens:
            extra["reasoning_tokens"] = reasoning_tokens
        return FinalMetrics(
            duration=duration,
            total_steps=total_steps,
            tool_call_count=tool_call_count,
            total_prompt_tokens=db_row.get("input_tokens") or 0,
            total_completion_tokens=db_row.get("output_tokens") or 0,
            total_cache_read=db_row.get("cache_read_tokens") or 0,
            total_cache_write=db_row.get("cache_write_tokens") or 0,
            total_cost_usd=cost,
            extra=extra or None,
        )

    # No db row: token totals are genuinely unknown.
    return FinalMetrics(
        duration=duration,
        total_steps=total_steps,
        tool_call_count=tool_call_count,
        total_prompt_tokens=None,
        total_completion_tokens=None,
    )


def _compute_duration(steps: list[Step]) -> int:
    """Wall-clock seconds between the first and last step timestamps."""
    timestamps = [s.timestamp for s in steps if s.timestamp]
    if len(timestamps) < 2:
        return 0
    return int((max(timestamps) - min(timestamps)).total_seconds())


_DEFAULT_PROJECT_PATH = "hermes://local"


def _derive_project_path(platform: str | None, origin: dict | None, db_row: dict | None) -> str:
    """Synthesise a ``project_path`` for a Hermes session.

    Hermes doesn't persist a filesystem cwd for its sessions. For the
    UI to group related conversations we instead derive a logical
    location URI from the chat platform and id:

      - Slack (and similar platforms with a chat_id) →
        ``slack://<chat_id>`` (e.g. ``slack://D0ATU26RX1Q``)
      - CLI sessions → ``hermes://cli``
      - Anything else → ``hermes://<platform>`` or ``hermes://local``

    This gives each chat / surface its own "project" and keeps unrelated
    chats from being bucketed together.
    """
    origin_details: dict = {}
    if origin:
        detail = origin.get("origin")
        origin_details = detail if isinstance(detail, dict) else origin

    effective_platform = (
        platform or origin_details.get("platform") or (db_row.get("source") if db_row else None)
    )
    chat_id = origin_details.get("chat_id") if origin_details else None

    if effective_platform and chat_id:
        return f"{effective_platform}://{chat_id}"
    if effective_platform == "cli":
        return "hermes://cli"
    if effective_platform:
        return f"hermes://{effective_platform}"
    return _DEFAULT_PROJECT_PATH


def _build_trajectory_extra(
    platform: str | None,
    base_url: str | None,
    system_prompt: str | None,
    db_row: dict | None,
    origin: dict | None,
    diagnostics: dict | None,
) -> dict[str, Any] | None:
    """Assemble the per-trajectory ``extra`` dict from all enrichment sources."""
    extra: dict[str, Any] = {}
    if platform:
        extra["platform"] = platform
    if base_url:
        extra["base_url"] = base_url
    if system_prompt:
        extra["system_prompt"] = system_prompt
    if db_row:
        for key in ("title", "end_reason", "cost_status", "cost_source", "billing_provider"):
            value = db_row.get(key)
            if value:
                extra[key] = value
        source = db_row.get("source")
        if source and source != platform:
            extra["source"] = source
    if origin:
        origin_details = origin.get("origin") if isinstance(origin.get("origin"), dict) else {}
        for key in ("chat_type", "chat_id", "user_name", "thread_id"):
            value = origin_details.get(key) if origin_details else origin.get(key)
            if value:
                extra[key] = value
    if diagnostics:
        extra.update(diagnostics)
    return extra or None
