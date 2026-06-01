"""Tests for Wave-5 feature_add handler stubs (F0, F1, F2–F6).

These tests validate the handler logic that will be wired into
mutate.py by W0.  The handlers are tested against fake COM objects;
the real CreateFeature paths are marked ``# SEAT-PENDING (W0)``
and are NOT exercised here.

Test structure mirrors ``test_mutate_feature_add.py``:
  - TestPropose<Feature>  — propose-validation rejects bad inputs
  - TestDryRun<Feature>   — dry-run calls the right COM methods
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge import mutate
from ai_sw_bridge.mutate import sw_propose_feature_add


# ---------------------------------------------------------------------------
# F0 — Ref-geometry handlers (seat-proven by spike_refgeom, W3)
# ---------------------------------------------------------------------------


class _FakeRefGeomFm:
    """Fake FeatureManager for ref-geom creation."""

    def __init__(
        self,
        ref_plane_ret: Any = object(),
        ref_axis_ret: Any = object(),
        csys_ret: Any = object(),
        ref_point_ret: Any = object(),
    ) -> None:
        self.ref_plane_calls: list[tuple] = []
        self.ref_axis_calls: list[tuple] = []
        self.csys_calls: list[tuple] = []
        self.ref_point_calls: list[tuple] = []
        self._plane_ret = ref_plane_ret
        self._axis_ret = ref_axis_ret
        self._csys_ret = csys_ret
        self._point_ret = ref_point_ret

    def InsertRefPlane(self, c1: int, v1: Any, c2: int, v2: Any, c3: int, v3: Any) -> Any:
        self.ref_plane_calls.append((c1, v1, c2, v2, c3, v3))
        return self._plane_ret

    def InsertCoordinateSystem(self, flip_x: bool, flip_y: bool, flip_z: bool) -> Any:
        self.csys_calls.append((flip_x, flip_y, flip_z))
        return self._csys_ret

    def InsertReferencePoint(self, t: int, v1: int, v2: float, v3: int) -> Any:
        self.ref_point_calls.append((t, v1, v2, v3))
        return self._point_ret


class _FakeRefGeomDoc:
    """Fake IModelDoc2 for ref-geom."""

    def __init__(self, fm: _FakeRefGeomFm, axis_ret: Any = "axis_feature") -> None:
        self.FeatureManager = fm
        self.select_calls: list[tuple] = []
        self.clear_calls: list[bool] = []
        self._axis_ret = axis_ret

    def InsertAxis2(self, auto_size: bool) -> Any:
        return self._axis_ret

    def ClearSelection2(self, top: bool) -> None:
        self.clear_calls.append(top)

    def SelectByID(self, name: str, t: str, x: float, y: float, z: float) -> bool:
        self.select_calls.append((name, t, x, y, z))
        return True


class TestRefPlaneOffset:
    def test_creates_offset_plane(self) -> None:
        fm = _FakeRefGeomFm()
        doc = _FakeRefGeomDoc(fm)
        result = _create_ref_plane_offset(doc, "Front Plane", distance_m=0.05)
        assert result[0] is True
        assert len(fm.ref_plane_calls) == 1
        c1, v1, *_ = fm.ref_plane_calls[0]
        assert c1 == 8  # SW_REFPLANE_OFFSET bit-flag
        assert v1 == pytest.approx(0.05)

    def test_fails_when_insert_returns_none(self) -> None:
        fm = _FakeRefGeomFm(ref_plane_ret=None)
        doc = _FakeRefGeomDoc(fm)
        ok, err = _create_ref_plane_offset(doc, "Front Plane", distance_m=0.05)
        assert ok is False
        assert "did not materialize" in err


class TestRefAxisTwoPlanes:
    def test_creates_axis(self) -> None:
        fm = _FakeRefGeomFm()
        doc = _FakeRefGeomDoc(fm)
        ok, err = _create_ref_axis_two_planes(doc, "Front Plane", "Right Plane")
        assert ok is True
        assert len(doc.select_calls) == 2
        assert doc.select_calls[0] == ("Front Plane", "PLANE", 0, 0, 0)

    def test_fails_when_insert_returns_false(self) -> None:
        fm = _FakeRefGeomFm()
        doc = _FakeRefGeomDoc(fm, axis_ret=False)
        ok, err = _create_ref_axis_two_planes(doc, "Front Plane", "Right Plane")
        assert ok is False


class TestCoordinateSystem:
    def test_creates_csys(self) -> None:
        fm = _FakeRefGeomFm()
        doc = _FakeRefGeomDoc(fm)
        ok, err = _create_coordinate_system(doc)
        assert ok is True
        assert fm.csys_calls == [(False, False, False)]

    def test_fails_when_returns_none(self) -> None:
        fm = _FakeRefGeomFm(csys_ret=None)
        doc = _FakeRefGeomDoc(fm)
        ok, err = _create_coordinate_system(doc)
        assert ok is False


class TestRefPoint:
    def test_creates_point_at_vertex(self) -> None:
        fm = _FakeRefGeomFm()
        doc = _FakeRefGeomDoc(fm)
        ok, err = _create_ref_point_at_vertex(doc, x=0.01, y=0.01, z=0.01)
        assert ok is True
        assert len(fm.ref_point_calls) == 1


# ===========================================================================
# Handler function stubs (to be wired into mutate.py by W0)
# These are pure-Python, SW-free scaffolding — no COM calls.
# ===========================================================================


def _create_ref_plane_offset(
    doc: Any, plane_name: str, distance_m: float
) -> tuple[bool, str | None]:
    """Create an offset reference plane.  # SEAT-PENDING (W0)

    Seat-proven recipe (spike_refgeom, W3):
      fm.InsertRefPlane(8, distance_m, 0, 0, 0, 0)
      where 8 = swRefPlaneReferenceConstraint_Distance (bit-flag).
    """
    try:
        doc.ClearSelection2(True)
        doc.SelectByID(plane_name, "PLANE", 0, 0, 0)
        fm = doc.FeatureManager
        feat = fm.InsertRefPlane(8, distance_m, 0, 0, 0, 0)
        if feat is not None and not isinstance(feat, int):
            return True, None
        return False, "InsertRefPlane did not materialize"
    except Exception as exc:
        return False, f"ref-plane pipeline failed: {exc!r}"


def _create_ref_axis_two_planes(
    doc: Any, plane1: str, plane2: str
) -> tuple[bool, str | None]:
    """Create a reference axis from two-plane intersection.  # SEAT-PENDING (W0)

    Seat-proven recipe (spike_refgeom, W3):
      Select plane1, append-select plane2, then doc.InsertAxis2(True).
      InsertAxis2 is on IModelDoc2, NOT IFeatureManager.
    """
    try:
        doc.ClearSelection2(True)
        doc.SelectByID(plane1, "PLANE", 0, 0, 0)
        doc.SelectByID(plane2, "PLANE", 0, 0, 0)
        feat = doc.InsertAxis2(True)
        if feat is not None and feat is not False and not isinstance(feat, int):
            return True, None
        return False, "InsertAxis2 did not materialize"
    except Exception as exc:
        return False, f"ref-axis pipeline failed: {exc!r}"


def _create_coordinate_system(
    doc: Any,
    flip_x: bool = False,
    flip_y: bool = False,
    flip_z: bool = False,
) -> tuple[bool, str | None]:
    """Create a coordinate system.  # SEAT-PENDING (W0)

    Seat-proven recipe (spike_refgeom, W3):
      fm.InsertCoordinateSystem(flip_x, flip_y, flip_z).
    """
    try:
        doc.ClearSelection2(True)
        fm = doc.FeatureManager
        feat = fm.InsertCoordinateSystem(flip_x, flip_y, flip_z)
        if feat is not None and not isinstance(feat, int):
            return True, None
        return False, "InsertCoordinateSystem did not materialize"
    except Exception as exc:
        return False, f"coordinate-system pipeline failed: {exc!r}"


def _create_ref_point_at_vertex(
    doc: Any, x: float, y: float, z: float
) -> tuple[bool, str | None]:
    """Create a reference point at a vertex.  # SEAT-PENDING (W0)

    Seat-proven recipe (spike_refgeom, W3):
      Select vertex, then fm.InsertReferencePoint(5, 0, 0.0, 1).
    """
    try:
        doc.ClearSelection2(True)
        doc.SelectByID("", "VERTEX", x, y, z)
        fm = doc.FeatureManager
        feat = fm.InsertReferencePoint(5, 0, 0.0, 1)
        if feat is not None and not isinstance(feat, int):
            return True, None
        return False, "InsertReferencePoint did not materialize"
    except Exception as exc:
        return False, f"ref-point pipeline failed: {exc!r}"


class _FakeWave5Doc:
    """Minimal fake doc for propose-validation (no COM calls needed)."""

    def __init__(self, path: str) -> None:
        self._path = path

    def GetPathName(self) -> str:
        return self._path

    def GetTitle(self) -> str:
        return Path(self._path).name


def _patch_propose(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, doc: Any) -> None:
    """Monkeypatch mutate.py for propose-only tests (no dry-run/COM)."""

    class _FakeSw:
        def OpenDoc6(self, path, *a: Any) -> tuple:
            return (doc, 0, 0)

    monkeypatch.setattr(mutate, "_proposals_dir", lambda: tmp_path / "proposals")
    monkeypatch.setattr(mutate, "get_sw_app", lambda: _FakeSw())
    monkeypatch.setattr(mutate, "wrapper_module", lambda: object())
    monkeypatch.setattr(mutate, "typed", lambda obj, iface, **kw: obj)
    monkeypatch.setattr(mutate, "typed_qi", lambda obj, iface, **kw: obj)


class TestProposeRefPlane:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_plane", "distance_mm": 50.0},
            {"plane": "Front Plane"},
        )
        assert r["ok"] is True

    def test_rejects_missing_plane(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_plane", "distance_mm": 50.0},
            {"other_key": "value"},
        )
        assert r["ok"] is False and "plane" in r["error"]

    def test_rejects_bad_distance(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_plane", "distance_mm": -1},
            {"plane": "Front Plane"},
        )
        assert r["ok"] is False and "distance_mm" in r["error"]


class TestProposeRefAxis:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_axis"},
            {"planes": ["Front Plane", "Right Plane"]},
        )
        assert r["ok"] is True

    def test_rejects_wrong_count(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_axis"},
            {"planes": ["Front Plane"]},
        )
        assert r["ok"] is False and "planes" in r["error"]


class TestProposeCoordinateSystem:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "coordinate_system"},
            {"origin": [0, 0, 0]},
        )
        assert r["ok"] is True


class TestProposeRefPoint:
    def test_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_point"},
            {"point": [0.01, 0.01, 0.01]},
        )
        assert r["ok"] is True

    def test_rejects_bad_point(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        doc_file = tmp_path / "t.sldprt"
        doc_file.touch()
        _patch_propose(monkeypatch, tmp_path, _FakeWave5Doc(str(doc_file)))
        r = sw_propose_feature_add(
            str(doc_file),
            {"type": "ref_point"},
            {"point": [0.01, 0.01]},
        )
        assert r["ok"] is False and "point" in r["error"]


