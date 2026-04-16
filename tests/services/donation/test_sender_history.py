"""Tests for the history-writing side effect of send_donation."""

import json
from datetime import datetime, timezone

from vibelens.services.donation import SENDER_INDEX_FILENAME
from vibelens.services.donation.history import hash_token
from vibelens.services.donation.sender import _append_history_entry


def test_append_history_entry_writes_expected_fields(tmp_path, monkeypatch):
    """_append_history_entry writes a single JSONL line with the correct shape."""
    donation_dir = tmp_path / "donations"
    monkeypatch.setattr(
        "vibelens.services.donation.sender.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": donation_dir})()})(),
    )
    _append_history_entry(
        donation_id="20260416154211_3b4d",
        session_count=2,
        session_token="browser-1",
    )

    path = donation_dir / SENDER_INDEX_FILENAME
    print(f"exists = {path.exists()}, content = {path.read_text()!r}")
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["donation_id"] == "20260416154211_3b4d"
    assert entry["session_count"] == 2
    assert entry["session_token_hash"] == hash_token("browser-1")
    parsed_at = datetime.fromisoformat(entry["donated_at"])
    assert parsed_at.tzinfo is not None
    assert parsed_at <= datetime.now(timezone.utc)


def test_append_history_entry_skips_when_token_missing(tmp_path, monkeypatch):
    """Missing session_token → no file written."""
    donation_dir = tmp_path / "donations"
    monkeypatch.setattr(
        "vibelens.services.donation.sender.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": donation_dir})()})(),
    )
    _append_history_entry(
        donation_id="20260416154211_3b4d",
        session_count=1,
        session_token=None,
    )
    _append_history_entry(
        donation_id="20260416154211_5e6f",
        session_count=1,
        session_token="",
    )
    path = donation_dir / SENDER_INDEX_FILENAME
    print(f"exists = {path.exists()}")
    assert not path.exists()


def test_append_history_entry_swallows_errors(tmp_path, monkeypatch, caplog):
    """Write failures are logged but don't raise."""
    bad_dir = tmp_path / "ro"
    bad_dir.mkdir()
    fake_dir = bad_dir / "missing" / "nested"
    monkeypatch.setattr(
        "vibelens.services.donation.sender.get_settings",
        lambda: type("S", (), {"donation": type("D", (), {"dir": fake_dir})()})(),
    )

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("vibelens.services.donation.sender.locked_jsonl_append", boom)

    # Should not raise
    _append_history_entry(
        donation_id="d1",
        session_count=1,
        session_token="tok",
    )
    print("call returned without raising")
