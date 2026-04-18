"""Tests for the byte-accurate JSON item scanner."""

import json

import pytest

from vibelens.storage.extension.json_item_scanner import ScannerError, scan_items


def _build_doc(items: list[dict]) -> bytes:
    """Serialize a catalog-shaped document with `items` as the object array."""
    return json.dumps({"generated_on": "2026-04-18", "items": items}).encode("utf-8")


def test_scan_items_single_item():
    """A single-item doc yields exactly one offset pair."""
    doc = _build_doc([{"item_id": "a:1", "name": "alpha"}])
    results = list(scan_items(doc, id_key="item_id"))
    assert len(results) == 1
    item_id, offset, length = results[0]
    assert item_id == "a:1"
    assert doc[offset : offset + length].startswith(b"{")
    assert doc[offset : offset + length].endswith(b"}")
    restored = json.loads(doc[offset : offset + length])
    assert restored["item_id"] == "a:1"
    print(f"single item: id={item_id} offset={offset} length={length}")


def test_scan_items_multiple():
    """Each item in a multi-item doc yields its own offset pair."""
    items = [{"item_id": f"a:{i}", "name": f"n{i}"} for i in range(3)]
    doc = _build_doc(items)
    results = list(scan_items(doc, id_key="item_id"))
    assert [r[0] for r in results] == ["a:0", "a:1", "a:2"]
    for item_id, offset, length in results:
        restored = json.loads(doc[offset : offset + length])
        assert restored["item_id"] == item_id
    print(f"multi-item: {[r[0] for r in results]}")


def test_scan_items_non_ascii():
    """Non-ASCII payloads produce byte offsets (not char offsets)."""
    items = [
        {"item_id": "emoji:1", "name": "smile 🙂"},
        {"item_id": "cjk:1", "name": "漢字"},
    ]
    doc = _build_doc(items)
    results = list(scan_items(doc, id_key="item_id"))
    assert len(results) == 2
    for item_id, offset, length in results:
        slice_bytes = doc[offset : offset + length]
        restored = json.loads(slice_bytes)
        assert restored["item_id"] == item_id
    print("non-ascii byte offsets round-trip")


def test_scan_items_string_with_braces():
    """Braces and brackets inside string values don't confuse the scanner."""
    items = [
        {"item_id": "str:1", "name": "a { b } c [ d ] e"},
        {"item_id": "str:2", "name": 'contains "quotes" and \\n'},
    ]
    doc = _build_doc(items)
    results = list(scan_items(doc, id_key="item_id"))
    assert [r[0] for r in results] == ["str:1", "str:2"]
    for item_id, offset, length in results:
        restored = json.loads(doc[offset : offset + length])
        assert restored["item_id"] == item_id
    print("string-embedded brackets handled")


def test_scan_items_nested_objects():
    """Nested objects/arrays inside items are spanned correctly."""
    items = [
        {
            "item_id": "nest:1",
            "metadata": {"a": [1, 2, {"b": "c"}], "d": {"e": [3]}},
        }
    ]
    doc = _build_doc(items)
    ((item_id, offset, length),) = tuple(scan_items(doc, id_key="item_id"))
    restored = json.loads(doc[offset : offset + length])
    assert restored["metadata"]["a"][2]["b"] == "c"
    print("nested structures spanned")


def test_scan_items_empty_array():
    """An empty items array yields nothing."""
    doc = _build_doc([])
    assert list(scan_items(doc, id_key="item_id")) == []
    print("empty items array yields none")


def test_scan_items_missing_items_key_raises():
    """A doc without `items` raises a clear error."""
    doc = json.dumps({"generated_on": "x"}).encode("utf-8")
    with pytest.raises(ScannerError, match="items"):
        list(scan_items(doc, id_key="item_id"))


def test_scan_items_missing_id_raises():
    """An item without the id_key raises a clear error."""
    doc = _build_doc([{"name": "no-id-here"}])
    with pytest.raises(ScannerError, match="item_id"):
        list(scan_items(doc, id_key="item_id"))
