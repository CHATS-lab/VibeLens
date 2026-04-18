"""Byte-accurate scanner for catalog-shaped JSON documents.

Walks a ``{"items": [ ... ]}`` document in binary mode and yields
``(item_id, byte_offset, byte_length)`` per top-level object in the
items array. Designed for building an offset index without fully
parsing the entire document into Python objects.

Assumes the input is valid UTF-8 JSON with a top-level ``items`` array
whose elements are objects containing ``id_key``.
"""

import json
from collections.abc import Iterator

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

_ITEMS_KEY = b'"items"'


class ScannerError(RuntimeError):
    """Raised when the scanner cannot locate items or extract an id."""


def scan_items(buf: bytes, id_key: str) -> Iterator[tuple[str, int, int]]:
    """Yield (item_id, byte_offset, byte_length) for each top-level item.

    Args:
        buf: Entire document bytes.
        id_key: Key whose string value identifies each item (e.g. "item_id").

    Yields:
        Tuples of (id_value, offset_in_buf, length_in_bytes). Slicing
        ``buf[offset:offset + length]`` produces valid JSON for that item.

    Raises:
        ScannerError: If the document has no "items" array, or any item
            is missing ``id_key``.
    """
    array_start = _find_items_array(buf)
    cursor = array_start + 1
    id_key_bytes = f'"{id_key}"'.encode("utf-8")

    while cursor < len(buf):
        cursor = _skip_ws_and_commas(buf, cursor)
        if cursor >= len(buf) or buf[cursor : cursor + 1] == b"]":
            return
        if buf[cursor : cursor + 1] != b"{":
            raise ScannerError(
                f"expected '{{' at offset {cursor}, found {buf[cursor : cursor + 1]!r}"
            )

        start = cursor
        end = _scan_object_end(buf, start)
        slice_bytes = buf[start:end]
        item_id = _extract_id(slice_bytes, id_key_bytes, id_key)
        yield item_id, start, end - start
        cursor = end


def _find_items_array(buf: bytes) -> int:
    """Locate the byte offset of the ``[`` opening the items array."""
    idx = 0
    while True:
        pos = buf.find(_ITEMS_KEY, idx)
        if pos < 0:
            raise ScannerError('document has no top-level "items" key')
        after = _skip_ws(buf, pos + len(_ITEMS_KEY))
        if after < len(buf) and buf[after : after + 1] == b":":
            after = _skip_ws(buf, after + 1)
            if after < len(buf) and buf[after : after + 1] == b"[":
                return after
        idx = pos + len(_ITEMS_KEY)


def _scan_object_end(buf: bytes, start: int) -> int:
    """Given ``buf[start] == '{'``, return the offset AFTER the matching ``}``."""
    depth = 0
    in_string = False
    escape = False
    i = start
    while i < len(buf):
        ch = buf[i : i + 1]
        if in_string:
            if escape:
                escape = False
            elif ch == b"\\":
                escape = True
            elif ch == b'"':
                in_string = False
        else:
            if ch == b'"':
                in_string = True
            elif ch == b"{":
                depth += 1
            elif ch == b"}":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ScannerError(f"unterminated object starting at offset {start}")


def _skip_ws(buf: bytes, idx: int) -> int:
    """Advance past whitespace."""
    while idx < len(buf) and buf[idx : idx + 1] in (b" ", b"\t", b"\n", b"\r"):
        idx += 1
    return idx


def _skip_ws_and_commas(buf: bytes, idx: int) -> int:
    """Advance past whitespace and item-separator commas."""
    while idx < len(buf) and buf[idx : idx + 1] in (b" ", b"\t", b"\n", b"\r", b","):
        idx += 1
    return idx


def _extract_id(slice_bytes: bytes, id_key_bytes: bytes, id_key: str) -> str:
    """Parse ``slice_bytes`` with stdlib json and read ``id_key``.

    ``id_key_bytes`` is unused here but kept so future tuning can do a
    fast byte-level prefilter before falling back to json.loads.
    """
    del id_key_bytes
    try:
        obj = json.loads(slice_bytes)
    except json.JSONDecodeError as exc:
        raise ScannerError(f"item slice failed to parse as JSON: {exc}") from exc
    if id_key not in obj:
        raise ScannerError(f"item missing required key {id_key!r}")
    value = obj[id_key]
    if not isinstance(value, str):
        raise ScannerError(f"item {id_key!r} is not a string: {value!r}")
    return value
