"""Tests for model-name normalization."""

import pytest

from vibelens.llm.normalizer import normalize_model_name


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Exact base names and their own entries.
        ("gpt-5", "gpt-5"),
        ("gpt-5.4", "gpt-5.4"),
        ("gpt-5-mini", "gpt-5-mini"),
        ("grok-4", "grok-4"),
        # Date / preview suffixes still match the base prefix.
        ("gpt-5-2026-01-01", "gpt-5"),
        ("gemini-2.5-flash-preview-04-17", "gemini-2.5-flash"),
        # Provider / path prefixes are stripped.
        ("anthropic/claude-opus-4-6", "claude-opus-4-6"),
        ("openai:gpt-5", "gpt-5"),
        ("models/gemini-2.5-pro", "gemini-2.5-pro"),
        # Dotted Anthropic version is rewritten to the dashed canonical.
        ("claude-opus-4.7", "claude-opus-4-7"),
        # Case insensitivity.
        ("GPT-5", "gpt-5"),
        # Unrecognized.
        ("", None),
        (None, None),
        ("totally-unknown-model", None),
    ],
)
def test_normalize_model_name(raw: str | None, expected: str | None) -> None:
    assert normalize_model_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "gpt-5.5",  # an unknown finer version of gpt-5
        "gpt-5.9",
        "grok-4.5",  # an unknown finer version of grok-4
        "glm-5.2",
    ],
)
def test_unknown_finer_version_is_not_collapsed_to_coarser(raw: str) -> None:
    """A finer dotted version must not be collapsed onto its coarser base.

    ``gpt-5.5`` is a different model from ``gpt-5``; returning ``gpt-5`` would
    misprice it and overwrite the source model name. Unknown finer versions
    return None so callers fall back to the raw value.
    """
    assert normalize_model_name(raw) is None
