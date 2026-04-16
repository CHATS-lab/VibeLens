"""Tests for vibelens.services.donation.history — per-token filtering, ordering."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from vibelens.services.donation import SENDER_INDEX_FILENAME
from vibelens.services.donation.history import hash_token, list_for_token


def _write_entry(
    path: Path, donation_id: str, session_count: int, donated_at: datetime, token: str
) -> None:
    """Write one JSONL entry matching the sender's schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "donation_id": donation_id,
        "session_count": session_count,
        "donated_at": donated_at.isoformat(),
        "session_token_hash": hash_token(token),
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def test_hash_token_is_sha256_hex():
    """hash_token returns a 64-char sha256 hex digest."""
    digest = hash_token("abc")
    expected = hashlib.sha256(b"abc").hexdigest()
    print(f"digest = {digest}")
    assert digest == expected
    assert len(digest) == 64


def test_list_for_token_returns_newest_first(tmp_path, monkeypatch):
    """list_for_token orders entries by donated_at descending."""
    donation_dir = tmp_path / "donations"
    monkeypatch.setattr(
        "vibelens.services.donation.history.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": donation_dir})()})(),
    )
    path = donation_dir / SENDER_INDEX_FILENAME
    token = "tok-A"
    _write_entry(path, "d1", 1, datetime(2026, 1, 1, tzinfo=timezone.utc), token)
    _write_entry(path, "d2", 2, datetime(2026, 2, 1, tzinfo=timezone.utc), token)
    _write_entry(path, "d3", 3, datetime(2026, 3, 1, tzinfo=timezone.utc), token)

    entries = list_for_token(token)
    print(f"entries = {[(e.donation_id, e.donated_at) for e in entries]}")
    assert [e.donation_id for e in entries] == ["d3", "d2", "d1"]


def test_list_for_token_filters_by_token_hash(tmp_path, monkeypatch):
    """Entries written by token B are invisible to token A."""
    donation_dir = tmp_path / "donations"
    monkeypatch.setattr(
        "vibelens.services.donation.history.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": donation_dir})()})(),
    )
    path = donation_dir / SENDER_INDEX_FILENAME
    _write_entry(path, "a1", 1, datetime(2026, 1, 1, tzinfo=timezone.utc), "token-A")
    _write_entry(path, "b1", 1, datetime(2026, 1, 2, tzinfo=timezone.utc), "token-B")

    a_entries = list_for_token("token-A")
    b_entries = list_for_token("token-B")
    print(f"a_entries = {[e.donation_id for e in a_entries]}")
    print(f"b_entries = {[e.donation_id for e in b_entries]}")
    assert [e.donation_id for e in a_entries] == ["a1"]
    assert [e.donation_id for e in b_entries] == ["b1"]


def test_list_for_token_skips_malformed_lines(tmp_path, monkeypatch):
    """Corrupt lines are skipped, valid ones still returned."""
    donation_dir = tmp_path / "donations"
    monkeypatch.setattr(
        "vibelens.services.donation.history.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": donation_dir})()})(),
    )
    path = donation_dir / SENDER_INDEX_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_entry(path, "d1", 1, datetime(2026, 1, 1, tzinfo=timezone.utc), "tok")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("not-json\n")
        fh.write('{"incomplete": true\n')
    _write_entry(path, "d2", 2, datetime(2026, 2, 1, tzinfo=timezone.utc), "tok")

    entries = list_for_token("tok")
    print(f"entries = {[e.donation_id for e in entries]}")
    assert [e.donation_id for e in entries] == ["d2", "d1"]


def test_list_for_token_missing_file_returns_empty(tmp_path, monkeypatch):
    """No sent.jsonl → empty list, no error."""
    donation_dir = tmp_path / "donations"
    monkeypatch.setattr(
        "vibelens.services.donation.history.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": donation_dir})()})(),
    )
    entries = list_for_token("any-token")
    print(f"entries = {entries}")
    assert entries == []


def test_list_for_token_empty_token_returns_empty(tmp_path, monkeypatch):
    """Empty/None token never matches any entry."""
    donation_dir = tmp_path / "donations"
    monkeypatch.setattr(
        "vibelens.services.donation.history.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": donation_dir})()})(),
    )
    path = donation_dir / SENDER_INDEX_FILENAME
    _write_entry(path, "d1", 1, datetime(2026, 1, 1, tzinfo=timezone.utc), "")
    _write_entry(path, "d2", 1, datetime(2026, 1, 2, tzinfo=timezone.utc), "real-token")

    print(f"empty_str = {list_for_token('')}")
    print(f"none = {list_for_token(None)}")
    assert list_for_token("") == []
    assert list_for_token(None) == []


def test_list_for_token_respects_limit(tmp_path, monkeypatch):
    """limit caps the number of entries returned."""
    donation_dir = tmp_path / "donations"
    monkeypatch.setattr(
        "vibelens.services.donation.history.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": donation_dir})()})(),
    )
    path = donation_dir / SENDER_INDEX_FILENAME
    for i in range(5):
        _write_entry(
            path,
            f"d{i}",
            1,
            datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            "tok",
        )
    entries = list_for_token("tok", limit=3)
    print(f"entries = {[e.donation_id for e in entries]}")
    assert len(entries) == 3
    assert [e.donation_id for e in entries] == ["d4", "d3", "d2"]
