"""Face resolution must be a pure function of model geometry.

Issue #47: the same spec, built twice on the same seat minutes apart, resolved
a face-referenced sketch to different live faces. ``_select_extrude_face``
used to accept the first SelectByID spiral hit whose normal matched, then
fall back to the first GetFaces entry within 1 um of the modelled centre.
Neither path is a total order on geometry: SelectByID is a view/screen pick,
and GetFaces order is not part of the spec.

These tests drive a fake COM document. Faces are returned in shuffled order
and SelectByID is wired to a WRONG coplanar face; the resolved face must
still be identical every time. That is the test that would have caught #47.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.spec._build_context import BuildContext, BuiltFeature
from ai_sw_bridge.spec._face_geometry import (
    _MAX_FACE_SEED_DIST_M,
    _SELECT_BY_ID_OFFSETS_UV,
    _face_sort_key,
    _select_extrude_face,
)


# A 20 x 20 x 10 mm box on Front Plane, centred on the origin. Modelled +z
# face centre is (0, 0, 0.010) m.
def _box_parent() -> BuiltFeature:
    return BuiltFeature(
        name="Extrude_Box",
        type="boss_extrude_blind",
        extrude_axis=(0.0, 0.0, 1.0),
        extrude_origin=(0.0, 0.0, 0.0),
        extrude_depth_m=0.010,
        extrude_flip=False,
        sketch_extent_uv=(0.010, 0.010),
    )


class _FakeFace:
    """Late-bound IFace2 stand-in. GetArea/GetBox are attributes (late-bound
    auto-invoke); GetClosestPointOn is a method. Select2 records the pick."""

    def __init__(
        self,
        name: str,
        *,
        normal: tuple[float, float, float],
        plane_z: float,
        area: float,
        centroid: tuple[float, float, float],
        bounded_closest: tuple[float, float, float] | None = None,
    ) -> None:
        self.name = name
        self.Normal = normal
        self._plane_z = plane_z
        self.GetArea = area
        cx, cy, cz = centroid
        self.GetBox = (
            cx - 0.001,
            cy - 0.001,
            cz - 0.001,
            cx + 0.001,
            cy + 0.001,
            cz + 0.001,
        )
        self._bounded_closest = bounded_closest
        self.selects: list[tuple[bool, int]] = []
        self._doc: _FakeDoc | None = None

    def GetClosestPointOn(
        self, x: float, y: float, z: float
    ) -> tuple[float, float, float]:
        # Default: project onto the infinite plane (the interpretation that
        # makes every coplanar same-normal face a 1-um match of the modelled
        # centre). Optional bounded_closest simulates a clamped-to-boundary
        # implementation.
        if self._bounded_closest is not None:
            return self._bounded_closest
        nx, ny, nz = self.Normal
        if abs(nz) > 0.99:
            return (x, y, self._plane_z)
        if abs(nx) > 0.99:
            return (self._plane_z, y, z)
        return (x, self._plane_z, z)

    def Select2(self, append: bool, mark: int) -> bool:
        self.selects.append((append, mark))
        if self._doc is not None:
            self._doc.selected = self
        return True


class _FakeBody:
    def __init__(self, faces: list[_FakeFace]) -> None:
        self._faces = faces

    def GetFaces(self) -> list[_FakeFace]:
        return list(self._faces)


class _FakeSelectionManager:
    def __init__(self, doc: _FakeDoc) -> None:
        self._doc = doc

    def GetSelectedObject6(self, _idx: int, _mark: int) -> _FakeFace | None:
        return self._doc.selected


class _FakeDoc:
    def __init__(
        self,
        faces: list[_FakeFace],
        *,
        select_by_id_face: _FakeFace | None = None,
        select_by_id_ok: bool = True,
    ) -> None:
        self._faces = list(faces)
        for face in self._faces:
            face._doc = self
        self.selected: _FakeFace | None = None
        self.select_by_id_face = select_by_id_face
        self.select_by_id_ok = select_by_id_ok
        self.select_by_id_calls: list[tuple[float, float, float]] = []
        self.clears = 0

    def ClearSelection2(self, _flag: bool) -> None:
        self.clears += 1
        self.selected = None

    def SelectByID(self, _name: str, typ: str, x: float, y: float, z: float) -> bool:
        self.select_by_id_calls.append((x, y, z))
        if typ != "FACE" or not self.select_by_id_ok or self.select_by_id_face is None:
            return False
        self.selected = self.select_by_id_face
        return True

    @property
    def SelectionManager(self) -> _FakeSelectionManager:
        return _FakeSelectionManager(self)

    def GetBodies2(self, _btype: int, _visible: bool) -> list[_FakeBody]:
        return [_FakeBody(self._faces)]

    def set_face_order(self, names: list[str]) -> None:
        by_name = {f.name: f for f in self._faces}
        self._faces = [by_name[n] for n in names]


def _coplanar_plusz_faces() -> tuple[_FakeFace, _FakeFace, _FakeFace, _FakeFace]:
    """Four faces: intended +z cap, a coplanar leftover sliver, a stacked
    parallel boss-cap, and the opposite -z cap."""
    intended = _FakeFace(
        "intended_+z",
        normal=(0.0, 0.0, 1.0),
        plane_z=0.010,
        area=4.0e-4,
        centroid=(0.0, 0.0, 0.010),
    )
    sliver = _FakeFace(
        "sliver_+z",
        normal=(0.0, 0.0, 1.0),
        plane_z=0.010,
        area=5.0e-5,
        centroid=(0.008, 0.0, 0.010),
    )
    stacked = _FakeFace(
        "stacked_boss_+z",
        normal=(0.0, 0.0, 1.0),
        plane_z=0.020,
        area=4.0e-4,
        centroid=(0.0, 0.0, 0.020),
    )
    minus_z = _FakeFace(
        "intended_-z",
        normal=(0.0, 0.0, -1.0),
        plane_z=0.0,
        area=4.0e-4,
        centroid=(0.0, 0.0, 0.0),
    )
    return intended, sliver, stacked, minus_z


def _ctx_for(doc: _FakeDoc) -> BuildContext:
    return BuildContext(
        sw=None, doc=doc, features_by_name={"Extrude_Box": _box_parent()}
    )


# ---------------------------------------------------------------------------
# Pure ranking key
# ---------------------------------------------------------------------------


def test_face_sort_key_is_a_total_order_on_geometry() -> None:
    # Nearer beats farther regardless of area.
    near = _face_sort_key(0.0, 1.0e-6, (9.0, 9.0, 9.0))
    far = _face_sort_key(1.0e-6, 1.0, (0.0, 0.0, 0.0))
    assert near < far
    # Equal distance: larger area wins.
    big = _face_sort_key(0.0, 4.0e-4, (1.0, 0.0, 0.0))
    small = _face_sort_key(0.0, 1.0e-4, (0.0, 0.0, 0.0))
    assert big < small
    # Equal distance and area: centroid lexicographic (x, then y, then z).
    a = _face_sort_key(0.0, 1.0e-4, (0.0, 0.0, 1.0))
    b = _face_sort_key(0.0, 1.0e-4, (0.0, 1.0, 0.0))
    c = _face_sort_key(0.0, 1.0e-4, (1.0, 0.0, 0.0))
    assert a < b < c


# ---------------------------------------------------------------------------
# The test that would have caught #47
# ---------------------------------------------------------------------------


_SHUFFLES = [
    ["intended_+z", "sliver_+z", "stacked_boss_+z", "intended_-z"],
    ["sliver_+z", "stacked_boss_+z", "intended_-z", "intended_+z"],
    ["stacked_boss_+z", "intended_-z", "intended_+z", "sliver_+z"],
    ["intended_-z", "intended_+z", "sliver_+z", "stacked_boss_+z"],
    ["sliver_+z", "intended_+z", "intended_-z", "stacked_boss_+z"],
    ["stacked_boss_+z", "sliver_+z", "intended_+z", "intended_-z"],
]


@pytest.mark.parametrize("order", _SHUFFLES)
def test_plusz_resolution_ignores_getfaces_order_and_selectbyid(
    order: list[str],
) -> None:
    intended, sliver, stacked, minus_z = _coplanar_plusz_faces()
    # SelectByID is wired to the leftover sliver -- the view-dependent wrong
    # pick the spiral path used to accept because the normal still matches.
    doc = _FakeDoc(
        [intended, sliver, stacked, minus_z],
        select_by_id_face=sliver,
        select_by_id_ok=True,
    )
    doc.set_face_order(order)
    ok, fx, fy, fz = _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
    assert ok is True
    assert doc.selected is intended
    # SelectByID may be used to enact the ranked pick, but a wrong-face hit
    # (the sliver) is rejected and the ranked IFace2 is Select2'd instead.
    assert intended.selects, "wrong SelectByID hit must fall through to Select2"
    # Returned point is the closest point on the winner to the modelled centre.
    assert abs(fx) < 1e-12 and abs(fy) < 1e-12 and abs(fz - 0.010) < 1e-12


def test_shuffled_runs_resolve_the_same_face() -> None:
    winners: list[str] = []
    for order in _SHUFFLES:
        intended, sliver, stacked, minus_z = _coplanar_plusz_faces()
        doc = _FakeDoc(
            [intended, sliver, stacked, minus_z],
            select_by_id_face=sliver,
        )
        doc.set_face_order(order)
        ok, *_ = _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
        assert ok is True
        assert doc.selected is not None
        winners.append(doc.selected.name)
    assert set(winners) == {"intended_+z"}
    assert len(winners) == len(_SHUFFLES)


def test_select_by_id_kept_when_it_fingerprints_as_the_ranked_winner() -> None:
    # The InsertSketch-proven pick is SelectByID at a point on the face.
    # When that pick IS the ranked winner, keep it (do not Select2).
    intended, sliver, stacked, minus_z = _coplanar_plusz_faces()
    doc = _FakeDoc(
        [intended, sliver, stacked, minus_z],
        select_by_id_face=intended,
        select_by_id_ok=True,
    )
    ok, *_ = _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
    assert ok is True
    assert doc.selected is intended
    assert doc.select_by_id_calls, "ranked winner is enacted via SelectByID first"
    assert intended.selects == []


def test_bounded_closest_prefers_nearest_fragment() -> None:
    # GetClosestPointOn clamps to the face boundary: the sliver's closest
    # point is 8 mm off the modelled centre, the intended face still contains
    # it (dist = 0). Rank-by-distance must pick the intended face even when
    # the sliver is enumerated first and is larger (so area-tie-break alone
    # would pick wrong).
    intended = _FakeFace(
        "intended_+z",
        normal=(0.0, 0.0, 1.0),
        plane_z=0.010,
        area=1.0e-4,
        centroid=(0.0, 0.0, 0.010),
        bounded_closest=(0.0, 0.0, 0.010),
    )
    sliver = _FakeFace(
        "sliver_+z",
        normal=(0.0, 0.0, 1.0),
        plane_z=0.010,
        area=4.0e-4,
        centroid=(0.008, 0.0, 0.010),
        bounded_closest=(0.008, 0.0, 0.010),
    )
    doc = _FakeDoc([sliver, intended], select_by_id_face=sliver)
    ok, *_ = _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
    assert ok is True
    assert doc.selected is intended


def test_select_by_id_is_fallback_when_enumeration_raises(
    capsys: pytest.CaptureFixture[str],
) -> None:
    intended, sliver, stacked, minus_z = _coplanar_plusz_faces()

    class _BrokenDoc(_FakeDoc):
        def GetBodies2(self, _btype: int, _visible: bool) -> list[_FakeBody]:
            raise RuntimeError("GetBodies2 unavailable")

    doc = _BrokenDoc(
        [intended, sliver, stacked, minus_z],
        select_by_id_face=intended,
        select_by_id_ok=True,
    )
    ok, *_ = _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
    assert ok is True
    assert doc.selected is intended
    assert doc.select_by_id_calls, "SelectByID spiral is the fallback path"
    err = capsys.readouterr().err
    assert "path=select_by_id" in err


def test_face_resolve_logs_enumeration_identity(
    capsys: pytest.CaptureFixture[str],
) -> None:
    intended, sliver, stacked, minus_z = _coplanar_plusz_faces()
    doc = _FakeDoc(
        [minus_z, sliver, intended, stacked],
        select_by_id_face=sliver,
    )
    _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
    err = capsys.readouterr().err
    assert "FACE_RESOLVE" in err
    assert "parent='Extrude_Box'" in err
    assert "face=+z" in err
    assert "path=enumeration" in err
    assert "index=2" in err  # intended is third in this GetFaces order
    assert "area_m2=" in err
    assert "centroid_mm=" in err
    assert "normal=" in err


def test_unresolved_logs_and_returns_false(capsys: pytest.CaptureFixture[str]) -> None:
    class _EmptyDoc(_FakeDoc):
        def GetBodies2(self, _btype: int, _visible: bool) -> list[_FakeBody]:
            return []

    intended, sliver, stacked, minus_z = _coplanar_plusz_faces()
    doc = _EmptyDoc(
        [intended, sliver, stacked, minus_z],
        select_by_id_ok=False,
    )
    ok, *_ = _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
    assert ok is False
    err = capsys.readouterr().err
    assert "FACE_RESOLVE" in err
    assert "path=unresolved" in err


def test_minus_z_does_not_pick_a_plus_z_face() -> None:
    intended, sliver, stacked, minus_z = _coplanar_plusz_faces()
    doc = _FakeDoc(
        [intended, sliver, stacked, minus_z],
        select_by_id_face=intended,
    )
    ok, *_ = _select_extrude_face(_ctx_for(doc), _box_parent(), "-z")
    assert ok is True
    assert doc.selected is minus_z


def test_far_away_matching_face_is_rejected_not_silently_selected() -> None:
    """A normal-matching face far from the modelled centre is NOT this face.

    Ranking alone is a total order but not a correctness test: with no
    acceptance radius the nearest candidate wins even when it belongs to a
    different feature, which turns an honest failure into a sketch built on
    the wrong body. The radius is derived from the SelectByID probe offsets,
    so a candidate the spiral could never have reached is rejected.
    """
    stray = _FakeFace(
        "stray_+z_on_another_body",
        normal=(0.0, 0.0, 1.0),
        plane_z=0.010,
        area=4.0e-4,
        centroid=(0.050, 0.0, 0.010),
        bounded_closest=(0.050, 0.0, 0.010),  # 50 mm from the modelled centre
    )
    doc = _FakeDoc([stray], select_by_id_ok=False)
    ok, fx, fy, fz = _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
    assert ok is False
    assert doc.selected is None
    # Falls back to the modelled centre, as the unresolved contract requires.
    assert (fx, fy, fz) == (0.0, 0.0, 0.010)


def test_acceptance_radius_tracks_the_probe_offsets() -> None:
    """The radius must stay derived, never hand-maintained alongside them."""
    expected = max((du * du + dv * dv) ** 0.5 for du, dv in _SELECT_BY_ID_OFFSETS_UV)
    assert _MAX_FACE_SEED_DIST_M == expected


def test_face_just_inside_the_radius_is_still_accepted() -> None:
    """The bound must not break the case the spiral existed for: a modelled
    centre sitting in a hole, with the real face's closest point offset."""
    offset = _MAX_FACE_SEED_DIST_M * 0.9
    reachable = _FakeFace(
        "rim_of_the_intended_face",
        normal=(0.0, 0.0, 1.0),
        plane_z=0.010,
        area=4.0e-4,
        centroid=(offset, 0.0, 0.010),
        bounded_closest=(offset, 0.0, 0.010),
    )
    doc = _FakeDoc([reachable], select_by_id_ok=False)
    ok, *_ = _select_extrude_face(_ctx_for(doc), _box_parent(), "+z")
    assert ok is True
    assert doc.selected is reachable
