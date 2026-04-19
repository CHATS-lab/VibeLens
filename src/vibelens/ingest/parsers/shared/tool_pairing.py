"""Id-keyed pairing of tool invocations with their results.

Claude, Gemini, Hermes, OpenClaw and Claude-Web each run a pre-scan
over their entries to build a ``{tool_call_id: ObservationResult}``
lookup, then attach results to ToolCall objects during the main pass.
The pre-scan loop is identical across formats — only the field names
differ — so we parameterize it with small getter lambdas.

Codex's bounded-cache variant stays in ``codex.py`` because its
eviction policy is part of the stateful parse (see ``_CodexParseState``)
and does not share shape with the pre-scan parsers.
"""

from collections.abc import Callable, Iterable

from vibelens.ingest.parsers.base import mark_error_content
from vibelens.models.trajectories import ObservationResult


def collect_tool_results_by_id(
    entries: Iterable[dict],
    get_id: Callable[[dict], str | None],
    get_content: Callable[[dict], str | None],
    get_is_error: Callable[[dict], bool] = lambda _e: False,
) -> dict[str, ObservationResult]:
    """Build a ``{tool_call_id: ObservationResult}`` map for later attachment.

    Entries with no id or no content are skipped.  Later duplicates
    overwrite earlier ones — matches the observed behaviour of streaming
    formats that may re-emit a result after a retry.

    Args:
        entries: The raw dicts to scan (one per tool-result event).
        get_id: Returns the tool_call_id (or None to skip the entry).
        get_content: Returns the result's content string (or None to skip).
        get_is_error: Returns True when the content should be prefixed
            with ERROR_PREFIX.  Defaults to always False.

    Returns:
        Mapping from tool_call_id to the observation result.
    """
    mapping: dict[str, ObservationResult] = {}
    for entry in entries:
        call_id = get_id(entry)
        content = get_content(entry)
        if not call_id or content is None:
            continue
        if get_is_error(entry):
            content = mark_error_content(content)
        mapping[call_id] = ObservationResult(content=content)
    return mapping
