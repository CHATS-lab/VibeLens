"""Friction digest — serialize StepSignals for LLM friction analysis.

Separate from digest.py because friction analysis requires:
- step_id and tool_call_id in output (existing digest uses index-only)
- Multi-session support (per-step session attribution)
- Different truncation limits

Pure functions with no I/O.
"""

from vibelens.models.analysis.friction import StepSignal

MAX_MESSAGE_CHARS = 300
MAX_TOOL_OUTPUT_CHARS = 500
MAX_ARGS_CHARS = 200


def digest_step_signals(signals: list[StepSignal]) -> str:
    """Serialize StepSignals into prompt text grouped by session.

    Groups signals by session_id, formats each session with header
    and step details. Preserves step_ids and tool_call_ids so the
    LLM can reference them in FrictionEvent output.

    Args:
        signals: Ordered list of StepSignal from build_step_signals().

    Returns:
        Formatted text digest suitable for LLM context.
    """
    if not signals:
        return "[no steps]"

    grouped = _group_by_session(signals)
    parts: list[str] = []
    for session_id, session_signals in grouped.items():
        parts.append(_format_session(session_id, session_signals))
    return "\n\n".join(parts)


def _group_by_session(signals: list[StepSignal]) -> dict[str, list[StepSignal]]:
    """Group signals by session_id preserving order."""
    grouped: dict[str, list[StepSignal]] = {}
    for signal in signals:
        grouped.setdefault(signal.session_id, []).append(signal)
    return grouped


def _format_session(session_id: str, signals: list[StepSignal]) -> str:
    """Format all signals for one session with header and steps."""
    first = signals[0]
    header_lines = [f"=== SESSION: {session_id} ==="]
    if first.project_path:
        header_lines.append(f"PROJECT: {first.project_path}")

    # Extract agent info from step metadata if available
    model_name = first.step.model_name
    if model_name:
        header_lines.append(f"MODEL: {model_name}")
    header_lines.append(f"STEPS: {len(signals)}")
    header = "\n".join(header_lines)

    step_lines: list[str] = []
    for signal in signals:
        step_lines.append(_format_step(signal))

    return header + "\n\n" + "\n\n".join(step_lines)


def _format_step(signal: StepSignal) -> str:
    """Format a single step with step_id, source, message, tools, and observations."""
    step = signal.step
    lines: list[str] = []

    # Step header with step_id for LLM cross-referencing
    message = _extract_text(step.message)
    truncated = _truncate(message, MAX_MESSAGE_CHARS)
    lines.append(f"[{signal.step_index}] step_id={step.step_id} {step.source.value}:")
    if truncated:
        lines.append(f"  {truncated}")

    # Tool calls with tool_call_id
    for tc in step.tool_calls:
        args_summary = _summarize_args(tc.arguments)
        tc_id = tc.tool_call_id or "?"
        lines.append(f"  TOOL: tc_id={tc_id} fn={tc.function_name} args={{{args_summary}}}")

    # Observation results with source_call_id and extra metadata
    if step.observation:
        for result in step.observation.results:
            content = _extract_text(result.content)
            src_id = result.source_call_id or "?"
            content_preview = _truncate(content, MAX_TOOL_OUTPUT_CHARS)

            extra_parts: list[str] = []
            if result.extra:
                # Include is_error flag and other useful metadata
                for key, value in result.extra.items():
                    extra_parts.append(f"{key}: {value}")
            extra_str = f" extra={{{', '.join(extra_parts)}}}" if extra_parts else ""
            lines.append(f'  RESULT: src={src_id} content="{content_preview}"{extra_str}')

    return "\n".join(lines)


def _extract_text(content) -> str:
    """Extract plain text from a message or observation content field."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
            elif hasattr(part, "type"):
                text_parts.append(f"[{part.type}]")
        return " ".join(text_parts)
    return str(content)


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, collapsing whitespace and adding ellipsis."""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _summarize_args(arguments) -> str:
    """Create a compact summary of tool call arguments."""
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return _truncate(arguments, MAX_ARGS_CHARS)
    if isinstance(arguments, dict):
        parts = []
        for key, value in arguments.items():
            val_str = str(value)
            parts.append(f"{key}={_truncate(val_str, 60)}")
        return ", ".join(parts)
    return _truncate(str(arguments), MAX_ARGS_CHARS)
