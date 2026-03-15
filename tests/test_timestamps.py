"""Tests for vibelens.utils.timestamps — timestamp parsing and validation."""

from datetime import UTC, datetime

from vibelens.utils.timestamps import (
    MAX_VALID_EPOCH,
    MIN_VALID_EPOCH,
    normalize_timestamp,
    parse_iso_timestamp,
    parse_ms_timestamp,
    safe_int,
)


# ─── parse_ms_timestamp
class TestParseMsTimestamp:
    def test_valid_ms_timestamp(self):
        dt = parse_ms_timestamp(1700000000000)
        assert dt is not None
        assert dt.tzinfo == UTC
        print(f"  parsed: {dt.isoformat()}")

    def test_none_returns_none(self):
        assert parse_ms_timestamp(None) is None

    def test_string_ms_timestamp(self):
        dt = parse_ms_timestamp("1700000000000")
        assert dt is not None
        print(f"  parsed from string: {dt.isoformat()}")

    def test_zero_returns_none(self):
        """Epoch 0 is before MIN_VALID_EPOCH, so rejected."""
        assert parse_ms_timestamp(0) is None

    def test_negative_returns_none(self):
        assert parse_ms_timestamp(-1000) is None

    def test_infinity_returns_none(self):
        assert parse_ms_timestamp(float("inf")) is None

    def test_nan_returns_none(self):
        assert parse_ms_timestamp(float("nan")) is None

    def test_far_future_returns_none(self):
        """Year 5138 timestamp is out of range."""
        assert parse_ms_timestamp(99999999999999) is None

    def test_pre_2015_returns_none(self):
        """Timestamps before 2015 are rejected."""
        pre_2015_ms = 1400000000000  # ~2014
        assert parse_ms_timestamp(pre_2015_ms) is None

    def test_valid_2024_timestamp(self):
        ms_2024 = 1704067200000  # 2024-01-01T00:00:00Z
        dt = parse_ms_timestamp(ms_2024)
        assert dt is not None
        assert dt.year == 2024

    def test_overflow_returns_none(self):
        assert parse_ms_timestamp(10**30) is None


# ─── parse_iso_timestamp
class TestParseIsoTimestamp:
    def test_valid_iso(self):
        dt = parse_iso_timestamp("2024-06-15T10:30:00+00:00")
        assert dt is not None
        assert dt.year == 2024

    def test_naive_gets_utc(self):
        dt = parse_iso_timestamp("2024-06-15T10:30:00")
        assert dt is not None
        assert dt.tzinfo == UTC

    def test_none_returns_none(self):
        assert parse_iso_timestamp(None) is None

    def test_empty_returns_none(self):
        assert parse_iso_timestamp("") is None

    def test_invalid_format_returns_none(self):
        assert parse_iso_timestamp("not-a-date") is None

    def test_pre_2015_returns_none(self):
        assert parse_iso_timestamp("2010-01-01T00:00:00Z") is None

    def test_far_future_returns_none(self):
        assert parse_iso_timestamp("2040-01-01T00:00:00Z") is None


# ─── normalize_timestamp
class TestNormalizeTimestamp:
    def test_none(self):
        assert normalize_timestamp(None) is None

    def test_iso_string(self):
        dt = normalize_timestamp("2024-06-15T10:30:00Z")
        assert dt is not None
        assert dt.year == 2024

    def test_ms_epoch(self):
        """Large number treated as milliseconds."""
        dt = normalize_timestamp(1700000000000)
        assert dt is not None
        print(f"  ms epoch: {dt.isoformat()}")

    def test_s_epoch(self):
        """Smaller number treated as seconds."""
        dt = normalize_timestamp(1700000000)
        assert dt is not None
        print(f"  s epoch: {dt.isoformat()}")

    def test_float_inf_returns_none(self):
        assert normalize_timestamp(float("inf")) is None

    def test_float_neg_inf_returns_none(self):
        assert normalize_timestamp(float("-inf")) is None

    def test_float_nan_returns_none(self):
        assert normalize_timestamp(float("nan")) is None

    def test_negative_returns_none(self):
        assert normalize_timestamp(-100) is None

    def test_far_future_s_epoch_returns_none(self):
        far_future = MAX_VALID_EPOCH + 1_000_000
        assert normalize_timestamp(far_future) is None


# ─── safe_int
class TestSafeInt:
    def test_int(self):
        assert safe_int(42) == 42

    def test_float(self):
        assert safe_int(3.7) == 3

    def test_string_number(self):
        assert safe_int("100") == 100

    def test_none_returns_default(self):
        assert safe_int(None) == 0

    def test_none_with_custom_default(self):
        assert safe_int(None, default=-1) == -1

    def test_nan_returns_default(self):
        assert safe_int(float("nan")) == 0

    def test_inf_returns_default(self):
        assert safe_int(float("inf")) == 0

    def test_neg_inf_returns_default(self):
        assert safe_int(float("-inf")) == 0

    def test_non_numeric_string_returns_default(self):
        assert safe_int("abc") == 0

    def test_empty_string_returns_default(self):
        assert safe_int("") == 0

    def test_bool_true(self):
        assert safe_int(True) == 1

    def test_bool_false(self):
        assert safe_int(False) == 0


# ─── Range validation constants
class TestValidationConstants:
    def test_min_valid_epoch_is_2015(self):
        dt = datetime.fromtimestamp(MIN_VALID_EPOCH, tz=UTC)
        assert dt.year == 2015
        assert dt.month == 1
        assert dt.day == 1
        print(f"  MIN_VALID_EPOCH → {dt.isoformat()}")

    def test_max_valid_epoch_is_2035(self):
        dt = datetime.fromtimestamp(MAX_VALID_EPOCH, tz=UTC)
        assert dt.year == 2035
        print(f"  MAX_VALID_EPOCH → {dt.isoformat()}")

    def test_boundary_just_inside_min(self):
        dt = parse_ms_timestamp(MIN_VALID_EPOCH * 1000)
        assert dt is not None

    def test_boundary_just_inside_max(self):
        dt = parse_ms_timestamp(MAX_VALID_EPOCH * 1000)
        assert dt is not None

    def test_boundary_just_outside_min(self):
        dt = parse_ms_timestamp((MIN_VALID_EPOCH - 1) * 1000)
        assert dt is None

    def test_boundary_just_outside_max(self):
        dt = parse_ms_timestamp((MAX_VALID_EPOCH + 1) * 1000)
        assert dt is None
