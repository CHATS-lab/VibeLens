"""Text scanning and redaction engine for regex-based secret detection.

Scans text against compiled pattern lists, deduplicates overlapping
matches, and replaces them end-to-start to preserve character offsets.
"""

import re
from typing import NamedTuple

from vibelens.ingest.anonymize.rule_anonymizer.patterns import (
    PatternDef,
    is_allowlisted,
)


class Finding(NamedTuple):
    """A single secret match with its location in the source text."""

    name: str
    start: int
    end: int
    matched_text: str


def scan_text(text: str, patterns: list[PatternDef]) -> list[Finding]:
    """Scan text for all non-overlapping secret matches.

    Runs each pattern against the text and filters out allowlisted matches.

    Args:
        text: The source text to scan.
        patterns: List of named regex patterns to match against.

    Returns:
        List of Finding objects sorted by start position ascending.
    """
    findings: list[Finding] = []
    for pdef in patterns:
        for match in pdef.pattern.finditer(text):
            matched = match.group(0)
            if is_allowlisted(matched):
                continue
            findings.append(Finding(pdef.name, match.start(), match.end(), matched))
    findings.sort(key=lambda f: f.start)
    return findings


def _deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Remove overlapping findings, keeping the earliest (longest) match.

    When two findings overlap, the one starting earlier wins. If they
    start at the same position, the longer match wins.

    Args:
        findings: Sorted list of findings (by start position).

    Returns:
        De-duplicated list with no overlapping ranges.
    """
    if not findings:
        return []
    deduped: list[Finding] = [findings[0]]
    for finding in findings[1:]:
        last = deduped[-1]
        if finding.start >= last.end:
            deduped.append(finding)
        # Overlapping — skip (the earlier/longer match already covers it)
    return deduped


def redact_patterns(
    text: str, patterns: list[PatternDef], placeholder: str
) -> tuple[str, int]:
    """Scan and redact all pattern matches in text.

    Finds matches, deduplicates overlaps, then replaces end-to-start
    so earlier replacements don't shift later offsets.

    Args:
        text: Source text to redact.
        patterns: Compiled regex patterns to match.
        placeholder: Replacement string for each match.

    Returns:
        Tuple of (redacted text, number of replacements made).
    """
    findings = scan_text(text, patterns)
    findings = _deduplicate_findings(findings)
    if not findings:
        return text, 0
    # Replace end-to-start to preserve character offsets
    for finding in reversed(findings):
        text = text[: finding.start] + placeholder + text[finding.end :]
    return text, len(findings)


def redact_custom_strings(
    text: str, strings: list[str], placeholder: str
) -> tuple[str, int]:
    """Replace all occurrences of custom literal strings in text.

    Args:
        text: Source text to redact.
        strings: Literal strings to find and replace.
        placeholder: Replacement string for each match.

    Returns:
        Tuple of (redacted text, total number of replacements made).
    """
    total_count = 0
    for literal in strings:
        if not literal:
            continue
        escaped = re.escape(literal)
        new_text, count = re.subn(escaped, placeholder, text)
        text = new_text
        total_count += count
    return text, total_count
