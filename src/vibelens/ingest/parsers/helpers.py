"""Cross-parser helpers shared by every concrete parser implementation.

Pulled out of ``base.py`` so the BaseParser class stays focused on the
abstract API and lifecycle hooks, and parser modules can import only the
small surface they need.

Public surface, grouped by lifecycle phase:

* Constants — ``MAX_FIRST_MESSAGE_LENGTH``, ``ROLE_TO_SOURCE``.
* JSONL iteration — ``iter_jsonl_safe``.
* Tool-arg decoding — ``parse_tool_arguments``.
* First-message detection — ``is_meaningful_prompt``,
  ``step_text_only``, ``find_first_user_text``,
  ``truncate_first_message``.
* Multimodal assembly — ``build_multimodal_message``,
  ``data_url_to_image_content_part``.
* Trajectory rollup — ``compute_final_metrics``.
* Synthetic boundary steps — ``make_compaction_step``.
* Skills — none here. Each parser owns its own activation-tool constant.
* Diagnostics — ``build_diagnostics_extra``.

Helpers prefixed with ``_`` are intentionally private to this module.
"""

import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.models.enums import ContentType, StepSource
from vibelens.models.trajectories import DailyBucket, FinalMetrics, Step
from vibelens.models.trajectories.content import Base64Source, ContentPart
from vibelens.utils.log import get_logger
from vibelens.utils.timestamps import local_date_key

logger = get_logger(__name__)

# Keeps session-list previews short enough for UI display while preserving
# enough context for the user to recognise the conversation at a glance.
MAX_FIRST_MESSAGE_LENGTH = 200

# ATIF source mapping shared across parsers that use standard role names.
ROLE_TO_SOURCE: dict[str, StepSource] = {"user": StepSource.USER, "assistant": StepSource.AGENT}

# Prefix marking inline data URLs in agent payloads (OpenCode/Codex/etc.).
_DATA_URL_PREFIX = "data:"

# System-XML-tag prefixes are agent-specific (observed via actual session scans):
#   claude  -> <local-command-caveat, <command-name, <command-message,
#              <local-command-stdout, <system-reminder, <user-prompt-submit-hook,
#              <task-notification, <command-args
#   codex   -> <environment_context, <turn_aborted, <skill, <subagent_notification
# Each parser module owns the list that fits its format. The union below is
# used only for agent-agnostic callers (e.g. demo mode loading ATIF files
# where the originating agent is unknown).
_ALL_KNOWN_SYSTEM_TAG_PREFIXES = (
    # claude
    "<system-reminder",
    "<command-name",
    "<command-message",
    "<command-args",
    "<user-prompt-submit-hook",
    "<local-command-caveat",
    "<local-command-stdout",
    "<task-notification",
    # codex
    "<environment_context",
    "<turn_aborted",
    "<subagent_notification",
    # generic fallbacks seen in wrapped imports
    "<environment-details",
    "<context",
    "<tool-",
    "<instructions",
)

# Skill-output marker is a claude-specific convention (the Skill tool writes
# "Base directory for this skill: ..." as the first line of its result).
# Unique enough that the agent-agnostic check costs nothing for other agents.
_SKILL_OUTPUT_PREFIX = "Base directory for this skill:"

def is_meaningful_prompt(text: str, extra_system_prefixes: tuple[str, ...] = ()) -> bool:
    """Return True if text looks like a real user prompt, not system chatter.

    Args:
        text: Candidate message body.
        extra_system_prefixes: Agent-specific system XML-tag prefixes to
            reject in addition to the universal set. Pass an empty tuple
            when the caller already provides a full list.
    """
    stripped = text.strip()
    if not stripped:
        return False
    prefixes = extra_system_prefixes or _ALL_KNOWN_SYSTEM_TAG_PREFIXES
    if stripped.startswith(prefixes):
        return False
    if stripped.startswith(_SKILL_OUTPUT_PREFIX):
        return False
    is_single_line = "\n" not in stripped
    # Single slash commands like "/permissions", "/compact"
    if stripped.startswith("/") and is_single_line and len(stripped.split()) <= 3:
        return False
    # System-generated interrupt/status messages wrapped in square brackets,
    # e.g. "[Request interrupted by user for tool use]".
    return not (stripped.startswith("[") and stripped.endswith("]") and is_single_line)


def truncate_first_message(text: str) -> str:
    """Truncate text to ``MAX_FIRST_MESSAGE_LENGTH`` with ellipsis if needed."""
    if len(text) <= MAX_FIRST_MESSAGE_LENGTH:
        return text
    return text[:MAX_FIRST_MESSAGE_LENGTH] + "..."


def find_first_user_text(steps: list[Step]) -> str | None:
    """Extract truncated text of the first meaningful user step.

    Skips copied context (from ``claude --resume``), slash commands
    (e.g. ``/permissions``, ``/compact``), and parser-flagged auto/skill
    prompts. For multimodal messages (``list[ContentPart]``, e.g. pasted
    screenshots) only text parts are joined — the ``[image]``-style
    placeholders that :func:`vibelens.utils.content.content_to_text`
    emits would make the joined string end with ``]`` and trip the
    system-message filter in :func:`is_meaningful_prompt`.
    """
    for step in steps:
        if step.source != StepSource.USER:
            continue
        if step.is_copied_context:
            continue
        extra = step.extra or {}
        if extra.get("is_skill_output") or extra.get("is_auto_prompt"):
            continue
        text = step_text_only(step.message)
        if text and is_meaningful_prompt(text):
            return truncate_first_message(text)
    return None


def step_text_only(message) -> str:
    """Join only the text parts of a step message.

    Differs from :func:`vibelens.utils.content.content_to_text` by
    skipping non-text parts entirely instead of emitting ``[<type>]``
    placeholders. Used for first-message detection where placeholders
    would break the bracket-wrapped system-message filter.
    """
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return "\n\n".join(p.text for p in message if getattr(p, "text", None))
    return ""


def parse_tool_arguments(raw: Any) -> dict | str | None:
    """Decode a tool-call ``arguments`` field into a dict (or pass through).

    Codex/Hermes follow the OpenAI Responses API convention and
    serialise ``arguments`` as a JSON string. If decoding fails we keep
    the raw string so no data is lost. Dicts pass through unchanged.
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
        return parsed if isinstance(parsed, dict) else raw
    return None


def iter_jsonl_safe(
    source: Path | str, diagnostics: DiagnosticsCollector | None = None
) -> Iterator[dict]:
    """Yield parsed JSON dicts from a JSONL file path or raw content string.

    Blank lines are skipped silently; decode errors are recorded to
    ``diagnostics`` (if provided) and skipped. ``orjson.JSONDecodeError``
    is a subclass of ``json.JSONDecodeError``, so the except clause
    catches both implementations.

    Args:
        source: Filesystem path to a ``.jsonl`` file, or a raw content
            string already loaded into memory.
        diagnostics: Optional collector for parse-quality metrics
            (total/parsed line counts, skip reasons).
    """
    if isinstance(source, Path):
        try:
            with source.open(encoding="utf-8") as f:
                yield from _iter_parsed_jsonl(f, diagnostics)
        except OSError:
            logger.debug("Cannot read file: %s", source)
    else:
        yield from _iter_parsed_jsonl(source.splitlines(), diagnostics)


def _iter_parsed_jsonl(
    lines: Iterable[str], diagnostics: DiagnosticsCollector | None
) -> Iterator[dict]:
    """Yield parsed JSON dicts from a stream of JSONL lines.

    Used by :func:`iter_jsonl_safe` from both the file-streaming and
    string-splitting paths so they share the same blank-line and
    decode-error handling.
    """
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if diagnostics is not None:
            diagnostics.total_lines += 1
        try:
            parsed = orjson.loads(stripped)
        except json.JSONDecodeError:
            if diagnostics is not None:
                diagnostics.record_skip("invalid JSON")
            continue
        if diagnostics is not None:
            diagnostics.parsed_lines += 1
        yield parsed


def build_diagnostics_extra(collector: DiagnosticsCollector) -> dict | None:
    """Return a trajectory ``extra`` dict from diagnostics, or None on no issues."""
    has_issues = (
        collector.skipped_lines > 0
        or collector.orphaned_tool_calls > 0
        or collector.orphaned_tool_results > 0
    )
    if not has_issues:
        return None
    return {"diagnostics": collector.to_diagnostics().model_dump()}


def compute_final_metrics(steps: list[Step], session_model: str | None) -> FinalMetrics:
    """Roll a step list up to a ``FinalMetrics`` and populate per-step cost.

    When a step has token metrics but no pre-computed ``cost_usd`` (the
    common case for Claude / Hermes / Codex — only OpenClaw records it
    in source), look up pricing and write the derived cost back to
    ``step.metrics.cost_usd`` so downstream code can read a canonical
    per-step cost without re-querying the pricing table.

    Args:
        steps: All steps in the trajectory.
        session_model: Agent-level model name used as a fallback when
            ``step.model_name`` is missing (Claude populates it per-step,
            Gemini does not).
    """
    # Local import avoids a module-level cycle at interpreter startup.
    from vibelens.llm.pricing import compute_step_cost

    total_prompt = 0
    total_completion = 0
    total_cost: float | None = None
    total_cache_write_tokens = 0
    total_cache_read_tokens = 0
    tool_call_count = 0
    breakdown: dict[str, DailyBucket] = {}

    # Fallback day for steps that lack their own timestamp. Mirrors the
    # behaviour of ``aggregate_session`` in services/dashboard/stats.py
    # so ``sum(daily_breakdown.messages) == len(steps)`` holds even when
    # some steps (e.g. injected SYSTEM markers) carry no timestamp.
    fallback_ts = next((s.timestamp for s in steps if s.timestamp), None)
    fallback_day = local_date_key(fallback_ts) if fallback_ts else None

    for step in steps:
        tool_call_count += len(step.tool_calls)

        tokens_this_step = 0
        cost_this_step = 0.0

        if step.metrics:
            total_prompt += step.metrics.prompt_tokens
            total_completion += step.metrics.completion_tokens
            total_cache_read_tokens += step.metrics.cache_read_tokens
            total_cache_write_tokens += step.metrics.cache_write_tokens
            tokens_this_step = step.metrics.prompt_tokens + step.metrics.completion_tokens

            if step.metrics.cost_usd is None:
                step.metrics.cost_usd = compute_step_cost(step, session_model)

            if step.metrics.cost_usd is not None:
                cost_this_step = step.metrics.cost_usd
                total_cost = (total_cost or 0.0) + cost_this_step

        # ``local_date_key`` uses ``.astimezone()`` (no args) so the
        # offset is resolved per-timestamp, honouring DST. A cached
        # fixed-offset tz would mis-attribute sessions across the
        # midnight boundary on DST transition days.
        day = local_date_key(step.timestamp) if step.timestamp else fallback_day
        if day:
            bucket = breakdown.setdefault(day, DailyBucket())
            bucket.messages += 1
            bucket.tokens += tokens_this_step
            bucket.cost_usd += cost_this_step

    timestamps = [s.timestamp for s in steps if s.timestamp]
    duration = 0
    if len(timestamps) >= 2:
        duration = int((max(timestamps) - min(timestamps)).total_seconds())

    return FinalMetrics(
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_cost_usd=total_cost,
        total_steps=len(steps),
        tool_call_count=tool_call_count,
        duration=duration,
        total_cache_write_tokens=total_cache_write_tokens,
        total_cache_read_tokens=total_cache_read_tokens,
        daily_breakdown=breakdown or None,
    )


def build_multimodal_message(text: str, image_parts: list[ContentPart]) -> str | list[ContentPart]:
    """Assemble a ``Step.message`` value from text and (optional) image parts.

    Returns the plain ``text`` string when no images are present so the cache
    payload stays compact for text-only turns. When at least one image is
    present, returns a ``list[ContentPart]`` with the text first (if non-empty)
    followed by each image — the canonical ATIF multimodal shape.

    Used by every parser that surfaces images: claude, codex, codebuddy,
    copilot, gemini, opencode/kilo, openclaw. Centralising the assembly here
    means the renderer never sees a parser-specific quirk like a stray empty
    text part or an image-then-text ordering inversion.
    """
    if not image_parts:
        return text
    parts: list[ContentPart] = []
    if text:
        parts.append(ContentPart(type=ContentType.TEXT, text=text))
    parts.extend(image_parts)
    return parts


def data_url_to_image_content_part(
    data_url: str, fallback_mime: str = "image/png"
) -> ContentPart | None:
    """Decode a ``data:<mime>;base64,<...>`` URL into an inline image ContentPart.

    Returns ``None`` for non-data URLs, missing ``;base64`` markers, and
    non-image mime types — callers can record those as diagnostics. The
    ``fallback_mime`` is used only when the URL header omits a mime type;
    it should match the agent's documented default (``image/png`` is the
    universal fallback in observed data).

    Used by parsers whose images arrive embedded in URL form (OpenCode /
    Kilo ``part.url``, Codex ``input_image.image_url``).
    """
    if not data_url.startswith(_DATA_URL_PREFIX) or "," not in data_url:
        return None
    header, _, payload = data_url.partition(",")
    if ";base64" not in header:
        return None
    mime = header[len(_DATA_URL_PREFIX) :].split(";", 1)[0] or fallback_mime
    if not mime.startswith("image/"):
        return None
    return ContentPart(
        type=ContentType.IMAGE,
        source=Base64Source(media_type=mime, base64=payload),
    )


def make_compaction_step(
    step_id: str,
    timestamp: datetime | None,
    message: str = "[Context compacted]",
    extra: dict | None = None,
) -> Step:
    """Build a synthetic SYSTEM Step marking a compaction / truncation boundary.

    Sets the typed ``Step.is_compaction = True`` flag so the dashboard and
    UI can detect the marker without looking at the message text. Callers
    may pass additional ``extra`` keys (e.g. token counts, summary length)
    — those stay in the polymorphic ``extra`` dict; they are not promoted
    because they are vendor-specific.

    Used by parsers that surface compaction as a discrete event: codex
    (``event_msg.context_compacted``), copilot (``session.compaction_complete``),
    gemini (``/compress`` slash command in ``logs.json``), kiro
    (``kind: Compaction`` envelope), cursor (``providerOptions.cursor.isSummary``
    flag in SQLite blobs). Parsers whose compaction is in-stream (codebuddy
    ``providerData.agent="compact"``, opencode ``part.type=compaction``) tag
    existing steps directly via :func:`tag_step_compaction` instead.
    """
    return Step(
        step_id=step_id,
        source=StepSource.SYSTEM,
        message=message,
        timestamp=timestamp,
        is_compaction=True,
        extra=extra or None,
    )


def attach_subagent_ref(
    parent_steps: list[Step], source_call_id: str, child_session_id: str
) -> bool:
    """Wire a child trajectory's session_id onto the parent's spawning observation.

    Walks ``parent_steps`` looking for an ``ObservationResult`` whose
    ``source_call_id`` matches the spawning tool call id; appends a
    ``TrajectoryRef(session_id=child_session_id)`` to that observation's
    ``subagent_trajectory_ref`` list (creating it if absent). De-duplicates
    by ``session_id`` so re-running the link step is a no-op.

    Used by parsers that build the parent → child link after both sides have
    been parsed: copilot (events grouped by ``agentId``), gemini (inline
    sub-agent synthesised from a tool-result text). Returns ``True`` when a
    match is found, so callers can record a diagnostic when the parent
    can't be located.
    """
    # Local import keeps helpers.py free of agent-domain types at import time.
    from vibelens.models.trajectories.trajectory_ref import TrajectoryRef

    new_ref = TrajectoryRef(session_id=child_session_id)
    for step in parent_steps:
        if step.observation is None:
            continue
        for obs_result in step.observation.results:
            if obs_result.source_call_id != source_call_id:
                continue
            existing = obs_result.subagent_trajectory_ref or []
            if all(r.session_id != child_session_id for r in existing):
                obs_result.subagent_trajectory_ref = [*existing, new_ref]
            return True
    return False


def tag_step_compaction(step: Step, **extra_fields: Any) -> Step:
    """Return a copy of ``step`` with the compaction flag set.

    Sets the typed ``Step.is_compaction = True`` field. Additional keyword
    arguments are merged into ``extra`` for format-specific metadata
    (``agent_role="compact"`` for CodeBuddy, etc.). The original step is
    left untouched (Pydantic ``model_copy``).
    """
    update: dict[str, Any] = {"is_compaction": True}
    if extra_fields:
        update["extra"] = {**(step.extra or {}), **extra_fields}
    return step.model_copy(update=update)
