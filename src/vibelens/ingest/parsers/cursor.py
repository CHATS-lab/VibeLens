"""Cursor (Cursor CLI / IDE chat) session parser.

Cursor stores each chat session in two parallel locations:

1. ``~/.cursor/chats/<workspace-hash>/<sid>/store.db`` — SQLite database with
   the **complete** session state. Tables:

       blobs (id TEXT PRIMARY KEY, data BLOB)
       meta  (key TEXT PRIMARY KEY, value TEXT)

   The ``blobs`` table holds two distinct payload kinds:

       (a) JSON-encoded message blobs of shape ``{role, content[], id?,
           providerOptions}``. ``content[]`` carries Anthropic-style content
           blocks: ``text`` / ``tool-call`` / ``tool-result`` / ``image`` /
           ``reasoning``.
       (b) Binary protobuf "tree node" blobs that knit messages into a
           Merkle DAG (each node points at parent message hashes). These
           are the source of truth for branch ordering, but for VibeLens we
           only want the linear current-thread view.

   We rely on **SQLite's `rowid` insertion order** for chronological
   ordering of the JSON message blobs. Cursor inserts blobs as the chat
   progresses, and `ORDER BY rowid` matches user-visible order in
   observed sessions. Walking the protobuf tree is overkill for our use.

2. ``~/.cursor/projects/<project-hash>/agent-transcripts/<sid>/<sid>.jsonl``
   — a "write-only export" plain transcript. It is **partial** (text +
   ``tool_use`` blocks only — no tool_result, image, reasoning, or
   compaction markers) and exists for human-readable debugging. We use it
   only to:

       - Recover the project path (the project-hash directory contains
         ``repo.json`` with workspace info).
       - Discover sub-agent files at ``subagents/<child-sid>.jsonl``.

Capability vs Claude reference parser:
  - text content                  ✓ (SQLite ``text`` blocks)
  - reasoning content             ✗ // TODO(cursor-reasoning): SQLite stores
                                    ``type: reasoning`` blocks, but for
                                    OpenAI-provider sessions the only
                                    populated field is ``signature.encrypted_content``
                                    (text is empty). The provider encrypts
                                    chain-of-thought; nothing decodable to
                                    surface. Re-evaluate if Cursor switches
                                    providers or exposes a plaintext field.
  - tool calls + observations     ✓ (SQLite ``tool-call`` / ``tool-result``,
                                    paired by ``toolCallId``)
  - sub-agents (sibling files)    ✓ ``subagents/*.jsonl`` directory walk.
                                    // TODO(cursor-subagent-pairing): Cursor's
                                    ``Subagent`` ``tool-call`` blocks have no
                                    Anthropic-style ``id`` field, and child
                                    files don't carry parent-call references.
                                    Best-effort temporal pairing matches the
                                    i-th Subagent call to the i-th child by
                                    creation time. Could improve by hashing
                                    the spawning prompt against each child's
                                    first user message.
  - multimodal images (inline)    ✓ ``type: image`` blocks with
                                    ``image: {__type: Uint8Array, hex: ...}``
                                    decoded into base64 ContentParts.
  - compaction                    ✓ ``providerOptions.cursor.isSummary: True``
                                    flag on user-role blobs marks the
                                    boundary of a Cursor auto-summarisation.
                                    The summary text lives in the message body.
  - skills                        ✗ // TODO(cursor-skills): Cursor's Skills
                                    (``~/.cursor/skills-cursor/<name>/SKILL.md``)
                                    activate by injecting SKILL.md content
                                    into the system prompt — they are not
                                    explicit tool calls. The session log
                                    therefore has no structural marker
                                    distinguishing skill-driven turns from
                                    regular ones. Could heuristically flag
                                    when ``ReadFile`` targets a SKILL.md
                                    inside ``skills-cursor/``, but that's
                                    parser-side guesswork rather than a
                                    real signal.
  - persistent output files       ✗ Cursor doesn't split large tool outputs.
  - continuation refs (prev/next) ✗ Cursor has no resume-from-prior workflow.
"""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import BaseParser, DiscoveredSession
from vibelens.ingest.parsers.helpers import build_multimodal_message
from vibelens.models.enums import AgentType, ContentType, StepSource
from vibelens.models.trajectories import (
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)
from vibelens.models.trajectories.content import Base64Source, ContentPart
from vibelens.utils import get_logger

logger = get_logger(__name__)

# Local data root. The actual conversation data lives under ``chats/`` —
# ``projects/`` carries only project metadata and the partial JSONL export.
_LOCAL_ROOT = Path.home() / ".cursor"

# System-injected user messages we drop from the visible timeline. Cursor
# wraps its sub-agent system prompts in ``<system_reminder>`` tags and
# injects ``<user_query>`` markers around the human's actual prompt.
_USER_QUERY_OPEN = "<user_query>"
_USER_QUERY_CLOSE = "</user_query>"
_SYSTEM_REMINDER_PREFIX = "<system_reminder>"

# Notebook blobs are stored in the same ``blobs`` table because Cursor
# reuses the store for IDE notebook content too. We ignore these.
_NOTEBOOK_KEYS = frozenset({"cells", "nbformat", "nbformat_minor"})

# Cursor injects a ``<timestamp>...</timestamp>`` envelope in every user
# message containing a human-readable date string like
# ``Sunday, Apr 26, 2026, 9:53 PM (UTC-4)``. We extract this so sub-agent
# trajectories — whose JSONL has no other timestamp signal — can sort
# correctly in the UI.
_TIMESTAMP_TAG_RE = re.compile(r"<timestamp>(.*?)</timestamp>", re.DOTALL)
# ``Sunday, Apr 26, 2026, 9:53 PM (UTC-4)`` → drop the day prefix and
# (UTC...) suffix, then strptime. The day-name prefix is informational only.
_TIMESTAMP_BODY_RE = re.compile(
    r"(?:[A-Za-z]+, )?([A-Za-z]+ \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M)"
)


class CursorParser(BaseParser):
    """Parser for Cursor's SQLite-primary chat session format."""

    AGENT_TYPE = AgentType.CURSOR
    LOCAL_DATA_DIR: Path | None = _LOCAL_ROOT
    # Session ids are UUIDs (the agent-id directory under chats/<workspace>/),
    # already globally unique — no namespace needed.
    NAMESPACE_SESSION_IDS = False

    # ---- Discovery ----
    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Return one ``store.db`` per Cursor session.

        The path layout is ``chats/<workspace-hash>/<sid>/store.db``. The
        workspace hash isn't meaningful to us — we treat each store.db as
        the discovery target and use its parent directory name as the
        session id.
        """
        chats_root = data_dir / "chats"
        if not chats_root.is_dir():
            return []
        return sorted(
            workspace.joinpath(sid_dir.name, "store.db")
            for workspace in chats_root.iterdir()
            if workspace.is_dir()
            for sid_dir in workspace.iterdir()
            if sid_dir.is_dir() and (sid_dir / "store.db").is_file()
        )

    def discover_sessions(self, data_dir: Path) -> list[DiscoveredSession]:
        """Yield ``(path, session_id, mtime_ns)`` per session.

        Session id is the parent directory name of ``store.db``. Cursor
        names that directory after the agent UUID (matching the JSONL
        transcript filename in ``projects/<project>/agent-transcripts/<sid>/``).
        """
        out: list[DiscoveredSession] = []
        for db_path in self.discover_session_files(data_dir):
            try:
                mtime = db_path.stat().st_mtime_ns
            except OSError:
                continue
            out.append(
                DiscoveredSession(path=db_path, session_id=db_path.parent.name, mtime_ns=mtime)
            )
        return out

    def get_session_files(self, session_file: Path) -> list[Path]:
        """Return store.db plus all sub-agent transcripts for cache invalidation."""
        files = [session_file]
        sid = session_file.parent.name
        sub_dir = _subagent_dir_for_session(sid)
        if sub_dir is not None and sub_dir.is_dir():
            files.extend(sorted(sub_dir.glob("*.jsonl")))
        return files

    # ---- 4-stage parsing ----
    def _decode_file(self, file_path: Path, diagnostics: DiagnosticsCollector) -> list[dict] | None:
        """Read all role-bearing JSON blobs from ``store.db`` in rowid order."""
        if not file_path.is_file():
            return None
        try:
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            logger.warning("Cannot open Cursor SQLite %s: %s", file_path, exc)
            return None
        try:
            rows = conn.execute("SELECT data FROM blobs ORDER BY rowid").fetchall()
        except sqlite3.Error as exc:
            logger.warning("Failed to read Cursor blobs from %s: %s", file_path, exc)
            return None
        finally:
            conn.close()
        return _decode_message_blobs(rows, diagnostics)

    def _extract_metadata(
        self, raw: list[dict], file_path: Path, diagnostics: DiagnosticsCollector
    ) -> Trajectory | None:
        """Build the trajectory header. Project path comes from the sibling
        ``projects/<project>/repo.json`` if discoverable."""
        session_id = file_path.parent.name
        project_path = _resolve_project_path(session_id)
        return Trajectory(
            session_id=session_id,
            agent=self.build_agent(),
            project_path=project_path,
        )

    def _build_steps(
        self, raw: list[dict], traj: Trajectory, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> list[Step]:
        """Walk decoded message blobs in rowid order, build ATIF Steps."""
        # tool-result blocks live in their own ``role: tool`` blob; pre-scan
        # by toolCallId so we can attach them to the spawning assistant turn.
        results_by_call_id = _index_tool_results(raw)
        steps: list[Step] = []
        for msg in raw:
            role = msg.get("role")
            if role == "system":
                # Cursor's ``role: system`` blob is the always-on system
                # prompt — not a conversation turn. Drop.
                continue
            if role == "tool":
                # Already consumed via the pre-scan map; emitting standalone
                # tool steps would duplicate observations.
                continue
            step = _build_step(msg, results_by_call_id, diagnostics)
            if step is None:
                diagnostics.record_skip(f"empty {role} blob dropped")
                continue
            steps.append(step)
        return steps

    def _load_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Discover and parse sibling sub-agent JSONL transcripts.

        Cursor's main chat is in SQLite, but every sub-agent it spawns
        gets its own JSONL transcript at
        ``projects/<project>/agent-transcripts/<sid>/subagents/<child-sid>.jsonl``.
        We walk that directory if present and parse each child file as a
        smaller Anthropic-style transcript.

        Each child runs through ``_finalize`` so its ``final_metrics``
        (tool_call_count, total_steps, etc.) gets populated — the prompt
        nav panel reads ``sub.final_metrics.tool_call_count`` to render
        the per-sub-agent tool count, and unfinalised children would
        show ``0 tools``.

        Pairing limitation: Cursor's ``Subagent`` ``tool-call`` blocks have
        no ``id`` field and the child files don't carry parent-call
        references, so we cannot map a specific child to its spawning
        call. We attach all children to the main as a flat list and skip
        per-call ``subagent_trajectory_ref`` linkage. See module docstring.
        """
        sub_dir = _subagent_dir_for_session(main.session_id)
        if sub_dir is None or not sub_dir.is_dir():
            return []
        children: list[Trajectory] = []
        for child_path in sorted(sub_dir.glob("*.jsonl")):
            child = _parse_subagent_file(
                child_path, parent_session_id=main.session_id, agent_builder=self.build_agent
            )
            if child is None:
                continue
            children.append(self._finalize(child, DiagnosticsCollector()))
        return children


def _decode_message_blobs(rows: list[tuple], diagnostics: DiagnosticsCollector) -> list[dict]:
    """Decode each blob row, keeping only role-bearing JSON message blobs.

    Skips:
      - Empty blobs
      - Binary (protobuf tree-node) blobs that aren't UTF-8 decodable
      - Notebook blobs (``cells/nbformat``)
      - Anything that doesn't carry a ``role`` field
    """
    out: list[dict] = []
    for (data,) in rows:
        if not data:
            continue
        if isinstance(data, (bytes, bytearray)):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                # Binary protobuf tree node — used by Cursor for branch
                # tracking, not for VibeLens.
                continue
        else:
            text = data
        try:
            d = json.loads(text)
        except json.JSONDecodeError:
            diagnostics.record_skip("blob is non-JSON text")
            continue
        if not isinstance(d, dict):
            continue
        if _NOTEBOOK_KEYS.intersection(d.keys()):
            continue
        if "role" not in d:
            continue
        out.append(d)
    return out


def _index_tool_results(messages: list[dict]) -> dict[str, dict]:
    """Build ``toolCallId -> tool-result block`` map from ``role: tool`` blobs.

    Cursor stores tool results in dedicated ``role: tool`` messages that
    contain one or more ``type: tool-result`` blocks. We index by
    ``toolCallId`` so the assistant turn's spawning ``tool-call`` block
    can recover its observation in O(1).
    """
    out: dict[str, dict] = {}
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        for block in msg.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "tool-result":
                cid = block.get("toolCallId")
                if cid:
                    out[cid] = block
    return out


def _build_step(
    msg: dict, results_by_call_id: dict[str, dict], diagnostics: DiagnosticsCollector
) -> Step | None:
    """Build one Step from a message blob.

    Pure-text and pure-tool turns become single Steps. Multimodal turns
    (text + image) emit a ``list[ContentPart]`` ``message``. Reasoning
    blocks contribute to ``Step.reasoning_content`` only when they carry
    plaintext — Cursor's reasoning is encrypted for OpenAI providers, so
    in practice this stays empty (see module docstring).
    """
    role = msg.get("role", "")
    source = StepSource.USER if role == "user" else StepSource.AGENT
    content = msg.get("content", []) or []
    is_summary = bool(((msg.get("providerOptions") or {}).get("cursor") or {}).get("isSummary"))

    text_parts: list[str] = []
    image_parts: list[ContentPart] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    obs_results: list[ObservationResult] = []
    timestamp: datetime | None = None

    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            raw = block.get("text") or ""
            if timestamp is None:
                # Cursor wraps user messages with a ``<timestamp>...</timestamp>``
                # envelope; the frontend's sub-agent placement uses these
                # timestamps to interleave sibling sub-agent files at the
                # right point in the timeline.
                timestamp = _parse_cursor_timestamp(raw)
            text = _extract_user_query(raw)
            if text:
                text_parts.append(text)
        elif block_type == "image":
            image_part = _image_block_to_content_part(block)
            if image_part is not None:
                image_parts.append(image_part)
        elif block_type == "reasoning":
            # Encrypted for OpenAI providers — text is almost always empty.
            # We still propagate the rare plaintext reasoning so Anthropic
            # provider sessions (if any) get their thinking surfaced.
            text = block.get("text") or ""
            if text:
                reasoning_parts.append(text)
        elif block_type == "tool-call":
            tc, obs = _build_tool_pair(block, results_by_call_id, diagnostics)
            if tc is not None:
                tool_calls.append(tc)
            if obs is not None:
                obs_results.append(obs)

    raw_text = "".join(text_parts).strip()
    if source == StepSource.USER and raw_text.lstrip().startswith(_SYSTEM_REMINDER_PREFIX):
        # Cursor's sub-agent system prompt injection — not user-typed text.
        # Reclassify as SYSTEM so the UI doesn't show an empty user bubble.
        source = StepSource.SYSTEM

    message = build_multimodal_message(raw_text, image_parts)
    if not (raw_text or image_parts or reasoning_parts or tool_calls or obs_results or is_summary):
        return None

    return Step(
        step_id=msg.get("id") or str(uuid4()),
        source=source,
        message=message,
        timestamp=timestamp,
        reasoning_content="\n".join(reasoning_parts) or None,
        tool_calls=tool_calls,
        observation=Observation(results=obs_results) if obs_results else None,
        is_compaction=True if is_summary else None,
    )


def _extract_user_query(text: str) -> str:
    """Strip Cursor's ``<timestamp>`` prefix and ``<user_query>`` wrapping.

    User messages arrive wrapped like
    ``<timestamp>...</timestamp>\\n<user_query>\\n<actual prompt>\\n</user_query>``.
    We extract just the inner prompt for display; the timestamp envelope
    is bookkeeping the agent injected before sending to the model.
    """
    if _USER_QUERY_OPEN in text and _USER_QUERY_CLOSE in text:
        start = text.index(_USER_QUERY_OPEN) + len(_USER_QUERY_OPEN)
        end = text.index(_USER_QUERY_CLOSE)
        return text[start:end].strip()
    return text


def _image_block_to_content_part(block: dict) -> ContentPart | None:
    """Decode a Cursor ``image`` block into an inline image ContentPart.

    Cursor serialises pasted images as ``{type: image, image: {__type:
    "Uint8Array", hex: "<raw hex bytes>"}}``. We re-encode the bytes to
    base64 for ATIF compatibility and assume ``image/png`` since Cursor
    always converts pasted clipboard data to PNG in observed sessions.
    Future work: detect mime via the byte signature when JPEG / WebP
    appears.
    """
    img = block.get("image")
    if not isinstance(img, dict) or img.get("__type") != "Uint8Array":
        return None
    hex_bytes = img.get("hex")
    if not isinstance(hex_bytes, str) or not hex_bytes:
        return None
    try:
        raw = bytes.fromhex(hex_bytes)
    except ValueError:
        return None
    return ContentPart(
        type=ContentType.IMAGE,
        source=Base64Source(media_type="image/png", base64=base64.b64encode(raw).decode("ascii")),
    )


def _build_tool_pair(
    block: dict,
    results_by_call_id: dict[str, dict],
    diagnostics: DiagnosticsCollector,
) -> tuple[ToolCall | None, ObservationResult | None]:
    """Convert a ``tool-call`` block into ``(ToolCall, ObservationResult)``.

    Pairs against the pre-scanned ``results_by_call_id`` map. Cursor uses
    Anthropic-style ``toolCallId`` (e.g. ``call_<hex>\\nfc_<hex>``) on
    both sides, so the lookup is exact. Returns the observation as
    ``None`` when the spawning call hasn't received a result yet
    (in-flight, last call of an interrupted session).
    """
    call_id = block.get("toolCallId") or ""
    function_name = block.get("toolName") or ""
    diagnostics.record_tool_call()
    tc = ToolCall(
        tool_call_id=call_id,
        function_name=function_name,
        arguments=block.get("args"),
    )
    result_block = results_by_call_id.get(call_id) if call_id else None
    if result_block is None:
        if call_id:
            diagnostics.record_orphaned_call(call_id)
        return tc, None
    diagnostics.record_tool_result()
    obs = ObservationResult(
        source_call_id=call_id,
        content=_format_tool_result_content(result_block.get("result")),
        is_error=False,  # Cursor doesn't expose a native error flag in observed data.
    )
    return tc, obs


def _format_tool_result_content(value: Any) -> str:
    """Coerce a ``tool-result.result`` field into a string body."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # ``experimental_content`` shape — array of {type, text}
        chunks = []
        for c in value:
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                chunks.append(c["text"])
        return "\n".join(chunks)
    return json.dumps(value)


def _resolve_project_path(session_id: str) -> str | None:
    """Find the project_path for a session by scanning ``projects/<project>/``.

    Cursor stores the project under ``projects/<encoded-path>/`` where the
    encoded form replaces ``/`` with ``-``. We locate the directory that
    has ``agent-transcripts/<sid>/`` matching the session, then read its
    ``repo.json`` for the canonical path. Returns ``None`` if the project
    metadata is missing — sessions are still usable without a known path.
    """
    projects_root = _LOCAL_ROOT / "projects"
    if not projects_root.is_dir():
        return None
    for project in projects_root.iterdir():
        if not project.is_dir():
            continue
        if not (project / "agent-transcripts" / session_id).is_dir():
            continue
        repo_json = project / "repo.json"
        if repo_json.is_file():
            try:
                meta = json.loads(repo_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for key in ("workspace", "rootPath", "path"):
                value = meta.get(key)
                if isinstance(value, str) and value:
                    return value
        # Fallback: decode the directory name (``Users-foo-bar`` → ``/Users/foo/bar``).
        encoded = project.name
        if encoded.startswith("Users-"):
            return "/" + encoded.replace("-", "/")
        return None
    return None


def _subagent_dir_for_session(session_id: str) -> Path | None:
    """Locate the ``subagents/`` directory for a session, if any.

    Sub-agent transcripts live under
    ``projects/<project>/agent-transcripts/<sid>/subagents/`` even though
    the main session itself lives in ``chats/<workspace>/<sid>/store.db``.
    Returns the first matching directory or ``None`` if no project owns
    this session.
    """
    projects_root = _LOCAL_ROOT / "projects"
    if not projects_root.is_dir():
        return None
    for project in projects_root.iterdir():
        sub_dir = project / "agent-transcripts" / session_id / "subagents"
        if sub_dir.is_dir():
            return sub_dir
    return None


def _parse_subagent_file(
    child_path: Path,
    parent_session_id: str,
    agent_builder,
) -> Trajectory | None:
    """Parse a Cursor sub-agent JSONL transcript into a child Trajectory.

    Sub-agents share the parent's wire format (Anthropic-style envelope
    ``{role, message: {content[...]}}``) but live in plain JSONL because
    they don't have their own SQLite store. Sub-agent transcripts only
    capture text + ``tool_use`` blocks (the limitation that pushed the
    main parser to SQLite); we accept the gap and leave tool results
    out for sub-agents. Future work: surface tool results when Cursor
    starts persisting them in the JSONL.

    Timestamps: Cursor wraps every user message with a ``<timestamp>...
    </timestamp>`` block carrying a human-readable date string. We parse
    the first one to set ``Trajectory.created_at`` so sub-agents sort
    correctly in the UI (otherwise they all collapse to ``datetime.min``
    and render in alphabetical-UUID order at the bottom of the timeline).
    Falls back to the file's mtime when the timestamp tag isn't parseable.
    """
    try:
        lines = child_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    first_user_timestamp: datetime | None = None
    steps: list[Step] = []
    for raw_line in lines:
        if not raw_line.strip():
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        role = entry.get("role")
        if role not in ("user", "assistant"):
            continue
        content = (entry.get("message") or {}).get("content") or []
        text_parts: list[str] = []
        raw_text_for_timestamp = ""
        tool_calls: list[ToolCall] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                raw = block.get("text") or ""
                if not raw_text_for_timestamp:
                    raw_text_for_timestamp = raw
                text = _extract_user_query(raw)
                if text:
                    text_parts.append(text)
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        tool_call_id=block.get("id") or "",
                        function_name=block.get("name") or "",
                        arguments=block.get("input"),
                    )
                )
        if first_user_timestamp is None and role == "user" and raw_text_for_timestamp:
            first_user_timestamp = _parse_cursor_timestamp(raw_text_for_timestamp)
        message_text = "\n".join(text_parts).strip()
        if not message_text and not tool_calls:
            continue
        steps.append(
            Step(
                step_id=str(uuid4()),
                source=StepSource.USER if role == "user" else StepSource.AGENT,
                message=message_text,
                timestamp=first_user_timestamp if not steps else None,
                tool_calls=tool_calls,
            )
        )
    if not steps:
        return None
    if first_user_timestamp is None:
        try:
            first_user_timestamp = datetime.fromtimestamp(
                child_path.stat().st_mtime, tz=_LOCAL_TZ_PLACEHOLDER
            )
        except OSError:
            first_user_timestamp = None
    return Trajectory(
        session_id=child_path.stem,
        agent=agent_builder(),
        created_at=first_user_timestamp,
        parent_trajectory_ref=TrajectoryRef(session_id=parent_session_id),
        steps=steps,
        extra={"agent_role": "subagent"},
    )


def _parse_cursor_timestamp(text: str) -> datetime | None:
    """Extract and parse Cursor's ``<timestamp>...</timestamp>`` envelope.

    The format is ``Sunday, Apr 26, 2026, 9:53 PM (UTC-4)``. We strip the
    weekday prefix and the parenthesised offset, then strptime. The
    offset matters for absolute ordering across timezones; Cursor only
    emits one timezone per machine in observed sessions, so we accept
    a naive datetime (callers compare relatively, not absolutely).
    """
    tag_match = _TIMESTAMP_TAG_RE.search(text)
    if not tag_match:
        return None
    body_match = _TIMESTAMP_BODY_RE.search(tag_match.group(1))
    if not body_match:
        return None
    try:
        return datetime.strptime(body_match.group(1), "%b %d, %Y, %I:%M %p")
    except ValueError:
        return None


# Cursor sub-agent files lack a structural timestamp; we fall back to the
# file's mtime when the inline ``<timestamp>`` tag is malformed. The mtime
# is naive (system local), so we attach the system's local tzinfo to keep
# the resulting datetime comparable with Cursor's tz-naive parsed value.
from datetime import timezone as _datetime_timezone  # noqa: E402

_LOCAL_TZ_PLACEHOLDER = _datetime_timezone.utc
