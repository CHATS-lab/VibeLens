"""Hermes Agent JSONL format parser.

Parses ``~/.hermes/sessions/*.jsonl`` for Hermes Agent conversation data.

Hermes Agent stores each conversation event as a separate JSONL line with a
top-level ``role`` field.  The format is:

- ``session_meta``: first line, contains tool definitions, model name, platform.
- ``user``: user messages.
- ``assistant``: agent responses. May contain ``tool_calls`` (list of tool
  invocation objects) and ``reasoning`` (chain-of-thought text).
- ``tool``: tool execution results, linked to the preceding assistant's
  tool_calls via ``tool_call_id``.

Tool calls follow the Anthropic Messages API convention: invocations appear
as objects inside ``assistant.tool_calls`` with ``id``, ``function.name``,
and ``function.arguments``.  Results come back in ``tool`` role entries linked
by ``tool_call_id``.
"""

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.base import (
    BaseParser,
    ERROR_PREFIX,
    mark_error_content,
)
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import (
    Agent,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.utils import get_logger, normalize_timestamp

logger = get_logger(__name__)

# Hermes session files live in ~/.hermes/sessions/
HERMES_DATA_DIR = Path.home() / ".hermes" / "sessions"


class HermesParser(BaseParser):
    """Parser for Hermes Agent JSONL session files."""

    AGENT_TYPE = AgentType.HERMES
    LOCAL_DATA_DIR = HERMES_DATA_DIR

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Discover Hermes session JSONL files.

        Hermes stores sessions as ``<timestamp>_<id>.jsonl`` in
        ``~/.hermes/sessions/``.  We skip ``session_*.json`` (full dumps)
        and only read the JSONL files.

        Args:
            data_dir: Hermes sessions directory.

        Returns:
            List of JSONL session file paths, sorted by name (chronological).
        """
        if not data_dir.is_dir():
            return []
        files = sorted(
            p
            for p in data_dir.iterdir()
            if p.suffix == ".jsonl" and not p.name.startswith("session_")
        )
        return files

    def parse(
        self, content: str, source_path: str | None = None
    ) -> list[Trajectory]:
        """Parse Hermes Agent JSONL content into Trajectory objects.

        Args:
            content: Raw JSONL content string.
            source_path: Original file path for session ID extraction.

        Returns:
            List with a single Trajectory (one session per file).
        """
        diagnostics = DiagnosticsCollector()

        lines = content.strip().split("\n") if content.strip() else []
        raw_events: list[dict] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            diagnostics.total_lines += 1
            try:
                raw_events.append(json.loads(stripped))
                diagnostics.parsed_lines += 1
            except json.JSONDecodeError:
                diagnostics.record_skip("invalid JSON")
                continue

        if not raw_events:
            return []

        # Extract session metadata from the first session_meta line
        model_name: str | None = None
        platform: str | None = None
        for evt in raw_events:
            if evt.get("role") == "session_meta":
                model_name = evt.get("model")
                platform = evt.get("platform")
                break

        # Build session ID from filename
        session_id = self._extract_session_id(source_path)

        # Build ATIF steps
        steps = self._build_steps(raw_events, diagnostics)

        if not steps:
            return []

        agent = self.build_agent(
            version=platform or "hermes-agent",
            model=model_name,
        )

        extra = self.build_diagnostics_extra(diagnostics)
        trajectory = self.assemble_trajectory(
            session_id=session_id,
            agent=agent,
            steps=steps,
            project_path=None,
            extra=extra,
        )
        return [trajectory]

    def _extract_session_id(self, source_path: str | None) -> str:
        """Derive a stable session ID from the file path.

        Falls back to a UUID if the path is unavailable or unparsable.

        Args:
            source_path: File path like ``/home/user/.hermes/sessions/20260418_192555_4077bccc.jsonl``

        Returns:
            Session ID string.
        """
        if source_path:
            stem = Path(source_path).stem
            # Hermes filenames: 20260418_192555_4077bccc
            if stem and not stem.startswith("session_"):
                return f"hermes-{stem}"
        return f"hermes-{uuid4().hex[:12]}"

    def _build_steps(
        self, raw_events: list[dict], diagnostics: DiagnosticsCollector
    ) -> list[Step]:
        """Convert raw JSONL events into ATIF Step objects.

        Hermes uses the pairing pattern where assistant tool_calls are
        followed by tool-role result entries.  We collect tool results
        into a lookup by tool_call_id, then build Steps that pair
        tool_calls with their observations.

        Args:
            raw_events: Parsed JSON objects from JSONL lines.
            diagnostics: Collector for tracking parse quality.

        Returns:
            Ordered list of ATIF Step objects.
        """
        # Pre-scan: build map of tool_call_id -> tool result content
        tool_result_map: dict[str, str] = {}
        for evt in raw_events:
            if evt.get("role") == "tool":
                tc_id = evt.get("tool_call_id", "")
                content = evt.get("content", "")
                if tc_id:
                    tool_result_map[tc_id] = content

        steps: list[Step] = []
        step_counter = 0

        for evt in raw_events:
            role = evt.get("role", "")

            # Skip internal metadata
            if role == "session_meta":
                continue

            # Map Hermes roles to ATIF StepSource
            if role == "user":
                source = StepSource.USER
            elif role == "assistant":
                source = StepSource.AGENT
            elif role == "tool":
                # Tool results are attached to the preceding assistant step
                # as Observation, not as standalone steps.
                continue
            else:
                # Unknown role — skip
                diagnostics.record_skip(f"unknown role: {role}")
                continue

            step_counter += 1
            step_id = str(step_counter)

            # Timestamp
            ts_raw = evt.get("timestamp")
            timestamp = normalize_timestamp(ts_raw) if ts_raw else None

            # Message content
            message = evt.get("content", "") or ""

            # Reasoning content (chain-of-thought)
            reasoning_content = evt.get("reasoning") or None

            # Model name per step (if overridden)
            model_name_step = evt.get("model") or None

            # Tool calls from assistant messages
            tool_calls_atif: list[ToolCall] = []
            observation_results: list[ObservationResult] = []

            raw_tool_calls = evt.get("tool_calls", [])
            for tc in raw_tool_calls:
                tc_id = tc.get("id") or tc.get("call_id", "")
                fn = tc.get("function", {})
                tool_name = fn.get("name", "unknown")
                tool_args_str = fn.get("arguments", "{}")

                tool_calls_atif.append(
                    ToolCall(
                        tool_call_id=tc_id,
                        tool_name=tool_name,
                        arguments=tool_args_str,
                    )
                )

                # Look up the tool result
                result_content = tool_result_map.get(tc_id, "")
                is_error = self._is_tool_error(result_content)
                if is_error:
                    result_content = mark_error_content(result_content)

                observation_results.append(
                    ObservationResult(
                        source_call_id=tc_id,
                        content=result_content,
                    )
                )

            # Build observation if there are results
            observation = None
            if observation_results:
                observation = Observation(results=observation_results)

            # Build step metrics if available
            metrics = None
            usage = evt.get("usage")
            if usage and isinstance(usage, dict):
                metrics = Metrics(
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    cost_usd=usage.get("cost_usd"),
                )

            steps.append(
                Step(
                    step_id=step_id,
                    timestamp=timestamp,
                    source=source,
                    model_name=model_name_step,
                    reasoning_content=reasoning_content,
                    message=message,
                    tool_calls=tool_calls_atif,
                    observation=observation,
                    metrics=metrics,
                )
            )

        return steps

    @staticmethod
    def _is_tool_error(content: str) -> bool:
        """Check whether a tool result content indicates an error.

        Hermes tool results are JSON strings. Errors are signalled by
        a non-zero ``exit_code`` or an ``"error"`` key at the top level.

        Args:
            content: Raw tool result content string.

        Returns:
            True if the result indicates an error.
        """
        if not content:
            return False
        if content.startswith(ERROR_PREFIX):
            return True
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                # terminal(), execute_code(), etc. return {"exit_code": N, ...}
                exit_code = parsed.get("exit_code")
                if exit_code is not None and exit_code != 0:
                    return True
                # Generic error signal
                if "error" in parsed and parsed.get("success") is False:
                    return True
        except (json.JSONDecodeError, TypeError):
            pass
        return False
