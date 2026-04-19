"""Unit tests for vibelens.ingest.parsers.shared.tool_pairing."""

from vibelens.ingest.parsers.base import ERROR_PREFIX
from vibelens.ingest.parsers.shared.tool_pairing import collect_tool_results_by_id


def test_collects_results_keyed_by_id() -> None:
    entries = [
        {"call_id": "a", "output": "result-a"},
        {"call_id": "b", "output": "result-b"},
    ]

    mapping = collect_tool_results_by_id(
        entries,
        get_id=lambda e: e.get("call_id"),
        get_content=lambda e: e.get("output"),
    )

    assert set(mapping.keys()) == {"a", "b"}
    assert mapping["a"].content == "result-a"
    assert mapping["b"].content == "result-b"


def test_skips_entries_without_id_or_content() -> None:
    entries = [
        {"call_id": None, "output": "orphan"},
        {"call_id": "a", "output": None},
        {"call_id": "b", "output": "real"},
    ]

    mapping = collect_tool_results_by_id(
        entries,
        get_id=lambda e: e.get("call_id"),
        get_content=lambda e: e.get("output"),
    )

    assert set(mapping.keys()) == {"b"}


def test_marks_error_content_with_prefix() -> None:
    entries = [{"call_id": "a", "output": "boom", "error": True}]

    mapping = collect_tool_results_by_id(
        entries,
        get_id=lambda e: e.get("call_id"),
        get_content=lambda e: e.get("output"),
        get_is_error=lambda e: bool(e.get("error")),
    )

    assert mapping["a"].content.startswith(ERROR_PREFIX)
    assert mapping["a"].content.endswith("boom")


def test_later_duplicate_id_wins() -> None:
    entries = [
        {"call_id": "a", "output": "first"},
        {"call_id": "a", "output": "second"},
    ]

    mapping = collect_tool_results_by_id(
        entries,
        get_id=lambda e: e.get("call_id"),
        get_content=lambda e: e.get("output"),
    )

    assert mapping["a"].content == "second"
