"""Tests for locked JSONL append/remove.

The lock implementation differs per platform (``fcntl`` on POSIX,
``msvcrt`` on Windows); the tests exercise the shared API so Windows
CI catches regressions when the import or lock call changes.
"""

from pathlib import Path

from vibelens.utils.json import locked_jsonl_append, locked_jsonl_remove, read_jsonl


def test_append_creates_file_and_writes_line(tmp_path: Path):
    path = tmp_path / "log.jsonl"

    locked_jsonl_append(path, {"id": "a", "v": 1})

    assert path.exists()
    assert read_jsonl(path) == [{"id": "a", "v": 1}]


def test_append_adds_lines_in_order(tmp_path: Path):
    path = tmp_path / "log.jsonl"
    for i in range(3):
        locked_jsonl_append(path, {"i": i})

    rows = read_jsonl(path)
    assert [r["i"] for r in rows] == [0, 1, 2]


def test_remove_drops_matching_lines_keeps_others(tmp_path: Path):
    path = tmp_path / "log.jsonl"
    locked_jsonl_append(path, {"id": "a", "v": 1})
    locked_jsonl_append(path, {"id": "b", "v": 2})
    locked_jsonl_append(path, {"id": "a", "v": 3})

    removed = locked_jsonl_remove(path, "id", "a")

    assert removed == 2
    assert read_jsonl(path) == [{"id": "b", "v": 2}]


def test_remove_on_missing_file_returns_zero(tmp_path: Path):
    path = tmp_path / "nope.jsonl"
    assert locked_jsonl_remove(path, "id", "a") == 0


def test_remove_preserves_unparseable_lines(tmp_path: Path):
    path = tmp_path / "log.jsonl"
    path.write_text('{"id": "a"}\nnot-json\n{"id": "b"}\n', encoding="utf-8")

    removed = locked_jsonl_remove(path, "id", "a")

    assert removed == 1
    # Unparseable "not-json" is preserved; "b" survives.
    content = path.read_text(encoding="utf-8")
    assert "not-json" in content
    assert '"id": "b"' in content
