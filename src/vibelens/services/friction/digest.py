"""Friction digest — format batched session contexts for LLM prompts.

Thin layer that concatenates pre-extracted session contexts from
context_extraction.py into a single digest string for one LLM batch.

Also provides StepSignal-based digest utilities used by skill_digest.py.
"""

from dataclasses import dataclass

from vibelens.models.analysis.friction import StepSignal
from vibelens.services.session_batcher import SessionBatch
from vibelens.utils.text import extract_text, is_error_content, summarize_args, truncate

TIER_THRESHOLDS = [50, 150, 500]
MSG_LIMITS = [200, 120, 80, 40]
OBS_LIMITS = [150, 80, 40, 0]
ARG_LIMITS = [200, 120, 60, 30]


@dataclass
class DigestLimits:
    """Truncation limits for step signal formatting."""

    max_message_chars: int
    max_observation_chars: int
    max_arg_chars: int


def select_limits(step_count: int) -> DigestLimits:
    """Pick truncation limits based on total step count.

    More steps → tighter limits to keep total prompt size bounded.

    Args:
        step_count: Number of StepSignals being digested.

    Returns:
        DigestLimits with appropriate truncation thresholds.
    """
    tier = 0
    for i, threshold in enumerate(TIER_THRESHOLDS):
        if step_count > threshold:
            tier = i + 1
    tier = min(tier, len(MSG_LIMITS) - 1)
    return DigestLimits(
        max_message_chars=MSG_LIMITS[tier],
        max_observation_chars=OBS_LIMITS[tier],
        max_arg_chars=ARG_LIMITS[tier],
    )


def _group_by_session(signals: list[StepSignal]) -> dict[str, list[StepSignal]]:
    """Group signals by session_id preserving order.

    Args:
        signals: Flat list of StepSignals.

    Returns:
        Ordered dict of session_id → signals.
    """
    grouped: dict[str, list[StepSignal]] = {}
    for signal in signals:
        grouped.setdefault(signal.session_id, []).append(signal)
    return grouped


def _format_step(signal: StepSignal, limits: DigestLimits) -> str:
    """Format a single StepSignal into compact text.

    Args:
        signal: The step signal to format.
        limits: Truncation limits.

    Returns:
        Formatted step text.
    """
    step = signal.step
    source = step.source.value.upper()
    msg = truncate(extract_text(step.message), limits.max_message_chars)
    lines = [f"[{signal.step_index}] {source}: {msg}"]

    for tc in step.tool_calls:
        args_str = summarize_args(tc.arguments, max_total_chars=limits.max_arg_chars)
        lines.append(f"  TOOL: fn={tc.function_name} {args_str}")

        if tc.observation and tc.observation.result:
            obs_text = extract_text(tc.observation.result)
            if is_error_content(obs_text):
                lines.append(f"  ERROR: {truncate(obs_text, limits.max_observation_chars)}")
            elif limits.max_observation_chars > 0:
                lines.append(f"  OUT: {truncate(obs_text, limits.max_observation_chars)}")

    return "\n".join(lines)


def format_batch_digest(batch: SessionBatch) -> str:
    """Concatenate pre-extracted session contexts for one LLM prompt.

    Args:
        batch: SessionBatch containing pre-extracted session contexts.

    Returns:
        Formatted digest text with all session contexts.
    """
    if not batch.session_contexts:
        return "[no sessions]"

    parts = [ctx.context_text for ctx in batch.session_contexts]
    return "\n\n".join(parts)
