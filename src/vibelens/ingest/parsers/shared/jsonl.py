"""Safe JSONL parsing from an in-memory content string.

Replaces copies of the same loop that lived in codex, hermes,
dataclaw, claude_code, and openclaw.  Use BaseParser.iter_jsonl_safe
when streaming directly from a Path; use iter_jsonl_lines when the
content is already in memory (e.g. after a read_text call).
"""

import json
from collections.abc import Iterator

from vibelens.ingest.diagnostics import DiagnosticsCollector


def iter_jsonl_lines(
    content: str,
    diagnostics: DiagnosticsCollector | None = None,
) -> Iterator[dict]:
    """Yield parsed dicts from a JSONL content string.

    Blank lines are skipped silently.  Lines that fail JSON decode are
    skipped and reported to ``diagnostics`` (if provided) so callers
    can surface parse-quality issues to the UI.

    Args:
        content: Raw JSONL text.  Typically the output of ``Path.read_text``.
        diagnostics: Optional collector.  When supplied, every non-blank
            line bumps ``total_lines`` and either ``parsed_lines`` (on
            success) or ``skipped_lines`` (on JSON error).

    Yields:
        One ``dict`` per successfully parsed line, in file order.
    """
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if diagnostics is not None:
            diagnostics.total_lines += 1
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            if diagnostics is not None:
                diagnostics.record_skip("invalid JSON")
            continue
        if diagnostics is not None:
            diagnostics.parsed_lines += 1
        yield parsed
