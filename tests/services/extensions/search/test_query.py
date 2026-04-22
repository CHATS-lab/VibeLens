"""Tests for query.coerce_legacy_sort and ExtensionQuery type coercion."""

from vibelens.models.enums import AgentExtensionType
from vibelens.services.extensions.search.query import (
    ExtensionQuery,
    SortMode,
    coerce_legacy_sort,
)


def test_coerce_popularity_to_default():
    assert coerce_legacy_sort("popularity") == SortMode.DEFAULT


def test_coerce_relevance_to_personalized():
    assert coerce_legacy_sort("relevance") == SortMode.PERSONALIZED


def test_coerce_passthrough_modern_values():
    for mode in SortMode:
        assert coerce_legacy_sort(mode.value) == mode


def test_coerce_unknown_falls_back_to_default():
    assert coerce_legacy_sort("nonsense") == SortMode.DEFAULT
    assert coerce_legacy_sort("") == SortMode.DEFAULT
    assert coerce_legacy_sort(None) == SortMode.DEFAULT  # type: ignore[arg-type]


def test_coerce_case_insensitive_and_strips():
    assert coerce_legacy_sort("  Quality  ") == SortMode.QUALITY
    assert coerce_legacy_sort("RELEVANCE") == SortMode.PERSONALIZED


def test_extension_query_accepts_string_for_extension_type():
    """Pydantic coerces a valid string to AgentExtensionType."""
    q = ExtensionQuery(extension_type="skill")
    print(f"coerced: {q.extension_type}, type={type(q.extension_type)}")
    assert q.extension_type == AgentExtensionType.SKILL


def test_extension_query_defaults_to_default_sort():
    q = ExtensionQuery()
    assert q.sort == SortMode.DEFAULT
    assert q.search_text == ""
    assert q.profile is None
    assert q.extension_type is None
