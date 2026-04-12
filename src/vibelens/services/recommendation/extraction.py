"""Lightweight context extraction using compaction summaries.

Reads compaction agent JSONL files (~50KB each) instead of full session
files (~2.3MB each) to produce a digest suitable for the L2 profile
generation step. Falls back to session metadata for sessions without
compaction agents.
"""

import json
from pathlib import Path

from vibelens.llm.tokenizer import count_tokens
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Max characters per compaction summary
SUMMARY_MAX_CHARS = 300
# Default token budget for the digest (leaves room for system prompt overhead)
DIGEST_TOKEN_BUDGET = 80_000
# Max sessions per project in diversity sampling
MAX_PER_PROJECT = 3


def extract_lightweight_digest(
    metadata_list: list[dict],
) -> tuple[str, int, int]:
    """Extract a lightweight digest from session metadata and compaction files.

    For sessions with compaction agents: reads the compaction JSONL directly,
    extracts the summary text, and truncates to SUMMARY_MAX_CHARS.
    For sessions without: formats metadata as a signal line.

    Args:
        metadata_list: List of session metadata dicts from store.list_metadata().

    Returns:
        Tuple of (digest_text, session_count, signal_count).
    """
    if not metadata_list:
        return "", 0, 0

    signals: list[tuple[str, str, str, str]] = []

    for meta in metadata_list:
        session_id = meta.get("session_id", "unknown")
        project_path = meta.get("project_path", "unknown")
        filepath = meta.get("filepath", "")
        timestamp = meta.get("timestamp", meta.get("created_at", ""))

        compaction_text = _read_compaction_summary(filepath)
        if compaction_text:
            signal = _format_compaction_signal(session_id, project_path, compaction_text)
        else:
            signal = _format_metadata_signal(session_id, meta)

        signals.append((session_id, signal, project_path, str(timestamp)))

    sampled = _sample_sessions(signals, token_budget=DIGEST_TOKEN_BUDGET)
    digest = "\n\n".join(signal_text for _, signal_text in sampled)

    total_sessions = len(metadata_list)
    signal_count = len(sampled)
    if signal_count < total_sessions:
        logger.info(
            "Sampled %d/%d sessions (%d tokens)",
            signal_count,
            total_sessions,
            count_tokens(digest),
        )

    return digest, total_sessions, signal_count


def _read_compaction_summary(filepath: str) -> str | None:
    """Read the most recent compaction summary for a session.

    Claude Code layout: {uuid}/subagents/agent-acompact-*.jsonl
    Derives compaction path from the main session filepath.

    Args:
        filepath: Path to the main session JSONL file.

    Returns:
        Summary text from the compaction agent, or None if unavailable.
    """
    if not filepath:
        return None

    session_path = Path(filepath)
    compaction_dir = session_path.parent / session_path.stem / "subagents"
    if not compaction_dir.is_dir():
        return None

    compaction_files = sorted(compaction_dir.glob("agent-acompact-*.jsonl"))
    if not compaction_files:
        return None

    # Read the most recent compaction file (last in sorted order)
    latest = compaction_files[-1]
    return _extract_summary_from_jsonl(latest)


def _extract_summary_from_jsonl(jsonl_path: Path) -> str | None:
    """Extract the assistant's summary text from a compaction JSONL file.

    Scans for the first message with role=assistant and extracts
    the text content, which is the compaction summary.

    Args:
        jsonl_path: Path to the compaction agent JSONL file.

    Returns:
        Summary text truncated to SUMMARY_MAX_CHARS, or None.
    """
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                message = entry.get("message", entry)
                if message.get("role") != "assistant":
                    continue

                content = message.get("content", "")
                if isinstance(content, list):
                    text_parts = [
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    text = " ".join(text_parts)
                elif isinstance(content, str):
                    text = content
                else:
                    continue

                text = text.strip()
                if text:
                    return text[:SUMMARY_MAX_CHARS]
    except OSError as exc:
        logger.debug("Failed to read compaction file %s: %s", jsonl_path, exc)

    return None


def _format_compaction_signal(session_id: str, project_path: str, summary: str) -> str:
    """Format a session signal from a compaction summary.

    Args:
        session_id: Session identifier.
        project_path: Project directory path.
        summary: Compaction summary text.

    Returns:
        Formatted signal string.
    """
    project_name = Path(project_path).name if project_path else "unknown"
    return f"--- SESSION {session_id} ---\nProject: {project_name}\nCompaction summary: {summary}"


def _format_metadata_signal(session_id: str, meta: dict) -> str:
    """Format a session signal from metadata only (no compaction available).

    Args:
        session_id: Session identifier.
        meta: Session metadata dict.

    Returns:
        Formatted signal string.
    """
    project_name = Path(meta.get("project_path", "unknown")).name
    tool_count = meta.get("total_tool_calls", 0)
    duration = meta.get("duration_seconds", 0)
    model = meta.get("model", "unknown")
    dur_min = round(duration / 60) if duration else 0
    return (
        f"--- SESSION {session_id} ---\n"
        f"Project: {project_name} | Tools: {tool_count} | Duration: {dur_min}min | Model: {model}"
    )


def _sample_sessions(
    sessions: list[tuple[str, str, str, str]],
    token_budget: int = DIGEST_TOKEN_BUDGET,
) -> list[tuple[str, str]]:
    """Sample a diverse, representative subset of sessions to fit within token budget.

    Uses project-stratified sampling: groups by project, selects up to
    MAX_PER_PROJECT most recent sessions per project, then trims by
    project activity until under budget.

    Args:
        sessions: List of (session_id, signal_text, project_path, timestamp) tuples.
        token_budget: Maximum tokens for the combined digest.

    Returns:
        List of (session_id, signal_text) tuples fitting within budget.
    """
    if not sessions:
        return []

    # Check if everything fits without sampling
    combined = "\n\n".join(signal for _, signal, _, _ in sessions)
    if count_tokens(combined) <= token_budget:
        return [(sid, signal) for sid, signal, _, _ in sessions]

    # Group by project
    project_groups: dict[str, list[tuple[str, str, str]]] = {}
    for sid, signal, project, timestamp in sessions:
        project_groups.setdefault(project, []).append((sid, signal, timestamp))

    # Within each project, sort by timestamp (newest first), keep top MAX_PER_PROJECT
    selected: list[tuple[str, str, str]] = []
    for _project, group in project_groups.items():
        group.sort(key=lambda x: x[2], reverse=True)
        selected.extend(group[:MAX_PER_PROJECT])

    # Check if stratified selection fits
    combined = "\n\n".join(signal for _, signal, _ in selected)
    if count_tokens(combined) <= token_budget:
        return [(sid, signal) for sid, signal, _ in selected]

    # Still over budget: rank projects by session count (most active first),
    # drop least-active projects until under budget
    project_by_count = sorted(
        project_groups.keys(), key=lambda p: len(project_groups[p]), reverse=True
    )
    result: list[tuple[str, str]] = []
    running_text = ""
    for project in project_by_count:
        group = project_groups[project]
        group.sort(key=lambda x: x[2], reverse=True)
        for sid, signal, _ in group[:MAX_PER_PROJECT]:
            candidate = running_text + "\n\n" + signal if running_text else signal
            if count_tokens(candidate) > token_budget:
                return result
            running_text = candidate
            result.append((sid, signal))

    return result
