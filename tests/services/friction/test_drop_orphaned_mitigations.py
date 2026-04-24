"""Tests for friction's ``_drop_orphaned_mitigations`` helper.

Drops mitigations whose addressed friction types were all dropped when the
friction_types list was capped upstream.
"""

from vibelens.models.friction.models import Mitigation
from vibelens.services.friction.analysis import _drop_orphaned_mitigations


def _mitigation(title: str, addressed: list[str]) -> Mitigation:
    return Mitigation(
        title=title,
        addressed_friction_types=addressed,
        action="do a thing",
        rationale="one line.\n- bullet",
        confidence=0.5,
    )


class TestDropOrphanedMitigations:
    """Remove mitigations whose addressed friction types are all gone."""

    def test_all_retained(self) -> None:
        mits = [
            _mitigation("fix A", ["type-a"]),
            _mitigation("fix B", ["type-b"]),
        ]
        dropped = _drop_orphaned_mitigations(mits, {"type-a", "type-b"})
        assert dropped == 0
        assert len(mits) == 2

    def test_all_dropped(self) -> None:
        mits = [
            _mitigation("fix gone", ["removed-type"]),
            _mitigation("also gone", ["another-removed"]),
        ]
        dropped = _drop_orphaned_mitigations(mits, {"still-here"})
        assert dropped == 2
        assert mits == []

    def test_partial_drop(self) -> None:
        mits = [
            _mitigation("keep me", ["type-a"]),
            _mitigation("drop me", ["ghost"]),
            _mitigation("also keep", ["type-b"]),
        ]
        dropped = _drop_orphaned_mitigations(mits, {"type-a", "type-b"})
        assert dropped == 1
        assert [m.title for m in mits] == ["keep me", "also keep"]

    def test_multi_ref_mitigation_kept_if_any_ref_retained(self) -> None:
        mits = [_mitigation("keep", ["type-a", "ghost", "another-ghost"])]
        dropped = _drop_orphaned_mitigations(mits, {"type-a"})
        assert dropped == 0
        assert len(mits) == 1
        # addressed_friction_types filtered to only retained names.
        assert mits[0].addressed_friction_types == ["type-a"]

    def test_filters_addressed_types_to_retained(self) -> None:
        mits = [_mitigation("keep", ["type-a", "ghost"])]
        _drop_orphaned_mitigations(mits, {"type-a"})
        assert mits[0].addressed_friction_types == ["type-a"]

    def test_empty_retained_set_drops_all(self) -> None:
        mits = [_mitigation("x", ["any"])]
        dropped = _drop_orphaned_mitigations(mits, set())
        assert dropped == 1
        assert mits == []

    def test_mutates_in_place(self) -> None:
        mits = [_mitigation("a", ["ghost"])]
        original_id = id(mits)
        _drop_orphaned_mitigations(mits, set())
        assert id(mits) == original_id
