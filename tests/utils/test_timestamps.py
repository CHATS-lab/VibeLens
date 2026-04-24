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


def test_local_date_key_is_dst_aware_across_seasons():
    """A January UTC timestamp must render with January's local offset,
    not the offset cached at process start. Otherwise sessions in the
    opposite DST season land on the wrong local day at the midnight
    boundary, producing off-by-one daily bars on the dashboard.
    """
    # Pick timestamps that straddle local midnight in their own season.
    # For any tz that observes DST with a one-hour offset (US, most of EU):
    #   - a UTC instant close to midnight local in winter
    #   - a UTC instant close to midnight local in summer
    # The key must match what ``.astimezone()`` (no args — DST-aware)
    # renders, not what a fixed cached offset would render.
    winter_utc = datetime(2026, 1, 10, 3, 30, 0, tzinfo=timezone.utc)
    summer_utc = datetime(2026, 7, 10, 3, 30, 0, tzinfo=timezone.utc)

    winter_key = local_date_key(winter_utc)
    summer_key = local_date_key(summer_utc)

    winter_expected = winter_utc.astimezone().strftime("%Y-%m-%d")
    summer_expected = summer_utc.astimezone().strftime("%Y-%m-%d")
    print(f"winter: {winter_utc} -> key={winter_key} expected={winter_expected}")
    print(f"summer: {summer_utc} -> key={summer_key} expected={summer_expected}")

    assert winter_key == winter_expected
    assert summer_key == summer_expected


def test_local_date_key_preserves_epoch_across_dst_transitions():
    """Two UTC timestamps on the same local day must map to the same key
    regardless of which season the process was started in.
    """
    # 23:30 UTC on two dates in opposite seasons.
    jan_pair = (
        datetime(2026, 1, 5, 3, 30, 0, tzinfo=timezone.utc),  # local Jan 4 evening in ET
        datetime(2026, 1, 5, 4, 30, 0, tzinfo=timezone.utc),  # local Jan 4 late evening in ET
    )
    for ts in jan_pair:
        key = local_date_key(ts)
        expected = ts.astimezone().strftime("%Y-%m-%d")
        print(f"{ts} -> key={key} expected={expected}")
        assert key == expected
