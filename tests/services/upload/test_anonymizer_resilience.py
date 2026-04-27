"""Regression tests for redaction resilience.

Each documented bug must NOT crash the anonymizer when triggered.
"""

from vibelens.ingest.anonymize.rule_anonymizer.path_hasher import PathHasher
from vibelens.ingest.anonymize.rule_anonymizer.redactor import (
    redact_patterns,
)
from vibelens.ingest.anonymize.traversal import _transform_value


def test_path_hasher_handles_unknown_match_via_get_callback(monkeypatch):
    """Bug 1: ``replace_path`` used ``dict[key]`` so a regex match for a
    username the discovery pass had missed would crash with ``KeyError``.
    The fix uses ``.get()`` and returns the original substring on miss.
    """
    hasher = PathHasher()
    # Stub _register_username so discovery never populates the map; any
    # subsequent regex match will then fall through to the safe branch.
    monkeypatch.setattr(hasher, "_register_username", lambda *_: None)
    text = "/Users/charlie/x /home/dora/y"
    # Must not raise even though the substitution regex will match
    # 'charlie' / 'dora' but those aren't in _username_to_hash.
    out, _ = hasher.anonymize_text(text)
    assert "charlie" in out
    assert "dora" in out


def test_redact_patterns_caps_huge_input_to_avoid_backtracking():
    """Bug 2: PEM private-key pattern can backtrack catastrophically on
    a 1MB+ string with no END marker. Cap input length and skip the pass."""
    huge = "-----BEGIN PRIVATE KEY-----" + ("X" * 2_000_000)
    # Use a pattern set that contains the PEM pattern at minimum.
    from vibelens.ingest.anonymize.rule_anonymizer.patterns import CREDENTIAL_PATTERNS
    out, count = redact_patterns(huge, CREDENTIAL_PATTERNS, "[REDACTED]")
    assert count == 0
    # Returns input unchanged when over the cap.
    assert len(out) == len(huge)


def test_transform_value_handles_deep_nesting():
    """Bug 3: pathologically nested extra dicts blow Python's stack."""
    nested: dict | None = None
    for _ in range(2000):
        nested = {"k": nested}

    # Identity transform — must not raise RecursionError.
    out = _transform_value(nested, lambda s: s)
    assert out is not None
