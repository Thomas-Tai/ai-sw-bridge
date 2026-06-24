"""W68 offline tests — ``curve_through_xyz`` handler (Mode-B, UNFIRED/dormant).

Curve through XYZ points — a reference curve defined by a sequence of absolute
3-D coordinates (the 4th curve type, sibling to shipped composite / helix /
project_curve — W62).

Mode-B is the operative path: ``InsertCurveFileBegin()`` → N ×
``InsertCurveFilePoint(x_m, y_m, z_m)`` → ``InsertCurveFileEnd()``.
No Mode-A exists (no ``CreateDefinition`` route for free-form curves in
the SW2024 swconst harvest).

These tests pin:
  * the recipe (Mode-B pipeline method + mm→m conversion),
  * the verify gate (feature-node count delta + CURVE geometric gate),
  * fail-closed validation (≥ 2 points, each 3-number list),
  * never-raise guarantee,
  * SPIKE_STATUS == "UNFIRED" (dormant — NOT in HANDLER_REGISTRY).

COM seams are patched on the lane module itself (``features.curve_through_xyz``)
per the registry lane protocol.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features import curve_through_xyz
from ai_sw_bridge.features.curve_through_xyz import create_curve_through_xyz


@pytest.fixture(autouse=True)
def _mock_curve_length(monkeypatch):
    """Offline, the COM-heavy arc-length read (typed IReferenceCurve.GetSegments
    → ICurve.GetLength) is mocked to a positive default — the geometric CURVE
    gate (W67 P3b) is exercised explicitly in TestCurveGate."""
    monkeypatch.setattr(curve_through_xyz, "_curve_length_mm", lambda node: 50.0)


# ---------------------------------------------------------------------------
# Fake COM objects
# ---------------------------------------------------------------------------


class _FakeDoc:
    def __init__(
        self,
        *,
        point_result=True,
        end_result=True,
        raise_clear=False,
        raise_begin=False,
        raise_point=False,
        raise_end=False,
        effect=True,
    ):
        self._point_result = point_result
        self._end_result = end_result
        self._raise_clear = raise_clear
        self._raise_begin = raise_begin
        self._raise_point = raise_point
        self._raise_end = raise_end
        self._effect = effect
        self.cleared = False
        self.rebuilt = False
        self.begin_called = False
        self.point_calls: list[tuple] = []
        self.end_called = False
        self._curve_count = 0

    def ClearSelection2(self, flag):
        if self._raise_clear:
            raise RuntimeError("ClearSelection2 boom")
        self.cleared = True

    def InsertCurveFileBegin(self):
        if self._raise_begin:
            raise RuntimeError("Begin boom")
        self.begin_called = True

    def InsertCurveFilePoint(self, x, y, z):
        if self._raise_point:
            raise RuntimeError("Point boom")
        self.point_calls.append((x, y, z))
        return self._point_result

    def InsertCurveFileEnd(self):
        if self._raise_end:
            raise RuntimeError("End boom")
        self.end_called = True
        if self._effect:
            self._curve_count += 1
        return self._end_result

    def ForceRebuild3(self, flag):
        self.rebuilt = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PTS_3 = [[-50.0, 0.0, 50.0], [0.0, 30.0, 50.0], [50.0, 0.0, 50.0]]
_PTS_2 = [[-50.0, 0.0, 50.0], [50.0, 0.0, 50.0]]


def _wire(monkeypatch, *, nodes_before=3, nodes_after=4):
    """Patch _count_feature_nodes on the lane module."""
    call_count = [0]

    def fake_count(doc):
        call_count[0] += 1
        if call_count[0] <= 1:
            return nodes_before
        return nodes_after

    monkeypatch.setattr(curve_through_xyz, "_count_feature_nodes", fake_count)


# ---------------------------------------------------------------------------
# Mode-B operative path
# ---------------------------------------------------------------------------


class TestModeB:
    def test_green_path_3_points(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, note = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is True, note
        assert "Mode-B" in note
        assert doc.cleared is True
        assert doc.begin_called is True
        assert doc.end_called is True
        assert doc.rebuilt is True
        assert len(doc.point_calls) == 3

    def test_green_path_2_points(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_curve_through_xyz(doc, {}, {"points": _PTS_2})
        assert ok is True
        assert len(doc.point_calls) == 2

    def test_unit_conversion_mm_to_m(self, monkeypatch):
        """Points are provided in mm; the handler converts to metres for SW."""
        _wire(monkeypatch)
        doc = _FakeDoc()
        ok, _ = create_curve_through_xyz(
            doc,
            {},
            {"points": [[100.0, 200.0, 300.0], [400.0, 500.0, 600.0]]},
        )
        assert ok is True
        assert doc.point_calls[0] == pytest.approx((0.1, 0.2, 0.3))
        assert doc.point_calls[1] == pytest.approx((0.4, 0.5, 0.6))

    def test_point_returns_false_short_circuits(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(point_result=False)
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is False
        assert "Mode-B" in err

    def test_end_returns_false_is_failure(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(end_result=False)
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is False
        assert "Mode-B" in err

    def test_begin_raises_returns_false(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(raise_begin=True)
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is False

    def test_point_raises_returns_false(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(raise_point=True)
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is False

    def test_end_raises_returns_false(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(raise_end=True)
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is False

    def test_clear_selection_raise_handled(self, monkeypatch):
        _wire(monkeypatch)
        doc = _FakeDoc(raise_clear=True)
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is False


# ---------------------------------------------------------------------------
# Verify gate (ghost trap)
# ---------------------------------------------------------------------------


class TestVerifyGate:
    def test_no_new_node_is_ghost(self, monkeypatch):
        """Mode-B pipeline succeeds but no feature node materialized → ghost."""
        _wire(monkeypatch, nodes_before=3, nodes_after=3)
        doc = _FakeDoc()
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is False
        assert "no feature node materialized" in err

    def test_new_node_passes_verify(self, monkeypatch):
        _wire(monkeypatch, nodes_before=3, nodes_after=4)
        doc = _FakeDoc()
        ok, _ = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is True


# ---------------------------------------------------------------------------
# Validation (fail-closed)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_points_rejected(self):
        ok, err = create_curve_through_xyz(_FakeDoc(), {}, {})
        assert ok is False and "points" in err

    def test_one_point_rejected(self):
        ok, err = create_curve_through_xyz(
            _FakeDoc(),
            {},
            {"points": [[1, 2, 3]]},
        )
        assert ok is False and "points" in err

    def test_empty_points_rejected(self):
        ok, err = create_curve_through_xyz(_FakeDoc(), {}, {"points": []})
        assert ok is False and "points" in err

    def test_non_list_points_rejected(self):
        ok, err = create_curve_through_xyz(
            _FakeDoc(),
            {},
            {"points": "not_a_list"},
        )
        assert ok is False and "points" in err

    def test_point_wrong_length_rejected(self):
        ok, err = create_curve_through_xyz(
            _FakeDoc(),
            {},
            {"points": [[1, 2], [3, 4, 5]]},
        )
        assert ok is False and "point[0]" in err

    def test_point_non_numeric_rejected(self):
        ok, err = create_curve_through_xyz(
            _FakeDoc(),
            {},
            {"points": [["a", 2, 3], [4, 5, 6]]},
        )
        assert ok is False and "point[0]" in err

    def test_feature_not_dict_rejected(self):
        ok, err = create_curve_through_xyz(
            _FakeDoc(),
            "not_a_dict",
            {"points": _PTS_2},
        )
        assert ok is False and "feature must be a dict" in err

    def test_target_not_dict_rejected(self):
        ok, err = create_curve_through_xyz(
            _FakeDoc(),
            {},
            "not_a_dict",
        )
        assert ok is False and "target must be a dict" in err

    def test_never_raises_on_none_inputs(self):
        for _ in range(5):
            ok, err = create_curve_through_xyz(None, None, None)  # type: ignore[arg-type]
            assert ok is False


# ---------------------------------------------------------------------------
# CURVE geometric gate (W67 P3b)
# ---------------------------------------------------------------------------


class TestCurveGate:
    def test_node_without_arc_length_is_rejected(self, monkeypatch):
        """A curve node materialized but with NO readable arc length is the W42
        geometric ghost — the hard gate_curve must reject it."""
        monkeypatch.setattr(curve_through_xyz, "_curve_length_mm", lambda node: None)
        _wire(monkeypatch, nodes_before=3, nodes_after=4)
        doc = _FakeDoc()
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is False
        assert "arc length" in err

    def test_node_with_arc_length_passes(self, monkeypatch):
        monkeypatch.setattr(curve_through_xyz, "_curve_length_mm", lambda node: 120.0)
        _wire(monkeypatch, nodes_before=3, nodes_after=4)
        doc = _FakeDoc()
        ok, err = create_curve_through_xyz(doc, {}, {"points": _PTS_3})
        assert ok is True, err


# ---------------------------------------------------------------------------
# Dormant gate + kind disjointness
# ---------------------------------------------------------------------------


class TestDormantGate:
    def test_spike_status_is_green(self):
        # seat-proven 2026-06-21 (CurveInFile node, arc 119mm, survives reopen)
        assert curve_through_xyz.SPIKE_STATUS == "GREEN"

    def test_curve_through_xyz_registered(self):
        """GREEN lane is advertised in HANDLER_REGISTRY."""
        assert "curve_through_xyz" in HANDLER_REGISTRY
        assert HANDLER_REGISTRY["curve_through_xyz"] is create_curve_through_xyz


class TestKindNames:
    def test_curve_through_xyz_disjoint_from_builtin_types(self):
        builtin_kinds = {
            "fillet_constant_radius",
            "base_flange",
            "variable_radius_fillet",
            "wizard_hole",
            "shell",
            "draft",
            "sweep",
            "ref_plane",
            "ref_axis",
            "coordinate_system",
            "ref_point",
            "dome",
            "sweep_cut",
        }
        assert "curve_through_xyz" not in builtin_kinds

    def test_curve_through_xyz_disjoint_from_shipped_curves(self):
        shipped_curves = {"composite", "helix", "project_curve"}
        assert "curve_through_xyz" not in shipped_curves
