"""Tests for utils.json helpers (non-lock).

Currently exercises ``atomic_write_json``. Lock-based tests live in
``test_json_locked.py``.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vibelens.utils.json import atomic_write_json


def test_atomic_write_creates_file(tmp_path: Path):
    path = tmp_path / "cache.json"

    atomic_write_json(path, {"hello": "world"})

    assert path.exists()
    assert json.loads(path.read_text()) == {"hello": "world"}


def test_atomic_write_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "nested" / "deep" / "cache.json"

    atomic_write_json(path, [1, 2, 3])

    assert path.exists()
    assert json.loads(path.read_text()) == [1, 2, 3]


def test_atomic_write_indent_passthrough(tmp_path: Path):
    path = tmp_path / "pretty.json"

    atomic_write_json(path, {"a": 1, "b": 2}, indent=2)

    raw = path.read_text()
    assert "\n  " in raw, f"expected pretty-printed output, got: {raw!r}"


def test_atomic_write_no_indent_is_compact(tmp_path: Path):
    path = tmp_path / "compact.json"

    atomic_write_json(path, {"a": 1, "b": 2})

    assert "\n" not in path.read_text()


def test_atomic_write_cleans_up_tmp(tmp_path: Path):
    path = tmp_path / "cache.json"

    atomic_write_json(path, {"x": 1})

    tmp_sibling = path.with_suffix(path.suffix + ".tmp")
    assert not tmp_sibling.exists(), "expected .tmp file to be renamed away"


def test_atomic_write_overwrites_existing(tmp_path: Path):
    path = tmp_path / "cache.json"
    path.write_text('{"old": true}')

    atomic_write_json(path, {"new": True})

    assert json.loads(path.read_text()) == {"new": True}


def test_atomic_write_preserves_original_on_failure(tmp_path: Path):
    path = tmp_path / "cache.json"
    path.write_text('{"original": "intact"}')
    original_bytes = path.read_bytes()

    with (
        patch("vibelens.utils.json.json.dumps", side_effect=TypeError("not serializable")),
        pytest.raises(TypeError),
    ):
        atomic_write_json(path, object())

    assert path.read_bytes() == original_bytes, "original file must be untouched on failure"
