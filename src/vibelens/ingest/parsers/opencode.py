"""OpenCode session parser.

OpenCode (https://github.com/sst/opencode) stores all sessions for a user in
a single SQLite database at ``~/.local/share/opencode/opencode.db`` using a
Drizzle ORM schema. Tables:

    session(id, project_id, parent_id, slug, directory, title, version, ...,
            summary_additions, summary_deletions, summary_files, summary_diffs,
            time_created, time_updated, time_compacting, time_archived,
            workspace_id)
    message(id, session_id, time_created, time_updated, data)   -- data = JSON
    part(id, message_id, session_id, time_created, time_updated, data)
    todo(session_id, content, status, priority, position, ...)
    project(id, worktree, vcs, name, ..., commands, icon_url_override?)

Per-message ``data`` JSON shape (verified):
    {role, agent, mode, modelID, providerID, parentID,
     path.{cwd, root}, cost, finish, time.{created, completed},
     tokens.{input, output, reasoning, total, cache.{read, write}},
     tools.{<tool>: bool}, summary.diffs[...], error.{name, data.message},
     editorContext.{openTabs, shell}}     # editorContext only in Kilo

Per-part ``data`` JSON shapes:
    text         {type, text, time.{start?, end?}}
    reasoning    {type, text, time.{start, end}, metadata.anthropic.signature}
    tool         {type, tool, callID, state.{status, input, output|error,
                                              time, metadata, title}}
    step-start   {type, snapshot}
    step-finish  {type, snapshot, reason, cost, tokens}
    patch        {type, hash, files[]}

Sub-agent linkage:
    parent → child: tool.state.metadata.sessionId  (when tool=="task")
    child  → parent: session.parent_id column

Parser is multi-session-per-file: ``parse(opencode.db)`` returns one
Trajectory per session row. ``discover_session_files`` returns ``[opencode.db]``
when present.

Capability vs Claude reference parser:
  - text content                   ✓
  - reasoning content              ✓ (``reasoning`` parts)
  - tool calls + observations      ✓ (``tool`` parts with paired callID)
  - sub-agents (parent linkage)    ✓ via SQL ``session.parent_id`` column
  - sub-agents (depth >1)          ✗ // TODO(opencode-nested): the SQL
                                     ``parent_id`` walk in
                                     ``_build_session_with_children`` only
                                     follows depth-1 children. Recurse on
                                     ``parent_id`` chain when nested sub-
                                     agents appear in observed data.
  - multimodal images (inline)     ✓ (``file`` parts with ``data:`` URLs)
  - non-image file attachments     ✗ // TODO(opencode-files): docs/PDFs
                                     show up as ``file`` parts with
                                     ``mime != image/*``; surface them as
                                     ATIF document ContentParts once the
                                     renderer can show them.
  - persistent output files        ✗ no large-output split.
  - continuation refs (prev/next)  ✗ no resume workflow.

Future work:
  // TODO(snapshot): the snapshot/ tree carries Git-like file content store;
     surface as ATIF replay states once ATIF has a slot for it.
  // TODO(session-entry): session_entry table empty in observed data; revisit
     when populated.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser, DiscoveredSession
from vibelens.ingest.parsers.helpers import (
    build_multimodal_message,
    data_url_to_image_content_part,
)
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import (
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.models.trajectories.content import ContentPart
from vibelens.models.trajectories.trajectory_ref import TrajectoryRef
from vibelens.utils import get_logger

logger = get_logger(__name__)

# Fallback regex for parsing child session id out of a task tool's output text
# (used when state.metadata.sessionId is absent).
_TASK_OUTPUT_SESSION_ID_RE = re.compile(r"task_id:\s*(ses_\w+)")

# Optional columns we might select that may not exist on older Kilo databases.
_PROJECT_OPTIONAL_COLUMNS = ("icon_url_override",)

# OpenCode's (and inheriting Kilo's) dedicated skill-activation tool. Activation
# only — reading a SKILL.md via read/bash doesn't count.
_SKILL_TOOL_NAMES: frozenset[str] = frozenset({"skill"})


class OpencodeParser(BaseParser):
    """Parser for OpenCode's SQLite session database."""

    AGENT_TYPE = AgentType.OPENCODE
    LOCAL_DATA_DIR: Path | None = Path.home() / ".local" / "share" / "opencode"
    DB_FILENAME: ClassVar[str] = "opencode.db"
    # SQLite-backed: zip extraction needs the .db file plus its WAL/SHM
    # sidecars to read uncommitted pages. Subclasses (Kilo) inherit these.
    ALLOWED_EXTENSIONS: ClassVar[frozenset[str]] = BaseParser.ALLOWED_EXTENSIONS | {
        ".db",
        ".db-wal",
        ".db-shm",
    }
    # Session ids in the SQLite ``session.id`` column are already globally
    # unique (``ses_*``), and discover_sessions reads them directly so there's
    # no filename-derived sid to namespace.
    NAMESPACE_SESSION_IDS = False

    # ---- Discovery ----
    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Return ``[<data_dir>/<DB_FILENAME>]`` if the file exists."""
        candidate = data_dir / self.DB_FILENAME
        return [candidate] if candidate.is_file() else []

    def discover_sessions(self, data_dir: Path) -> list[DiscoveredSession]:
        """Enumerate every session row in the SQLite db.

        Reads ``id`` and ``time_updated`` from the ``session`` table so
        LocalStore can detect per-session changes (each row's
        ``time_updated`` is independent — touching one session doesn't
        bump the others). ``mtime_ns`` is converted from ms to ns to align
        with the units used by single-session-per-file parsers.
        """
        db_path = data_dir / self.DB_FILENAME
        if not db_path.is_file():
            return []
        try:
            conn = self._open_readonly(db_path)
        except sqlite3.Error as exc:
            logger.warning("Cannot open %s: %s", db_path, exc)
            return []
        try:
            rows = conn.execute("SELECT id, time_updated FROM session").fetchall()
        except sqlite3.Error as exc:
            logger.warning("Failed to read session table from %s: %s", db_path, exc)
            return []
        finally:
            conn.close()
        return [
            DiscoveredSession(
                path=db_path,
                session_id=row["id"],
                # Convert ms → ns; preserves ordering with file-mtime values.
                mtime_ns=(row["time_updated"] or 0) * 1_000_000,
            )
            for row in rows
            if row["id"]
        ]

    def get_session_files(self, session_file: Path) -> list[Path]:
        """All session data lives in the single db file."""
        return [session_file]

    def parse_skeletons_for_file(self, file_path: Path) -> list[Trajectory]:
        """Return one skeleton per session row in the db.

        Multi-session-per-file: ``parse_session_index`` already builds skeletons
        from the session table; we delegate to it. The orphan path in
        index_builder calls this when a session isn't covered by the fast
        index, so dropping back to it ensures consistency.
        """
        return self.parse_session_index(file_path.parent) or []

    def parse_session(self, file_path: Path, session_id: str) -> list[Trajectory] | None:
        """SQL-filtered single-session load.

        Loads only the requested session row plus its direct children
        (``WHERE parent_id = ?``) and the messages/parts for that subset.
        ~40 rows for a typical session vs. ~660 for a full-db parse.

        Sub-agent depth scope: captures depth-1 children only. OpenCode's
        observed data has no nested spawns; if that changes, walk
        ``parent_id`` recursively here.
        """
        if not file_path.is_file():
            return None
        try:
            conn = self._open_readonly(file_path)
        except sqlite3.Error as exc:
            logger.warning("Cannot open %s: %s", file_path, exc)
            return None
        try:
            return _build_session_with_children(conn, session_id, parser=self)
        except sqlite3.Error as exc:
            logger.warning("Failed to load session %s: %s", session_id, exc)
            return None
        finally:
            conn.close()

    # ---- Indexing (multi-session-per-file fast path) ----
    def parse_session_index(self, data_dir: Path) -> list[Trajectory] | None:
        """Build skeleton trajectories from the session table, one per row.

        Multi-session-per-file fast path: ``discover_session_files`` returns
        the single db file, but the file holds N sessions. Without this fast
        index, ``parse_skeleton_for_file`` would only surface the first
        trajectory (BaseParser default takes ``trajs[0]``). We read the
        ``session`` table directly and emit one skeleton per row, each
        tagged with ``extra.rollout_path`` so the LocalStore reconciler
        can map them back to the shared db file.

        ``first_message`` is populated from the first user-role message's
        first text part — required by ``_dedup_and_validate`` (sessions
        without it get dropped from the index).
        """
        db_path = data_dir / self.DB_FILENAME
        if not db_path.is_file():
            return []
        try:
            conn = self._open_readonly(db_path)
        except sqlite3.Error as exc:
            logger.warning("Cannot open SQLite db %s: %s", db_path, exc)
            return []
        try:
            project_lookup = _build_project_lookup(conn)
            session_rows = conn.execute("SELECT * FROM session ORDER BY time_created").fetchall()
            first_messages = _collect_first_user_messages(conn)
        except sqlite3.Error as exc:
            logger.warning("Failed to read session index from %s: %s", db_path, exc)
            return []
        finally:
            conn.close()

        skeletons: list[Trajectory] = []
        for row in session_rows:
            sid = row["id"]
            first_msg = first_messages.get(sid) or row["title"] or sid
            traj = Trajectory(
                session_id=sid,
                agent=self.build_agent(version=row["version"]),
                project_path=row["directory"] or None,
                first_message=first_msg,
                created_at=_ms_to_datetime(row["time_created"]),
                updated_at=_ms_to_datetime(row["time_updated"]),
                extra={
                    **(_build_session_extra(row, project_lookup) or {}),
                    "rollout_path": str(db_path),
                },
            )
            if row["parent_id"]:
                traj.parent_trajectory_ref = TrajectoryRef(session_id=row["parent_id"])
            skeletons.append(traj)
        return skeletons

    # ---- Multi-session parse ----
    def parse(self, file_path: Path) -> list[Trajectory]:
        """Parse every session row in the SQLite db into a Trajectory.

        Returns ``[]`` for a missing file or a non-SQLite blob at the path —
        ``parse`` never raises per the BaseParser contract.
        """
        if not file_path.is_file():
            return []
        try:
            conn = self._open_readonly(file_path)
        except sqlite3.Error as exc:
            logger.warning("Cannot open SQLite db %s: %s", file_path, exc)
            return []
        try:
            return list(self._iter_trajectories(conn))
        except sqlite3.Error as exc:
            logger.warning("Failed to read SQLite db %s: %s", file_path, exc)
            return []
        finally:
            conn.close()

    def _open_readonly(self, db_path: Path) -> sqlite3.Connection:
        """Open the db read-only without skipping WAL recovery.

        ``mode=ro`` lets SQLite serve uncommitted WAL pages from a live writer;
        ``immutable=1`` would skip WAL discovery and produce stale reads.
        """
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _iter_trajectories(self, conn: sqlite3.Connection):
        """Yield one Trajectory per session row."""
        # Build project lookup once.
        project_lookup = _build_project_lookup(conn)
        rows = conn.execute("SELECT * FROM session ORDER BY time_created").fetchall()
        for row in rows:
            diagnostics = DiagnosticsCollector()
            try:
                traj = self._row_to_trajectory(conn, row, project_lookup, diagnostics)
            except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                logger.warning("Failed to parse session %s: %s", row["id"], exc, exc_info=True)
                diagnostics.record_skip(f"session {row['id']}: {exc!r}")
                continue
            if traj is not None and traj.steps:
                yield self._finalize(traj, diagnostics)

    def _row_to_trajectory(
        self,
        conn: sqlite3.Connection,
        session_row: sqlite3.Row,
        project_lookup: dict[str, dict],
        diagnostics: DiagnosticsCollector,
    ) -> Trajectory | None:
        """Build a Trajectory from one session row + its messages + parts.

        Used by the full-db parse path. Loads messages, parts, and todos
        for this session via three targeted queries.
        """
        session_id = session_row["id"]
        if not session_id:
            return None
        msg_rows = conn.execute(
            "SELECT * FROM message WHERE session_id=? ORDER BY time_created",
            (session_id,),
        ).fetchall()
        part_rows = conn.execute(
            "SELECT * FROM part WHERE session_id=? ORDER BY message_id, time_created",
            (session_id,),
        ).fetchall()
        todo_rows = conn.execute(
            "SELECT content, status, priority, position FROM todo "
            "WHERE session_id=? ORDER BY position",
            (session_id,),
        ).fetchall()
        return self._row_to_trajectory_from_preloaded(
            session_row, msg_rows, part_rows, todo_rows, project_lookup, diagnostics
        )

    def _row_to_trajectory_from_preloaded(
        self,
        session_row: sqlite3.Row,
        msg_rows: list[sqlite3.Row],
        part_rows: list[sqlite3.Row],
        todo_rows: list[sqlite3.Row],
        project_lookup: dict[str, dict],
        diagnostics: DiagnosticsCollector,
    ) -> Trajectory | None:
        """Build a Trajectory from already-loaded message/part/todo rows.

        Used by ``parse_session`` to avoid running per-session SELECTs after
        a single batched fetch covering the main session and its children.
        ``msg_rows`` / ``part_rows`` may include rows for other sessions —
        we filter by ``session_id`` here.
        """
        session_id = session_row["id"]
        if not session_id:
            return None

        traj = Trajectory(
            session_id=session_id,
            agent=self.build_agent(version=session_row["version"]),
            project_path=session_row["directory"] or None,
            extra=_build_session_extra(session_row, project_lookup),
        )
        if session_row["parent_id"]:
            traj.parent_trajectory_ref = TrajectoryRef(session_id=session_row["parent_id"])

        own_msgs = [m for m in msg_rows if m["session_id"] == session_id]
        if not own_msgs:
            return None
        own_parts = [p for p in part_rows if p["session_id"] == session_id]
        parts_by_message = _group_parts_by_message(own_parts)

        own_todos = [t for t in todo_rows if t["session_id"] == session_id]
        if own_todos:
            traj.extra = {**(traj.extra or {}), "todos": [dict(r) for r in own_todos]}

        steps: list[Step] = []
        for msg_row in own_msgs:
            msg_data = _safe_json(msg_row["data"])
            if msg_data is None:
                diagnostics.record_skip(f"message {msg_row['id']}: invalid JSON in data column")
                continue
            parts = parts_by_message.get(msg_row["id"], [])
            step = _build_step_from_message(msg_row, msg_data, parts, diagnostics)
            if step is None:
                continue
            steps.append(step)
        traj.steps = steps

        for msg_row in reversed(own_msgs):
            data = _safe_json(msg_row["data"]) or {}
            if data.get("role") == "assistant" and data.get("modelID"):
                traj.agent.model_name = data["modelID"]
                break
        return traj


def _build_session_with_children(
    conn: sqlite3.Connection, session_id: str, parser: OpencodeParser
) -> list[Trajectory] | None:
    """Build ``[main, *children]`` for one session via SQL filtering.

    Three ``SELECT * FROM session`` queries plus two batched IN-clause
    queries. For a typical session (~10 messages, ~30 parts, optionally
    one sub-agent), loads ~40-80 rows instead of full-db ~660.
    """
    main_row = conn.execute("SELECT * FROM session WHERE id = ?", (session_id,)).fetchone()
    if main_row is None:
        return None
    child_rows = conn.execute("SELECT * FROM session WHERE parent_id = ?", (session_id,)).fetchall()
    all_session_rows: list[sqlite3.Row] = [main_row, *child_rows]
    sids = [r["id"] for r in all_session_rows]
    placeholders = ",".join("?" * len(sids))
    msg_rows = conn.execute(
        f"SELECT * FROM message WHERE session_id IN ({placeholders}) "
        f"ORDER BY session_id, time_created",
        sids,
    ).fetchall()
    part_rows = conn.execute(
        f"SELECT * FROM part WHERE session_id IN ({placeholders}) "
        f"ORDER BY session_id, message_id, time_created",
        sids,
    ).fetchall()
    todo_rows = conn.execute(
        f"SELECT session_id, content, status, priority, position FROM todo "
        f"WHERE session_id IN ({placeholders}) ORDER BY session_id, position",
        sids,
    ).fetchall()
    project_lookup = _build_project_lookup(conn)
    out: list[Trajectory] = []
    for srow in all_session_rows:
        diagnostics = DiagnosticsCollector()
        traj = parser._row_to_trajectory_from_preloaded(
            srow, msg_rows, part_rows, todo_rows, project_lookup, diagnostics
        )
        if traj is not None and traj.steps:
            out.append(parser._finalize(traj, diagnostics))
    return out or None


def _collect_first_user_messages(conn: sqlite3.Connection) -> dict[str, str]:
    """For each session, find the first text content from its earliest user message.

    Used by ``parse_session_index`` to populate ``Trajectory.first_message``
    without parsing the entire session — ``_dedup_and_validate`` drops any
    skeleton without a first_message. One JOIN, bounded by sessions.
    """
    rows = conn.execute(
        """
        WITH first_user_msg AS (
            SELECT m.session_id, m.id AS message_id, m.time_created,
                   ROW_NUMBER() OVER (
                       PARTITION BY m.session_id
                       ORDER BY m.time_created
                   ) AS rank
            FROM message m
            WHERE json_extract(m.data, '$.role') = 'user'
        )
        SELECT fum.session_id, p.data
        FROM first_user_msg fum
        JOIN part p ON p.message_id = fum.message_id
        WHERE fum.rank = 1
          AND json_extract(p.data, '$.type') = 'text'
        ORDER BY p.time_created
        """
    ).fetchall()
    out: dict[str, str] = {}
    for row in rows:
        if row["session_id"] in out:
            continue  # keep the earliest text part only
        data = _safe_json(row["data"]) or {}
        text = (data.get("text") or "").strip()
        if text:
            out[row["session_id"]] = text
    return out


def _build_project_lookup(conn: sqlite3.Connection) -> dict[str, dict]:
    """Map project_id -> selected columns; tolerates missing optional columns."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(project)")}
    base_cols = ["id", "worktree", "vcs", "name"]
    select_cols = [c for c in base_cols if c in cols]
    if not select_cols:
        return {}
    optional = [c for c in _PROJECT_OPTIONAL_COLUMNS if c in cols]
    select = ", ".join(select_cols + optional)
    rows = conn.execute(f"SELECT {select} FROM project").fetchall()
    return {row["id"]: dict(row) for row in rows}


def _build_session_extra(row: sqlite3.Row, project_lookup: dict[str, dict]) -> dict | None:
    """Return Trajectory.extra contents derived from a session row."""
    extra: dict[str, Any] = {}
    row_keys = set(row.keys())
    for src, dst in (
        ("slug", "slug"),
        ("title", "title"),
        ("version", "version"),
        ("share_url", "share_url"),
        ("revert", "revert"),
        ("workspace_id", "workspace_id"),
    ):
        val = row[src] if src in row_keys else None
        if val is not None:
            extra[dst] = val
    summary = {
        "additions": row["summary_additions"],
        "deletions": row["summary_deletions"],
        "files": row["summary_files"],
    }
    if row["summary_diffs"]:
        summary["diffs"] = _safe_json(row["summary_diffs"])
    if any(v is not None for v in summary.values()):
        extra["summary"] = {k: v for k, v in summary.items() if v is not None}
    if row["time_compacting"]:
        extra["time_compacting"] = row["time_compacting"]
    if row["time_archived"]:
        extra["time_archived"] = row["time_archived"]
    project = project_lookup.get(row["project_id"])
    if project:
        if project.get("worktree"):
            extra["project_worktree"] = project["worktree"]
        if project.get("vcs"):
            extra["project_vcs"] = project["vcs"]
        if project.get("name"):
            extra["project_name"] = project["name"]
    return extra or None


def _group_parts_by_message(part_rows) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in part_rows:
        grouped.setdefault(row["message_id"], []).append(row)
    return grouped


def _build_step_from_message(
    msg_row: sqlite3.Row,
    msg_data: dict,
    parts: list[sqlite3.Row],
    diagnostics: DiagnosticsCollector,
) -> Step | None:
    """Convert a message row + its parts into a Step."""
    role = msg_data.get("role")
    source = StepSource.USER if role == "user" else StepSource.AGENT

    text_parts: list[str] = []
    image_parts: list[ContentPart] = []
    reasoning_parts: list[str] = []
    reasoning_signatures: list[str] = []
    tool_calls: list[ToolCall] = []
    obs_results: list[ObservationResult] = []
    patches: list[dict] = []
    boundaries: list[dict] = []
    compaction_meta: dict | None = None

    for part_row in parts:
        part_data = _safe_json(part_row["data"])
        if part_data is None:
            diagnostics.record_skip(f"part {part_row['id']}: invalid JSON")
            continue
        part_type = part_data.get("type")
        if part_type == "text":
            text = part_data.get("text") or ""
            if text:
                text_parts.append(text)
        elif part_type == "file":
            image_part = _file_part_to_image_content_part(part_data)
            if image_part is not None:
                image_parts.append(image_part)
            else:
                diagnostics.record_skip(f"file part {part_row['id']}: missing/unsupported url")
        elif part_type == "reasoning":
            reasoning_parts.append(part_data.get("text") or "")
            sig = (part_data.get("metadata") or {}).get("anthropic", {}).get("signature")
            if sig:
                reasoning_signatures.append(sig)
        elif part_type == "tool":
            tc, obs = _build_tool_pair(part_data)
            if tc is not None:
                tool_calls.append(tc)
                diagnostics.record_tool_call()
            if obs is not None:
                obs_results.append(obs)
                diagnostics.record_tool_result()
        elif part_type == "patch":
            patches.append({"hash": part_data.get("hash"), "files": part_data.get("files", [])})
        elif part_type == "step-finish":
            boundaries.append(
                {
                    "snapshot": part_data.get("snapshot"),
                    "reason": part_data.get("reason"),
                    "tokens": part_data.get("tokens"),
                    "cost": part_data.get("cost"),
                }
            )
        elif part_type == "step-start":
            # Boundary marker only; snapshot reappears on step-finish.
            pass
        elif part_type == "compaction":
            # OpenCode emits one ``compaction`` part on the message that
            # marks a context-window auto-compaction or overflow event.
            # We surface the flags as Step.extra so the UI can label this
            # turn as the compaction boundary without losing the message.
            compaction_meta = {k: part_data[k] for k in ("auto", "overflow") if k in part_data}
        else:
            diagnostics.record_skip(f"unknown part type {part_type!r}")

    text = "".join(text_parts)
    reasoning_text = "".join(reasoning_parts) or None

    if (
        not text
        and not image_parts
        and not tool_calls
        and not reasoning_text
        and not compaction_meta
    ):
        return None

    message = build_multimodal_message(text, image_parts)

    metrics = _build_step_metrics(msg_data)
    extra = _build_step_extra(msg_data, patches, boundaries, reasoning_signatures)
    # OpenCode-specific compaction metadata (auto / overflow flags) stays in
    # ``extra``; the canonical boundary signal is the typed ``is_compaction``.
    if compaction_meta is not None:
        extra = {**(extra or {}), "compaction": compaction_meta}

    return Step(
        step_id=msg_row["id"],
        timestamp=_ms_to_datetime(msg_row["time_created"]),
        source=source,
        model_name=msg_data.get("modelID"),
        message=message,
        reasoning_content=reasoning_text,
        tool_calls=tool_calls,
        observation=Observation(results=obs_results) if obs_results else None,
        metrics=metrics,
        is_compaction=True if compaction_meta is not None else None,
        extra=extra,
    )


def _file_part_to_image_content_part(part_data: dict) -> ContentPart | None:
    """Decode an OpenCode ``file`` part into an inline image ``ContentPart``.

    OpenCode/Kilo serialize attached images as
    ``{type: file, mime: image/png, url: "data:image/png;base64,<...>"}``.
    The explicit ``mime`` field overrides whatever the data URL header
    carries; the URL itself is decoded by the shared
    :func:`data_url_to_image_content_part` helper.

    Future work: support http(s) URL fetching and document mime types
    (PDF, etc.) once the renderer can show them.
    """
    fallback_mime = part_data.get("mime") or "image/png"
    return data_url_to_image_content_part(part_data.get("url") or "", fallback_mime)


def _build_tool_pair(part_data: dict) -> tuple[ToolCall | None, ObservationResult | None]:
    """Convert one tool part into a (ToolCall, ObservationResult) pair."""
    state = part_data.get("state") or {}
    call_id = part_data.get("callID") or ""
    function_name = part_data.get("tool") or ""

    tc_extra: dict[str, Any] = {}
    title = state.get("title")
    if title:
        tc_extra["title"] = title
    metadata = state.get("metadata")
    if metadata:
        tc_extra["metadata"] = metadata
    time_info = state.get("time")
    if time_info:
        tc_extra["time"] = time_info
    tc = ToolCall(
        tool_call_id=call_id,
        function_name=function_name,
        arguments=state.get("input"),
        is_skill=True if function_name in _SKILL_TOOL_NAMES else None,
        extra=tc_extra or None,
    )

    status = state.get("status")
    is_error = status == "error"
    text = (state.get("error") or "") if is_error else (state.get("output") or "")

    obs_extra: dict[str, Any] = {}
    if metadata:
        obs_extra["metadata"] = metadata
    subagent_ref = _extract_subagent_ref(part_data, state)
    obs = ObservationResult(
        source_call_id=call_id,
        content=text,
        is_error=is_error,
        subagent_trajectory_ref=[subagent_ref] if subagent_ref else None,
        extra=obs_extra or None,
    )
    return tc, obs


def _extract_subagent_ref(part_data: dict, state: dict) -> TrajectoryRef | None:
    """Pull child session id from state.metadata.sessionId or output regex."""
    if part_data.get("tool") != "task":
        return None
    metadata = state.get("metadata") or {}
    session_id = metadata.get("sessionId")
    if session_id:
        return TrajectoryRef(session_id=session_id)
    # Fallback: regex on tool output
    output = state.get("output") or ""
    match = _TASK_OUTPUT_SESSION_ID_RE.search(output)
    if match:
        return TrajectoryRef(session_id=match.group(1))
    return None


def _build_step_metrics(msg_data: dict) -> Metrics | None:
    """Build a Metrics from message.tokens + message.cost."""
    tokens = msg_data.get("tokens") or {}
    cache = tokens.get("cache") or {}
    input_tokens = tokens.get("input") or 0
    output_tokens = tokens.get("output") or 0
    cache_read = cache.get("read") or 0
    cache_write = cache.get("write") or 0
    cost = msg_data.get("cost")
    reasoning = tokens.get("reasoning") or 0
    if not any((input_tokens, output_tokens, cache_read, cache_write, cost, reasoning)):
        return None
    extra = {"reasoning_output_tokens": reasoning} if reasoning else None
    return Metrics.from_tokens(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cost_usd=cost,
        extra=extra,
    )


def _build_step_extra(
    msg_data: dict, patches: list[dict], boundaries: list[dict], reasoning_signatures: list[str]
) -> dict | None:
    """Build per-step extra from message data + accumulated parts."""
    extra: dict[str, Any] = {}
    for src, dst in (
        ("agent", "agent_role"),
        ("mode", "mode"),
        ("providerID", "provider_id"),
        ("parentID", "parent_message_id"),
        ("finish", "finish_reason"),
    ):
        val = msg_data.get(src)
        if val is not None:
            extra[dst] = val
    path = msg_data.get("path") or {}
    if path.get("cwd"):
        extra["path_cwd"] = path["cwd"]
    if path.get("root"):
        extra["path_root"] = path["root"]
    summary = msg_data.get("summary")
    if isinstance(summary, dict) and summary.get("diffs"):
        extra["message_summary_diffs"] = summary["diffs"]
    tools = msg_data.get("tools")
    if isinstance(tools, dict) and tools:
        extra["tools_enabled"] = tools
    error = msg_data.get("error")
    if error:
        extra["error"] = error
    editor_ctx = msg_data.get("editorContext")
    if editor_ctx:
        extra["editor_context"] = editor_ctx
    if patches:
        extra["patches"] = patches
    if boundaries:
        extra["boundaries"] = boundaries
    if reasoning_signatures:
        extra["reasoning_signatures"] = reasoning_signatures
    return extra or None


def _safe_json(raw: Any) -> dict | None:
    """Decode a JSON string; return None on any failure."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _ms_to_datetime(value: Any) -> datetime | None:
    """Convert a millisecond Unix epoch into a UTC datetime."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
