"""OpenClaw JSONL format parser.

Parses ~/.openclaw/agents/main/sessions/ for session data.  OpenClaw stores
each conversation event as a JSONL line with a ``type`` field.  Message events
(``type: "message"``) carry the conversation content in a nested ``message``
object whose ``role`` distinguishes user prompts, assistant responses, and
tool results.

Key differences from Claude Code:
- Events are wrapped: ``{"type": "message", "message": {"role": "..."}}``
  instead of flat ``{"type": "user"}``.
- Tool calls use ``{"type": "toolCall", "id": ..., "name": ..., "arguments": ...}``
  inside assistant content blocks (not ``tool_use``).
- Tool results are separate ``toolResult``-role messages linked via
  ``toolCallId`` (not embedded in the next user message).
- Usage fields use short names: ``input``, ``output``, ``cacheRead``,
  ``cacheWrite``, with costs nested under ``usage.cost.total``.
- Session metadata comes from header events: ``session``, ``model_change``,
  ``thinking_level_change``, ``custom``.
"""

import json
from pathlib import Path
from uuid import uuid4

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import ROLE_TO_SOURCE, BaseParser, mark_error_content
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import (
    Agent,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.models.trajectories.trajectory import DEFAULT_ATIF_VERSION
from vibelens.utils import coerce_to_string, get_logger, normalize_timestamp

logger = get_logger(__name__)

# Sessions index filename to exclude from session file discovery
SESSIONS_INDEX_FILENAME = "sessions.json"

# Non-session files that may appear alongside real session JSONL
_EXCLUDED_SUFFIXES = ("-clean.jsonl",)


class OpenClawParser(BaseParser):
    """Parser for OpenClaw's native JSONL session format.

    Reads session files from ~/.openclaw/agents/*/sessions/ and the
    sessions.json index for fast skeleton listing.
    """

    AGENT_TYPE = AgentType.OPENCLAW
    LOCAL_DATA_DIR: Path | None = Path.home() / ".openclaw"

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Find OpenClaw session JSONL files across all agent instances.

        Scans ``data_dir/agents/*/sessions/*.jsonl``, excluding the
        sessions.json index and test/clean files.

        Args:
            data_dir: Root OpenClaw data directory (~/.openclaw).

        Returns:
            Sorted list of session file paths.
        """
        agents_dir = data_dir / "agents"
        if not agents_dir.is_dir():
            return []
        files: list[Path] = []
        for jsonl_file in sorted(agents_dir.rglob("*.jsonl")):
            if jsonl_file.name == SESSIONS_INDEX_FILENAME:
                continue
            if any(jsonl_file.name.endswith(suffix) for suffix in _EXCLUDED_SUFFIXES):
                continue
            # Only include files under a sessions/ directory
            if "sessions" not in jsonl_file.parts:
                continue
            files.append(jsonl_file)
        return files

    def parse_session_index(self, data_dir: Path) -> list[Trajectory] | None:
        """Build skeleton trajectories from sessions.json for fast listing.

        Args:
            data_dir: Root OpenClaw data directory (~/.openclaw).

        Returns:
            List of skeleton Trajectory objects, or None if no index found.
        """
        index_file = data_dir / "agents" / "main" / "sessions" / SESSIONS_INDEX_FILENAME
        if not index_file.exists():
            return None

        try:
            raw = json.loads(index_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.debug("Cannot read sessions.json at %s", index_file)
            return None

        if not isinstance(raw, dict):
            return None

        trajectories: list[Trajectory] = []
        for _key, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            session_id = entry.get("sessionId")
            if not session_id:
                continue

            timestamp = normalize_timestamp(entry.get("updatedAt"))
            skeleton_step = Step(
                step_id="index-0",
                source=StepSource.USER,
                message="",
                timestamp=timestamp,
            )

            trajectories.append(
                Trajectory(
                    schema_version=DEFAULT_ATIF_VERSION,
                    session_id=session_id,
                    agent=Agent(name=self.AGENT_TYPE.value),
                    steps=[skeleton_step],
                    final_metrics=FinalMetrics(),
                    extra={"is_skeleton": True},
                )
            )

        return trajectories if trajectories else None

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse OpenClaw JSONL session content into Trajectory objects.

        Args:
            content: Raw JSONL content string.
            source_path: Original file path for session ID fallback.

        Returns:
            List containing one Trajectory (main session).
        """
        collector = DiagnosticsCollector()
        entries = _parse_jsonl_content(content, collector)
        if not entries:
            return []

        meta = _extract_session_meta(entries)
        session_id = meta["session_id"]
        if not session_id:
            session_id = Path(source_path).stem if source_path else str(uuid4())

        steps = _build_steps(entries, collector)
        if not steps:
            return []

        agent = self.build_agent(model=meta["model"])
        extra = self.build_diagnostics_extra(collector)

        return [
            self.assemble_trajectory(
                session_id=session_id,
                agent=agent,
                steps=steps,
                project_path=meta["cwd"],
                extra=extra,
            )
        ]


def _parse_jsonl_content(content: str, diagnostics: DiagnosticsCollector) -> list[dict]:
    """Parse JSONL string into a list of dicts, tracking parse quality.

    Args:
        content: Raw JSONL content.
        diagnostics: Collector for tracking skipped lines.

    Returns:
        List of parsed JSON dicts.
    """
    entries: list[dict] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        diagnostics.total_lines += 1
        try:
            parsed = json.loads(stripped)
            diagnostics.parsed_lines += 1
            entries.append(parsed)
        except json.JSONDecodeError:
            diagnostics.record_skip("invalid JSON")
    return entries


def _extract_session_meta(entries: list[dict]) -> dict:
    """Extract session metadata from header and early message events.

    Scans all non-message events for ``session``, ``model_change``, and
    ``custom`` (model-snapshot) headers.  These can appear interleaved with
    early system messages (e.g. ``delivery-mirror``), so we do NOT break at the
    first message.  As a final fallback, extracts the model from the first real
    assistant message's ``model`` field.

    Args:
        entries: Parsed JSONL entries.

    Returns:
        Dict with keys: session_id, cwd, model, provider.
    """
    meta: dict = {"session_id": None, "cwd": None, "model": None, "provider": None}
    first_assistant_model: str | None = None

    for entry in entries:
        event_type = entry.get("type")
        if event_type == "session":
            meta["session_id"] = entry.get("id")
            meta["cwd"] = entry.get("cwd")
        elif event_type == "model_change":
            provider = entry.get("provider", "")
            model_id = entry.get("modelId", "")
            meta["provider"] = provider
            meta["model"] = f"{provider}/{model_id}" if provider and model_id else model_id
        elif event_type == "custom" and entry.get("customType") == "model-snapshot":
            data = entry.get("data", {})
            if not meta["model"] and data.get("modelId"):
                provider = data.get("provider", "")
                model_id = data["modelId"]
                meta["model"] = f"{provider}/{model_id}" if provider else model_id
        elif event_type == "message" and not first_assistant_model:
            # Capture model from first real assistant message as fallback
            msg = entry.get("message", {})
            model_name = msg.get("model", "")
            if msg.get("role") == "assistant" and model_name and model_name != "delivery-mirror":
                first_assistant_model = model_name

    # Fallback: use the first real assistant model if no header provided one
    if not meta["model"] and first_assistant_model:
        meta["model"] = first_assistant_model

    return meta


def _build_steps(entries: list[dict], diagnostics: DiagnosticsCollector) -> list[Step]:
    """Convert message entries into ATIF Step objects.

    Pre-scans toolResult entries into a lookup dict, then builds steps
    from user and assistant messages with tool results linked by ID.

    Args:
        entries: All parsed JSONL entries.
        diagnostics: Collector for tracking orphaned tool calls/results.

    Returns:
        Ordered list of Step objects.
    """
    message_entries = [e for e in entries if e.get("type") == "message"]
    tool_result_map = _collect_tool_results(message_entries)
    tool_call_ids: set[str] = set()

    steps: list[Step] = []
    for entry in message_entries:
        msg = entry.get("message", {})
        role = msg.get("role", "")

        # toolResult entries are consumed via the pre-scan map, not as steps
        if role == "toolResult":
            continue

        source = ROLE_TO_SOURCE.get(role)
        if source is None:
            continue

        timestamp = normalize_timestamp(entry.get("timestamp") or msg.get("timestamp"))
        step_id = entry.get("id", str(uuid4()))
        raw_content = msg.get("content", "")
        model_name = msg.get("model") or None

        message, reasoning_content, tool_calls = _decompose_content(raw_content)
        metrics = _build_metrics(msg.get("usage")) if source == StepSource.AGENT else None

        # Build observation from tool results linked to this step's tool calls
        observation = _build_observation(tool_calls, tool_result_map)

        for tc in tool_calls:
            if tc.tool_call_id:
                tool_call_ids.add(tc.tool_call_id)
                diagnostics.record_tool_call()

        steps.append(
            Step(
                step_id=step_id,
                source=source,
                message=message,
                reasoning_content=reasoning_content,
                model_name=model_name,
                timestamp=timestamp,
                metrics=metrics,
                tool_calls=tool_calls,
                observation=observation,
            )
        )

    # Detect orphaned tool calls and results
    for tc_id in tool_call_ids:
        if tc_id not in tool_result_map:
            diagnostics.record_orphaned_call(tc_id)
    for tr_id in tool_result_map:
        if tr_id not in tool_call_ids:
            diagnostics.record_orphaned_result(tr_id)

    return steps


def _collect_tool_results(message_entries: list[dict]) -> dict[str, dict]:
    """Pre-scan toolResult messages into a lookup dict keyed by toolCallId.

    Args:
        message_entries: Message-type JSONL entries.

    Returns:
        Mapping of tool_call_id to result dict with output, is_error, and details.
    """
    results: dict[str, dict] = {}
    for entry in message_entries:
        msg = entry.get("message", {})
        if msg.get("role") != "toolResult":
            continue
        tool_call_id = msg.get("toolCallId", "")
        if not tool_call_id:
            continue
        raw_content = msg.get("content", "")
        output = coerce_to_string(raw_content)
        is_error = bool(msg.get("isError", False))

        result_entry: dict = {"output": output, "is_error": is_error}
        details = msg.get("details")
        if details and isinstance(details, dict):
            result_entry["details"] = details
        results[tool_call_id] = result_entry
    return results


def _decompose_content(raw_content: str | list) -> tuple[str, str | None, list[ToolCall]]:
    """Split content blocks into text, reasoning, and tool calls.

    Args:
        raw_content: Content from message payload (string or block array).

    Returns:
        Tuple of (message_text, reasoning_content, tool_calls).
    """
    if isinstance(raw_content, str):
        return (raw_content.strip(), None, [])

    if not isinstance(raw_content, list):
        return ("", None, [])

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in raw_content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "text")

        if block_type == "text":
            text = block.get("text", "")
            if text:
                text_parts.append(text)
        elif block_type == "thinking":
            thinking = block.get("thinking", "")
            if thinking:
                thinking_parts.append(thinking)
        elif block_type == "toolCall":
            tool_calls.append(
                ToolCall(
                    tool_call_id=block.get("id", ""),
                    function_name=block.get("name", ""),
                    arguments=block.get("arguments"),
                )
            )

    message = "\n\n".join(text_parts).strip()
    reasoning = "\n\n".join(thinking_parts).strip() or None
    return (message, reasoning, tool_calls)


def _build_metrics(usage: dict | None) -> Metrics | None:
    """Convert OpenClaw usage dict to ATIF Metrics model.

    OpenClaw usage field mapping:
    - ``input`` -> prompt_tokens
    - ``output`` -> completion_tokens
    - ``cacheRead`` -> cached_tokens
    - ``cacheWrite`` -> cache_creation_tokens
    - ``cost.total`` -> cost_usd

    Args:
        usage: Usage dict from assistant message, or None.

    Returns:
        Metrics instance, or None if no usage data.
    """
    if not usage:
        return None

    input_tok = usage.get("input") or 0
    output_tok = usage.get("output") or 0
    cache_read = usage.get("cacheRead") or 0
    cache_write = usage.get("cacheWrite") or 0

    cost_data = usage.get("cost")
    cost_usd = cost_data.get("total") if isinstance(cost_data, dict) else None

    return Metrics(
        prompt_tokens=input_tok + cache_read,
        completion_tokens=output_tok,
        cached_tokens=cache_read,
        cache_creation_tokens=cache_write,
        cost_usd=cost_usd,
    )


def _build_observation(
    tool_calls: list[ToolCall], tool_result_map: dict[str, dict]
) -> Observation | None:
    """Build an Observation from tool calls and their pre-scanned results.

    Args:
        tool_calls: Tool calls from the current step.
        tool_result_map: Pre-scanned toolCallId -> result dict.

    Returns:
        Observation with results, or None if no tool calls have results.
    """
    if not tool_calls:
        return None

    obs_results: list[ObservationResult] = []
    for tc in tool_calls:
        result = tool_result_map.get(tc.tool_call_id)
        if not result:
            continue
        output = result["output"]
        if result["is_error"]:
            output = mark_error_content(output)
        extra = result.get("details")
        obs_results.append(
            ObservationResult(source_call_id=tc.tool_call_id, content=output, extra=extra)
        )

    return Observation(results=obs_results) if obs_results else None
