"""Tests for local_tz() and local_date_key() helpers."""

from datetime import datetime, timezone

import vibelens.utils.timestamps as ts_mod
from vibelens.utils.timestamps import local_date_key, local_tz


def test_local_tz_returns_same_object(monkeypatch):
    """Two calls return the same cached tzinfo instance."""
    monkeypatch.setattr(ts_mod, "_cached_local_tz", None)

    first = local_tz()
    second = local_tz()

    assert first is second


def test_local_tz_is_not_none(monkeypatch):
    monkeypatch.setattr(ts_mod, "_cached_local_tz", None)

    assert local_tz() is not None


def test_local_date_key_formats_yyyy_mm_dd():
    utc_noon = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)

    key = local_date_key(utc_noon)

    assert len(key) == 10
    assert key[4] == "-"
    assert key[7] == "-"
    year, month, day = key.split("-")
    assert year == "2026"
    assert 1 <= int(month) <= 12
    assert 1 <= int(day) <= 31


def test_local_date_key_respects_local_tz():
    """The date key reflects the local-tz rendering of the timestamp."""
    utc_ts = datetime(2026, 4, 18, 23, 30, 0, tzinfo=timezone.utc)

    key = local_date_key(utc_ts)
    expected = utc_ts.astimezone(local_tz()).strftime("%Y-%m-%d")

    assert key == expected
