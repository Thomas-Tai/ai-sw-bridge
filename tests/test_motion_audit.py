"""W49 Motion Audit — offline proof of the pure envelope/units logic.

No SOLIDWORKS. Covers the kinematic-unit conversion, position sampling, and the
collision-envelope summarizer (collision_free / first_collision / clear_ranges /
tightest_clearance). The COM drive + sweep are seat-proven separately
(spikes/v0_2x/kinematic_motion_derisk + kinematic_angle_confirm + the PAE).
"""
from __future__ import annotations

import math

import pytest

from ai_sw_bridge.motion_audit import (
    _from_si,
    _positions,
    _to_si,
    choose_clearance_pair,
    summarize_motion,
)


class TestUnits:
    def test_distance_mm_to_m(self) -> None:
        assert _to_si("distance", 50.0) == pytest.approx(0.050)

    def test_angle_deg_to_rad(self) -> None:
        assert _to_si("angle", 90.0) == pytest.approx(math.pi / 2)

    def test_roundtrip_distance(self) -> None:
        assert _from_si("distance", _to_si("distance", 12.5)) == pytest.approx(12.5)

    def test_roundtrip_angle(self) -> None:
        assert _from_si("angle", _to_si("angle", 33.0)) == pytest.approx(33.0)


class TestPositions:
    def test_linspace_endpoints_and_count(self) -> None:
        pos = _positions(0.0, 50.0, 6)
        assert len(pos) == 6
        assert pos[0] == 0.0
        assert pos[-1] == 50.0
        assert pos[1] == pytest.approx(10.0)

    def test_single_step_degenerates(self) -> None:
        assert _positions(5.0, 9.0, 1) == [5.0]


def _entry(pos: float, count: int, vol: float, clr: float | None) -> dict:
    return {
        "position": pos,
        "drive_route": "parameter",
        "interference_count": count,
        "interference_volume_mm3": vol,
        "min_clearance_mm": clr,
    }


class TestSummarizeMotion:
    def test_empty_profile_is_collision_free(self) -> None:
        s = summarize_motion([])
        assert s["collision_free"] is True
        assert s["first_collision_position"] is None
        assert s["clear_ranges"] == []

    def test_fully_clear_sweep(self) -> None:
        prof = [_entry(p, 0, 0.0, 5.0) for p in (0.0, 10.0, 20.0, 30.0)]
        s = summarize_motion(prof)
        assert s["collision_free"] is True
        assert s["first_collision_position"] is None
        assert s["clear_ranges"] == [[0.0, 30.0]]
        assert s["tightest_clearance_mm"] == pytest.approx(5.0)

    def test_collision_at_low_positions(self) -> None:
        # The distance-sweep shape: overlap shrinks to zero as distance grows.
        prof = [
            _entry(0.0, 1, 64000.0, None),
            _entry(10.0, 1, 48000.0, None),
            _entry(20.0, 1, 32000.0, None),
            _entry(30.0, 1, 16000.0, None),
            _entry(40.0, 0, 0.0, 0.0),
            _entry(50.0, 0, 0.0, 12.0),
        ]
        s = summarize_motion(prof)
        assert s["collision_free"] is False
        assert s["first_collision_position"] == 0.0
        assert s["colliding_positions"] == [0.0, 10.0, 20.0, 30.0]
        assert s["clear_ranges"] == [[40.0, 50.0]]
        assert s["max_interference_volume_mm3"] == pytest.approx(64000.0)

    def test_clear_then_collide_then_clear(self) -> None:
        # A mechanism that hits an obstacle mid-travel and emerges.
        prof = [
            _entry(0.0, 0, 0.0, 3.0),
            _entry(10.0, 0, 0.0, 1.0),
            _entry(20.0, 1, 500.0, None),
            _entry(30.0, 1, 800.0, None),
            _entry(40.0, 0, 0.0, 2.0),
        ]
        s = summarize_motion(prof)
        assert s["collision_free"] is False
        assert s["first_collision_position"] == 20.0
        assert s["clear_ranges"] == [[0.0, 10.0], [40.0, 40.0]]
        # tightest positive gap over the clear positions is 1.0 mm
        assert s["tightest_clearance_mm"] == pytest.approx(1.0)

    def test_touching_zero_clearance_excluded_from_tightest_positive(self) -> None:
        # A 0.0 (touching) clearance is not a positive gap; tightest uses >0 only.
        prof = [_entry(0.0, 0, 0.0, 0.0), _entry(10.0, 0, 0.0, 4.0)]
        s = summarize_motion(prof)
        assert s["tightest_clearance_mm"] == pytest.approx(4.0)

    def test_no_clearance_tracked(self) -> None:
        prof = [_entry(0.0, 0, 0.0, None), _entry(10.0, 0, 0.0, None)]
        s = summarize_motion(prof)
        assert s["tightest_clearance_mm"] is None
        assert s["collision_free"] is True


class TestChooseClearancePair:
    def test_empty_distances_returns_none(self) -> None:
        assert choose_clearance_pair(["a", "b"], {}) is None

    def test_single_pair(self) -> None:
        dists = {("a", "b"): 5.0}
        assert choose_clearance_pair(["a", "b"], dists) == ("a", "b")

    def test_picks_nearest(self) -> None:
        dists = {("a", "b"): 10.0, ("a", "c"): 2.0, ("b", "c"): 7.0}
        assert choose_clearance_pair(["a", "b", "c"], dists) == ("a", "c")

    def test_all_none_returns_none(self) -> None:
        dists = {("a", "b"): None, ("a", "c"): None}
        assert choose_clearance_pair(["a", "b", "c"], dists) is None

    def test_skips_none_picks_positive(self) -> None:
        dists = {("a", "b"): None, ("a", "c"): 3.0, ("b", "c"): 8.0}
        assert choose_clearance_pair(["a", "b", "c"], dists) == ("a", "c")

    def test_skips_negative(self) -> None:
        dists = {("a", "b"): -1.0, ("a", "c"): 4.0}
        assert choose_clearance_pair(["a", "b", "c"], dists) == ("a", "c")

    def test_zero_touching_selected(self) -> None:
        dists = {("a", "b"): 0.0, ("a", "c"): 5.0}
        assert choose_clearance_pair(["a", "b", "c"], dists) == ("a", "b")

    def test_all_negative_returns_none(self) -> None:
        dists = {("a", "b"): -1.0, ("a", "c"): -2.0}
        assert choose_clearance_pair(["a", "b", "c"], dists) is None

    def test_tie_returns_first(self) -> None:
        dists = {("a", "b"): 3.0, ("a", "c"): 3.0}
        result = choose_clearance_pair(["a", "b", "c"], dists)
        assert result == ("a", "b")
