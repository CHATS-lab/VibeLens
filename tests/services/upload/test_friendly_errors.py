"""Tests for ``to_friendly_error``: raw exceptions become summary + details."""

import json
import sqlite3

from vibelens.services.upload.processor import to_friendly_error


def test_json_decode_error_maps_to_friendly_summary():
    try:
        json.loads("not json")
    except json.JSONDecodeError as exc:
        out = to_friendly_error(exc)
    assert "JSON" in out["summary"]
    assert out["details"]


def test_sqlite_database_error_maps_to_friendly_summary():
    out = to_friendly_error(sqlite3.DatabaseError("file is encrypted or is not a database"))
    assert "SQLite" in out["summary"]
    assert "file is encrypted" in out["details"]


def test_unicode_decode_error_maps_via_class_name():
    exc = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    out = to_friendly_error(exc)
    assert "UTF-8" in out["summary"]
    assert "invalid start byte" in out["details"]


def test_file_not_found_error_maps_via_class_name():
    out = to_friendly_error(FileNotFoundError(2, "No such file", "/x/y"))
    assert "missing" in out["summary"].lower()


def test_unknown_exception_falls_back_to_generic():
    out = to_friendly_error(RuntimeError("boom"))
    assert out["summary"]  # non-empty generic message
    assert out["details"] == "boom"


def test_empty_exception_falls_back_to_class_name():
    out = to_friendly_error(RuntimeError(""))
    assert out["details"] == "RuntimeError"


def test_duplicate_step_ids_message_maps_to_parser_bug_summary():
    """Pydantic ValidationError carrying ``duplicate step IDs`` should surface
    a parser-bug message, not the generic 'unexpected ValidationError'."""
    out = to_friendly_error(
        ValueError(
            "1 validation error for Trajectory\n  Value error, Trajectory abc: "
            "duplicate step IDs: ['x', 'x']"
        )
    )
    assert "parser bug" in out["summary"].lower()
    assert "duplicate step ids" in out["details"].lower()


def test_size_limit_exception_maps_to_specific_summary():
    out = to_friendly_error(ValueError("Zip file exceeds size limit: 999 > 200"))
    assert "size limit" in out["summary"].lower()


def test_validation_error_class_name_maps_to_parser_bug():
    """A ValidationError without the dup-id substring still maps via class name."""

    # Synthesize a class that mimics pydantic.ValidationError's class name
    # without requiring the import (the friendly mapper does string match).
    class ValidationError(Exception):  # noqa: N818
        pass

    out = to_friendly_error(ValidationError("some other validation issue"))
    assert "parser bug" in out["summary"].lower()


def test_fallback_summary_names_the_exception_class():
    """Generic fallback should at least tell the user what category failed."""
    out = to_friendly_error(RuntimeError("boom"))
    assert "RuntimeError" in out["summary"]
