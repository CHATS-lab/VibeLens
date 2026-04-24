"""Tests for ``utils.collections.truncate_to_cap`` — generic in-place list truncation."""

import pytest

from vibelens.models.session.patterns import WorkflowPattern
from vibelens.models.step_ref import StepRef
from vibelens.utils.collections import truncate_to_cap


def _make_ref(idx: int) -> StepRef:
    """Produce a StepRef with a distinct session_id / step IDs for ordering checks."""
    return StepRef(
        session_id=f"session-{idx:04d}",
        start_step_id=f"step-{idx:04d}",
        end_step_id=f"step-{idx:04d}",
    )


def _pattern(ref_count: int, title: str = "test-pattern") -> WorkflowPattern:
    return WorkflowPattern(
        title=title,
        description="desc",
        example_refs=[_make_ref(i) for i in range(ref_count)],
    )


class TestCapValidation:
    """cap must be positive."""

    def test_cap_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="cap must be positive"):
            truncate_to_cap([1, 2, 3], 0)

    def test_cap_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="cap must be positive"):
            truncate_to_cap([1, 2, 3], -5)


class TestTruncateToCap:
    """Core truncation behavior."""

    def test_empty_list_noop(self) -> None:
        items: list[int] = []
        truncate_to_cap(items, 3)
        assert items == []

    def test_under_cap_unchanged(self) -> None:
        items = [1, 2]
        truncate_to_cap(items, 5)
        assert items == [1, 2]

    def test_at_cap_unchanged(self) -> None:
        items = [1, 2, 3]
        truncate_to_cap(items, 3)
        assert items == [1, 2, 3]

    def test_over_cap_truncates_keeping_first(self) -> None:
        items = [1, 2, 3, 4, 5, 6, 7]
        truncate_to_cap(items, 3)
        assert items == [1, 2, 3]

    def test_mutates_in_place(self) -> None:
        items = [10, 20, 30, 40]
        original_id = id(items)
        truncate_to_cap(items, 2)
        assert id(items) == original_id
        assert items == [10, 20]

    def test_works_on_model_lists(self) -> None:
        patterns = [_pattern(0, title=f"p{i}") for i in range(5)]
        truncate_to_cap(patterns, 2)
        assert len(patterns) == 2
        assert patterns[0].title == "p0"
        assert patterns[1].title == "p1"

    def test_per_item_field_truncation(self) -> None:
        """truncate_to_cap on item.example_refs is the inlined cap_example_refs pattern."""
        pattern = _pattern(7)
        truncate_to_cap(pattern.example_refs, 3)
        assert [r.session_id for r in pattern.example_refs] == [
            "session-0000",
            "session-0001",
            "session-0002",
        ]
