"""Offline tests for the W45 DFM perception probes (observe.py).

Two read-only probes:
  - undercut detection  (sw_undercut_faces / _classify_undercut_faces)
  - min-wall-thickness  (sw_min_wall_thickness / _min_wall_from_samples)

Most of the testing targets the PURE shape-functions, which take plain
Python numbers and need NO SOLIDWORKS seat. We verify DISCRIMINATION (the
project doctrine: a function that "returns a number" is not proof -- it must
distinguish the discriminating cases): undercut-vs-clean and thin-vs-thick.

The wrapper tests follow test_observe_shape.py: without a running SW the
COM-acquisition functions return a typed error dict whose KEYS are the wire
contract. We also drive the wrappers through a tiny fake-face geometry stack
(FakeFace/FakeBody/FakeDoc) to exercise the COM glue end-to-end offline.
"""

from __future__ import annotations

import math

from ai_sw_bridge.observe import (
    _classify_undercut_faces,
    _measure_opposite_distance,
    _min_wall_from_samples,
    _vec_unit,
    _sw_min_wall_thickness_impl as sw_min_wall_thickness,
    _sw_undercut_faces_impl as sw_undercut_faces,
)


# ---------------------------------------------------------------------------
# Pure: _classify_undercut_faces  (undercut detection)
# ---------------------------------------------------------------------------

# Pull = +Y. A simple draftable boss: top (+Y) releasable, four side walls
# parallel to pull (side_wall), bottom (-Y) faces back toward the tool ->
# for a one-sided +Y pull the bottom is a back face (releasable by the other
# half) but along +Y its outward normal is opposite -> undercut for THIS pull.
_PULL_Y = (0.0, 1.0, 0.0)


def _face(index, normal, area_m2=1e-4):
    return {"index": index, "normal": normal, "area_m2": area_m2}


def test_undercut_clean_part_flags_none():
    """A part whose every face is releasable or a side wall along +Y must
    report undercut_count == 0 (the GREEN 'clean' criterion)."""
    faces = [
        _face(0, (0.0, 1.0, 0.0)),  # top: releasable
        _face(1, (1.0, 0.0, 0.0)),  # +x wall: side_wall
        _face(2, (-1.0, 0.0, 0.0)),  # -x wall: side_wall
        _face(3, (0.0, 0.0, 1.0)),  # +z wall: side_wall
        _face(4, (0.0, 0.0, -1.0)),  # -z wall: side_wall
    ]
    out = _classify_undercut_faces(faces, _PULL_Y)
    assert out["undercut_count"] == 0
    assert out["undercut_faces"] == []
    assert out["releasable_count"] == 1
    assert out["side_wall_count"] == 4


def test_undercut_back_face_is_flagged():
    """A face whose outward normal points opposite the pull (-Y) is an
    undercut and must be listed (the GREEN 'undercut' criterion)."""
    faces = [
        _face(0, (0.0, 1.0, 0.0)),  # releasable
        _face(7, (0.0, -1.0, 0.0)),  # back face -> undercut
        _face(2, (1.0, 0.0, 0.0)),  # side wall
    ]
    out = _classify_undercut_faces(faces, _PULL_Y)
    assert out["undercut_count"] == 1
    assert len(out["undercut_faces"]) == 1
    flagged = out["undercut_faces"][0]
    assert flagged["index"] == 7
    assert flagged["classification"] == "undercut"
    assert flagged["dot_pull"] < 0


def test_undercut_discriminates_clean_vs_undercut():
    """The metric must DISCRIMINATE: same pull, the undercut part reports a
    strictly higher undercut_count than the clean one."""
    clean = [_face(0, (0.0, 1.0, 0.0)), _face(1, (1.0, 0.0, 0.0))]
    dirty = [_face(0, (0.0, 1.0, 0.0)), _face(1, (0.0, -1.0, 0.0))]
    c = _classify_undercut_faces(clean, _PULL_Y)
    d = _classify_undercut_faces(dirty, _PULL_Y)
    assert d["undercut_count"] > c["undercut_count"]


def test_undercut_partially_back_facing_is_flagged():
    """A face tilted past vertical so it slightly faces back (-Y component)
    is an undercut, even if mostly sideways."""
    # normal pointing mostly +x but a touch -y: dot with +Y is negative.
    n = _vec_unit((1.0, -0.2, 0.0))
    out = _classify_undercut_faces([_face(0, n)], _PULL_Y)
    assert out["undercut_count"] == 1


def test_undercut_side_wall_within_tolerance():
    """A face exactly parallel to the pull (dot ~ 0) is a side wall, not an
    undercut -- the side_tol band protects against float noise."""
    out = _classify_undercut_faces([_face(0, (1.0, 0.0, 0.0))], _PULL_Y)
    assert out["side_wall_count"] == 1
    assert out["undercut_count"] == 0


def test_undercut_pull_direction_matters():
    """Flipping the pull turns a releasable face into an undercut."""
    top = [_face(0, (0.0, 1.0, 0.0))]
    up = _classify_undercut_faces(top, (0.0, 1.0, 0.0))
    down = _classify_undercut_faces(top, (0.0, -1.0, 0.0))
    assert up["undercut_count"] == 0
    assert down["undercut_count"] == 1


def test_undercut_degenerate_normal_skipped():
    out = _classify_undercut_faces([_face(0, (0.0, 0.0, 0.0))], _PULL_Y)
    assert out["skipped"] == 1
    assert out["face_count"] == 1
    assert out["undercut_count"] == 0


def test_undercut_degenerate_pull_noted():
    out = _classify_undercut_faces([_face(0, (0.0, 1.0, 0.0))], (0.0, 0.0, 0.0))
    assert out["note"] == "degenerate_pull_dir"


def test_undercut_draft_deg_matches_w37_convention():
    """draft_deg = 90 - acos(dot). A face pointing straight along +pull has
    draft 90; a side wall has draft 0; a back face has draft -90."""
    releasable = _classify_undercut_faces([_face(0, (0.0, 1.0, 0.0))], _PULL_Y)
    side = _classify_undercut_faces([_face(0, (1.0, 0.0, 0.0))], _PULL_Y)
    back = _classify_undercut_faces([_face(0, (0.0, -1.0, 0.0))], _PULL_Y)
    assert math.isclose(releasable["faces"][0]["draft_deg"], 90.0, abs_tol=1e-6)
    assert math.isclose(side["faces"][0]["draft_deg"], 0.0, abs_tol=1e-6)
    assert math.isclose(back["faces"][0]["draft_deg"], -90.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Pure: _min_wall_from_samples  (min-wall reduction)
# ---------------------------------------------------------------------------


def test_min_wall_picks_smallest_valid_sample():
    out = _min_wall_from_samples([0.010, 0.003, 0.008])  # 10, 3, 8 mm
    assert math.isclose(out["min_wall_mm"], 3.0, abs_tol=1e-9)
    assert out["valid_sample_count"] == 3
    assert out["sample_count"] == 3


def test_min_wall_discriminates_thin_vs_thick():
    """DISCRIMINATION: the thin-walled fixture must report a smaller min-wall
    than the thick block (the GREEN criterion for the seat run)."""
    thin = _min_wall_from_samples([0.0015, 0.0015, 0.020])  # 1.5mm wall
    thick = _min_wall_from_samples([0.030, 0.030, 0.030])  # 30mm block
    assert thin["min_wall_mm"] < thick["min_wall_mm"]
    assert math.isclose(thin["min_wall_mm"], 1.5, abs_tol=1e-9)


def test_min_wall_drops_degenerate_zero_samples():
    """Self-hit / coincident samples below the floor must not report a bogus
    ~0 wall."""
    out = _min_wall_from_samples([0.0, 1e-9, 0.004])
    assert math.isclose(out["min_wall_mm"], 4.0, abs_tol=1e-9)
    assert out["valid_sample_count"] == 1


def test_min_wall_empty_input_is_noted_not_raised():
    out = _min_wall_from_samples([])
    assert out["min_wall_mm"] is None
    assert out["note"] == "no_valid_samples"


def test_min_wall_all_degenerate_noted():
    out = _min_wall_from_samples([0.0, None, 1e-12])  # type: ignore[list-item]
    assert out["min_wall_mm"] is None
    assert out["note"] == "no_valid_samples"


def test_min_wall_mean_is_diagnostic():
    out = _min_wall_from_samples([0.002, 0.004])
    assert math.isclose(out["mean_wall_mm"], 3.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Fake COM stack: exercise _measure_opposite_distance + the wrappers offline
# ---------------------------------------------------------------------------


class FakeFace:
    """Minimal IFace2 stand-in: a planar face at a fixed plane.

    GetClosestPointOn projects a probe onto the plane (axis-aligned planes
    only, which is all the fixtures need). Normal/GetArea mirror the real
    late-bound surface.
    """

    def __init__(self, normal, point_on_plane, area_m2=1e-4, box=None):
        self.Normal = normal
        self._n = _vec_unit(normal)
        self._p0 = point_on_plane  # a point the plane passes through
        self.GetArea = area_m2
        self._box = box or (
            point_on_plane[0] - 0.01,
            point_on_plane[1] - 0.01,
            point_on_plane[2] - 0.01,
            point_on_plane[0] + 0.01,
            point_on_plane[1] + 0.01,
            point_on_plane[2] + 0.01,
        )

    @property
    def GetBox(self):
        return self._box

    def GetClosestPointOn(self, x, y, z):
        # Project (x,y,z) onto the plane defined by (_p0, _n).
        if self._n is None:
            return None
        vx, vy, vz = x - self._p0[0], y - self._p0[1], z - self._p0[2]
        d = vx * self._n[0] + vy * self._n[1] + vz * self._n[2]
        return (x - d * self._n[0], y - d * self._n[1], z - d * self._n[2])


class FakeBody:
    def __init__(self, faces):
        self._faces = faces

    def GetFaces(self):
        return self._faces


class FakeDoc:
    """Models SW late-binding: zero-arg methods auto-invoke on attribute
    access (so ``resolve(doc, "GetType")`` yields the value, not a bound
    method), while arg-taking methods (GetBodies2) stay callable.
    """

    def __init__(self, faces, doc_type=1):
        self._faces = faces
        self.GetPathName = "C:/fake/part.SLDPRT"
        self.GetType = doc_type  # property-like; resolve() reads it directly

    def GetBodies2(self, body_type, visible_only):
        return [FakeBody(self._faces)]


def _slab_faces(thickness_m):
    """Two parallel planar faces a *thickness_m* apart along Y, forming a
    slab whose wall thickness is exactly *thickness_m*."""
    top = FakeFace((0.0, 1.0, 0.0), (0.0, thickness_m, 0.0))
    bottom = FakeFace((0.0, -1.0, 0.0), (0.0, 0.0, 0.0))
    return [top, bottom]


def test_measure_opposite_distance_recovers_slab_thickness():
    faces = _slab_faces(0.005)  # 5 mm
    top = faces[0]
    # Sample a point on the top face, cast inward (-Y) to the bottom.
    point = (0.0, 0.005, 0.0)
    inward = (0.0, -1.0, 0.0)
    d = _measure_opposite_distance(faces, top, point, inward)
    assert d is not None
    assert math.isclose(d, 0.005, abs_tol=1e-9)


def test_measure_opposite_distance_ignores_same_face_and_offaxis():
    faces = _slab_faces(0.003)
    top = faces[0]
    d = _measure_opposite_distance(faces, top, (0.0, 0.003, 0.0), (0.0, -1.0, 0.0))
    assert math.isclose(d, 0.003, abs_tol=1e-9)


def test_sw_min_wall_thickness_discriminates_via_fake_doc(monkeypatch):
    """End-to-end through the COM wrapper with a fake doc: a 2mm slab must
    report a smaller min wall than a 20mm slab."""
    import ai_sw_bridge.observe as obs

    monkeypatch.setattr(obs, "get_sw_app", lambda: object())

    def run(thickness_m):
        monkeypatch.setattr(
            obs, "get_active_doc", lambda _sw: FakeDoc(_slab_faces(thickness_m))
        )
        return obs._sw_min_wall_thickness_impl(samples_per_face=2)

    thin = run(0.002)
    thick = run(0.020)
    assert thin["ok"] is True
    assert thick["ok"] is True
    assert thin["min_wall_mm"] is not None
    assert thick["min_wall_mm"] is not None
    assert thin["min_wall_mm"] < thick["min_wall_mm"]
    assert math.isclose(thin["min_wall_mm"], 2.0, abs_tol=1e-3)


def test_sw_undercut_faces_flags_back_face_via_fake_doc(monkeypatch):
    """End-to-end through the COM wrapper: a doc with a back-facing face is
    flagged; one without is clean."""
    import ai_sw_bridge.observe as obs

    monkeypatch.setattr(obs, "get_sw_app", lambda: object())

    clean = [
        FakeFace((0.0, 1.0, 0.0), (0.0, 0.01, 0.0)),
        FakeFace((1.0, 0.0, 0.0), (0.01, 0.0, 0.0)),
    ]
    dirty = clean + [FakeFace((0.0, -1.0, 0.0), (0.0, -0.01, 0.0))]

    monkeypatch.setattr(obs, "get_active_doc", lambda _sw: FakeDoc(clean))
    c = obs._sw_undercut_faces_impl()  # default pull +Y
    monkeypatch.setattr(obs, "get_active_doc", lambda _sw: FakeDoc(dirty))
    d = obs._sw_undercut_faces_impl()

    assert c["ok"] is True and d["ok"] is True
    assert c["undercut_count"] == 0
    assert d["undercut_count"] == 1
    assert d["undercut_faces"][0]["dot_pull"] < 0


def test_sw_undercut_faces_rejects_non_part(monkeypatch):
    import ai_sw_bridge.observe as obs

    monkeypatch.setattr(obs, "get_sw_app", lambda: object())
    monkeypatch.setattr(
        obs, "get_active_doc", lambda _sw: FakeDoc([], doc_type=2)
    )  # assembly
    out = obs._sw_undercut_faces_impl()
    assert out["ok"] is False
    assert "requires a part" in out["error"]


# ---------------------------------------------------------------------------
# Wire-contract shape tests (no SW running -> typed error dict)
# ---------------------------------------------------------------------------

UNDERCUT_KEYS = frozenset(
    {
        "ok",
        "doc_path",
        "pull_dir",
        "face_count",
        "undercut_count",
        "releasable_count",
        "side_wall_count",
        "skipped",
        "undercut_faces",
        "faces",
        "error",
    }
)

MIN_WALL_KEYS = frozenset(
    {
        "ok",
        "doc_path",
        "min_wall_mm",
        "min_wall_m",
        "mean_wall_mm",
        "sample_count",
        "valid_sample_count",
        "samples_per_face",
        "method",
        "error",
    }
)


def test_sw_undercut_faces_shape_when_sw_unavailable():
    result = sw_undercut_faces()
    assert isinstance(result, dict)
    assert set(result.keys()) == UNDERCUT_KEYS
    if not result["ok"]:
        assert result["error"] is not None


def test_sw_min_wall_thickness_shape_when_sw_unavailable():
    result = sw_min_wall_thickness()
    assert isinstance(result, dict)
    assert set(result.keys()) == MIN_WALL_KEYS
    if not result["ok"]:
        assert result["error"] is not None
