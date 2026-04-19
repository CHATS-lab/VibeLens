"""Unit tests for vibelens.ingest.parsers.shared.jsonl."""

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.shared.jsonl import iter_jsonl_lines


def test_yields_parsed_dicts_from_valid_content() -> None:
    content = '{"a": 1}\n{"b": 2}\n'
    assert list(iter_jsonl_lines(content)) == [{"a": 1}, {"b": 2}]


def test_skips_empty_lines() -> None:
    content = '{"a": 1}\n\n   \n{"b": 2}\n'
    assert list(iter_jsonl_lines(content)) == [{"a": 1}, {"b": 2}]


def test_skips_invalid_json_and_records_diagnostic() -> None:
    diagnostics = DiagnosticsCollector()
    content = '{"a": 1}\n{not-json}\n{"b": 2}\n'

    results = list(iter_jsonl_lines(content, diagnostics=diagnostics))

    assert results == [{"a": 1}, {"b": 2}]
    assert diagnostics.total_lines == 3
    assert diagnostics.parsed_lines == 2
    assert diagnostics.skipped_lines == 1


def test_handles_empty_content() -> None:
    assert list(iter_jsonl_lines("")) == []


def test_works_without_diagnostics_collector() -> None:
    content = '{"a": 1}\n{bad}\n'
    assert list(iter_jsonl_lines(content)) == [{"a": 1}]
