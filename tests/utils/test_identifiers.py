"""Tests for the shared timestamped-id generator."""

import re
import time

from vibelens.utils.identifiers import generate_timestamped_id

ID_PATTERN = re.compile(r"^\d{8}T\d{6}-[A-Za-z0-9_-]{8}$")


def test_generate_timestamped_id_format() -> None:
    """ID shape is ``YYYYMMDDTHHMMSS-{8 url-safe chars}``."""
    generated = generate_timestamped_id()
    print(f"generated id: {generated}")
    assert ID_PATTERN.match(generated), f"id {generated!r} does not match expected format"


def test_generate_timestamped_id_is_sortable() -> None:
    """Sequential IDs sort lexicographically in chronological order."""
    ids: list[str] = []
    for _ in range(3):
        ids.append(generate_timestamped_id())
        # Sleep past a whole second so the timestamp prefix advances.
        time.sleep(1.01)
    print(f"sequential ids: {ids}")
    assert ids == sorted(ids), "lexicographic sort must match generation order"
