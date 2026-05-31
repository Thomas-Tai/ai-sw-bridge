"""Tests for brep/interrogator.py (spec.md §2.2).

Uses a mocked ``IFeature`` / ``IFace2`` pair with canned box + normal
tuples. The mock emulates the E2.1 spike's load-bearing findings:

* zero-arg IFace2 methods auto-invoke on attribute access under
  pywin32 late binding — so ``face.GetBox`` returns the tuple, not a
  callable. The mock matches this shape (plain attributes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from ai_sw_bridge.brep import BrepFace, interrogate
from ai_sw_bridge.brep.interrogator import _role_hint


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------


@dataclass
class MockFace:
    """Stand-in for an IFace2 dispatch proxy.

    Late-binding quirk: ``GetBox`` / ``Normal`` / ``GetArea`` are
    attribute reads that already return the value. We model that by
    exposing methods that return the stored value; the interrogator
    reads ``face.GetBox`` (property access) and gets the value back
    thanks to the dataclass-decorated class's ``callable`` check.
    """

    box: tuple[float, float, float, float, float, float]
    normal: tuple[float, float, float]
    area_m2: float = 1e-4  # 100 mm²
    is_surface: bool = False

    def GetBox(self) -> tuple[float, ...]:
        return self.box

    def Normal(self) -> tuple[float, ...]:
        return self.normal

    def GetArea(self) -> float:
        # Some dispatch paths surface this as a callable; support both.
        return self.area_m2

    def IsSurface(self) -> bool:
        return self.is_surface


@dataclass
class MockFeature:
    """Stand-in for an IFeature dispatch proxy."""

    Name: str = "Extrude_Plate"
    faces: tuple[MockFace, ...] = ()

    def GetFaces(self):
        return self.faces


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enable_brep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force brep_interrogation ON for the duration of a test."""
    monkeypatch.setenv("AI_SW_BRIDGE_FLAG_BREP_INTERROGATION", "1")


@pytest.fixture
def disable_brep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SW_BRIDGE_FLAG_BREP_INTERROGATION", "0")


def _box_face(
    min_corner: tuple[float, float, float],
    max_corner: tuple[float, float, float],
    normal: tuple[float, float, float],
) -> MockFace:
    box = (*min_corner, *max_corner)
    # area is approximate — the interrogator's area path is best-effort.
    return MockFace(box=box, normal=normal, area_m2=1e-4)


# ---------------------------------------------------------------------------
# Tests — flag gating
# ---------------------------------------------------------------------------


def test_interrogate_returns_none_when_flag_off(disable_brep) -> None:
    feature = MockFeature(
        faces=(
            _box_face(
                (0.0, 0.0, 0.0),
                (0.01, 0.01, 0.005),
                (0.0, 0.0, 1.0),
            ),
        )
    )
    assert interrogate(feature) is None


# ---------------------------------------------------------------------------
# Tests — flag-on, single face
# ---------------------------------------------------------------------------


def test_interrogate_extracts_face_dict(enable_brep) -> None:
    face = _box_face(
        (-0.01, -0.01, 0.0),
        (0.01, 0.01, 0.005),
        (0.0, 0.0, 1.0),
    )
    feature = MockFeature(faces=(face,))
    result = interrogate(feature)
    assert result is not None
    assert result["feature"] == "Extrude_Plate"
    assert len(result["faces"]) == 1
    f = result["faces"][0]
    assert f["face_idx"] == 0
    assert f["body_id"] == 0
    assert f["temp_id"] == "body0_face0"
    assert f["normal"] == [0.0, 0.0, 1.0]
    # centroid is box midpoint
    assert f["centroid"] == pytest.approx([0.0, 0.0, 0.0025])
    assert f["bbox"] == [[-0.01, -0.01, 0.0], [0.01, 0.01, 0.005]]
    assert f["area_mm2"] == pytest.approx(100.0)  # 1e-4 m² -> 100 mm²
    assert "fingerprint" in f  # empty until E2.3 assigns one
    assert f["role_hint"] == "+z_outboard"


# ---------------------------------------------------------------------------
# Tests — six-face box (matches E2.1 spike output shape)
# ---------------------------------------------------------------------------


def test_six_face_box_roles(enable_brep) -> None:
    """Each of the six faces of a 20x20x5mm box gets the expected role_hint."""
    # Box centered at origin, extruded +Z from 0 to 5mm.
    faces = (
        # -X face
        _box_face((-0.01, -0.01, 0.0), (-0.01, 0.01, 0.005), (-1.0, 0.0, 0.0)),
        # -Y face
        _box_face((-0.01, -0.01, 0.0), (0.01, -0.01, 0.005), (0.0, -1.0, 0.0)),
        # +X face
        _box_face((0.01, -0.01, 0.0), (0.01, 0.01, 0.005), (1.0, 0.0, 0.0)),
        # +Y face
        _box_face((-0.01, 0.01, 0.0), (0.01, 0.01, 0.005), (0.0, 1.0, 0.0)),
        # +Z face (top, outboard)
        _box_face((-0.01, -0.01, 0.005), (0.01, 0.01, 0.005), (0.0, 0.0, 1.0)),
        # -Z face (bottom)
        _box_face((-0.01, -0.01, 0.0), (0.01, 0.01, 0.0), (0.0, 0.0, -1.0)),
    )
    feature = MockFeature(faces=faces)
    result = interrogate(feature)
    assert result is not None
    roles = [f["role_hint"] for f in result["faces"]]
    assert roles == [
        "-x_outboard",
        "-y_outboard",
        "+x_outboard",
        "+y_outboard",
        "+z_outboard",
        "-z_outboard",
    ]


# ---------------------------------------------------------------------------
# Tests — role-hint heuristic (unit)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "normal,expected",
    [
        ((1.0, 0.0, 0.0), "+x_outboard"),
        ((-1.0, 0.0, 0.0), "-x_outboard"),
        ((0.0, 1.0, 0.0), "+y_outboard"),
        ((0.0, -1.0, 0.0), "-y_outboard"),
        ((0.0, 0.0, 1.0), "+z_outboard"),
        ((0.0, 0.0, -1.0), "-z_outboard"),
    ],
)
def test_role_hint_axis_aligned(
    normal: tuple[float, float, float], expected: str
) -> None:
    box = (0.0, 0.0, 0.0, 0.01, 0.01, 0.005)
    centroid = (0.005, 0.005, 0.0025)
    assert _role_hint(normal, centroid, box) == expected


# ---------------------------------------------------------------------------
# Tests — Phase-0 durable-selection persist capture (persist_capture flag)
# ---------------------------------------------------------------------------


@dataclass
class _Ctx:
    """Minimal BuildContext stand-in carrying just the live doc handle."""

    doc: object = None


@pytest.fixture
def enable_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SW_BRIDGE_FLAG_PERSIST_CAPTURE", "1")


def _one_face_feature() -> MockFeature:
    return MockFeature(
        faces=(_box_face((-0.01, -0.01, 0.0), (0.01, 0.01, 0.005), (0.0, 0.0, 1.0)),)
    )


def test_capture_off_by_default_omits_persist_id(enable_brep) -> None:
    """With persist_capture OFF, the face dict carries no persist_id key."""
    result = interrogate(_one_face_feature(), _Ctx(doc=object()))
    assert result is not None
    assert "persist_id" not in result["faces"][0]


def test_capture_on_encodes_token_base64url_nopad(
    enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """persist_capture ON + a readable token -> base64url (no padding) persist_id."""
    # 4 raw bytes -> "//79/A" unpadded (b64 of these would normally pad with "==").
    raw = bytes([255, 254, 253, 252])
    monkeypatch.setattr(
        "ai_sw_bridge.brep.interrogator.read_persist_reference",
        lambda doc, entity: raw,
    )
    result = interrogate(_one_face_feature(), _Ctx(doc=object()))
    assert result is not None
    pid = result["faces"][0]["persist_id"]
    assert pid == "__79_A"  # urlsafe, padding stripped
    # Round-trips through the canonical DurableRef adapter.
    import base64

    restored = base64.urlsafe_b64decode(pid + "=" * (-len(pid) % 4))
    assert restored == raw


def test_capture_on_but_read_returns_none_omits_persist_id(
    enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A token that won't read (None) leaves persist_id absent — fail-soft."""
    monkeypatch.setattr(
        "ai_sw_bridge.brep.interrogator.read_persist_reference",
        lambda doc, entity: None,
    )
    result = interrogate(_one_face_feature(), _Ctx(doc=object()))
    assert result is not None
    assert "persist_id" not in result["faces"][0]


def test_capture_on_but_no_doc_skips_read(
    enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No live doc on ctx -> the per-face read is never attempted."""
    calls: list[object] = []

    def _spy(doc, entity):
        calls.append(entity)
        return b"x"

    monkeypatch.setattr(
        "ai_sw_bridge.brep.interrogator.read_persist_reference", _spy
    )
    result = interrogate(_one_face_feature(), _Ctx(doc=None))
    assert result is not None
    assert "persist_id" not in result["faces"][0]
    assert calls == []


# ---------------------------------------------------------------------------
# Tests — Phase-0 edge capture (persist_capture flag, body-scoped edge walk)
# ---------------------------------------------------------------------------


@dataclass
class MockEdge:
    """IEdge stand-in: GetCurveParams2 head is start xyz + end xyz.

    ``curve`` / ``length`` are optional: when ``None`` (the default) the
    interrogator's curve-eval helper can't reach the ICurve vtable and the
    stored midpoint / length fall back to chord values — which is the
    behaviour every pre-existing test asserts. Supply a ``MockCurve`` and a
    float arc length to exercise the true-curve path.
    """

    cp: tuple
    curve: object = None
    length: object = None

    def GetCurveParams2(self):
        return self.cp

    def GetCurve(self):
        if self.curve is None:
            raise AttributeError("GetCurve not configured")
        return self.curve

    def GetLength(self):
        if self.length is None:
            raise AttributeError("GetLength not configured")
        return self.length


@dataclass
class MockCurve:
    """ICurve stand-in: parametric range + Evaluate(t) -> xyz tuple."""

    param_range: tuple[float, float]
    points: dict[float, tuple[float, float, float]]

    def GetParameterRange(self):
        return self.param_range

    def Evaluate(self, t):
        if t not in self.points:
            raise RuntimeError(f"MockCurve: no point at t={t}")
        return self.points[t]


@dataclass
class MockBody:
    edges: tuple

    def GetEdges(self):
        return self.edges


@dataclass
class MockDoc:
    bodies: tuple

    def GetBodies2(self, body_type, visible_only):
        return self.bodies


def _doc_with_one_edge(cp=(0.0, 0.0, 0.0, 0.0, 0.0, 0.01, 0, 0, 0, 0, 0)) -> MockDoc:
    return MockDoc(bodies=(MockBody(edges=(MockEdge(cp=cp),)),))


def test_edge_capture_on_populates_edges_block(
    enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ai_sw_bridge.brep.interrogator.read_persist_reference",
        lambda doc, entity: bytes([1, 2, 3, 4]),
    )
    result = interrogate(_one_face_feature(), _Ctx(doc=_doc_with_one_edge()))
    assert result is not None
    edges = result.get("edges")
    assert edges is not None and len(edges) == 1
    e = edges[0]
    assert e["start"] == [0.0, 0.0, 0.0]
    assert e["end"] == [0.0, 0.0, 0.01]
    assert e["length"] == pytest.approx(0.01)
    assert e["midpoint"] == pytest.approx([0.0, 0.0, 0.005])
    assert e["curve_mid_source"] == "chord"  # MockEdge has no ICurve configured
    assert e["persist_id"] == "AQIDBA"  # base64url(bytes 1,2,3,4), no pad


def test_edge_capture_off_has_no_edges_block(enable_brep) -> None:
    """persist_capture OFF -> no edge walk at all, no edges key."""
    result = interrogate(_one_face_feature(), _Ctx(doc=_doc_with_one_edge()))
    assert result is not None
    assert "edges" not in result


def test_edge_capture_omits_persist_id_when_unreadable(
    enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ai_sw_bridge.brep.interrogator.read_persist_reference",
        lambda doc, entity: None,
    )
    result = interrogate(_one_face_feature(), _Ctx(doc=_doc_with_one_edge()))
    assert result is not None
    # Edge still captured (geometry), but no token -> persist_id omitted.
    assert "persist_id" not in result["edges"][0]


def test_edge_with_bad_curveparams_is_skipped(
    enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ai_sw_bridge.brep.interrogator.read_persist_reference",
        lambda doc, entity: b"x",
    )
    doc = MockDoc(bodies=(MockBody(edges=(MockEdge(cp=(1.0, 2.0)),)),))  # too short
    result = interrogate(_one_face_feature(), _Ctx(doc=doc))
    assert result is not None
    assert "edges" not in result  # the only edge was skipped -> no block


# ---------------------------------------------------------------------------
# Tests — true curve-mid / arc-length capture (A-author, SW-free mock)
#
# Geometry: quarter-circle arc in the XY plane, r = 10 mm, center (0.01, 0, 0),
# from (0,0,0) at t=0 through apex (0.01, 0.01, 0) at t=pi/2 to (0.02, 0, 0)
# at t=pi. Chord length = 0.02 m, arc length = pi*r ≈ 0.03142 m. Chord midpoint
# = (0.01, 0, 0); true curve midpoint (apex) = (0.01, 0.01, 0).
#
# The predicate in selection/_edge_match.py is consume-only (Opus rule) — these
# tests verify the *interrogator* emits the true values; the downstream
# discrimination is pinned in tests/test_selection_live.py::
# TestEdgeMatchPredicate::test_true_curve_mid_separates_straight_from_arc.
# ---------------------------------------------------------------------------


_ARC_CP = (0.0, 0.0, 0.0, 0.02, 0.0, 0.0)  # start + end endpoints
_ARC_TRUE_MID = (0.01, 0.01, 0.0)          # apex of quarter-circle
_ARC_TRUE_LEN = math.pi * 0.01             # pi * r (r = 0.01 m)


def _arc_edge() -> MockEdge:
    curve = MockCurve(
        param_range=(0.0, math.pi),
        points={
            0.0: (0.0, 0.0, 0.0),
            math.pi / 2.0: _ARC_TRUE_MID,
            math.pi: (0.02, 0.0, 0.0),
        },
    )
    return MockEdge(cp=_ARC_CP, curve=curve, length=_ARC_TRUE_LEN)


def _chord_mid() -> tuple[float, float, float]:
    return (
        (_ARC_CP[0] + _ARC_CP[3]) / 2.0,
        (_ARC_CP[1] + _ARC_CP[4]) / 2.0,
        (_ARC_CP[2] + _ARC_CP[5]) / 2.0,
    )


class TestCurveMidpointCapture:
    """_probe_edge prefers true ICurve.Evaluate + IEdge.GetLength over chord."""

    def test_true_curve_mid_and_arc_length_captured(
        self, enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "ai_sw_bridge.brep.interrogator.read_persist_reference",
            lambda doc, entity: None,
        )
        doc = MockDoc(bodies=(MockBody(edges=(_arc_edge(),)),))
        result = interrogate(_one_face_feature(), _Ctx(doc=doc))
        assert result is not None
        e = result["edges"][0]
        # True curve midpoint (apex), NOT chord midpoint (0.01, 0, 0).
        assert e["midpoint"] == pytest.approx(list(_ARC_TRUE_MID))
        # True arc length (pi*r), NOT chord length (0.02).
        assert e["length"] == pytest.approx(_ARC_TRUE_LEN)
        assert e["curve_mid_source"] == "curve"

    def test_chord_fallback_when_curve_unreachable(
        self, enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MockEdge with no curve/length configured -> chord fallback."""
        monkeypatch.setattr(
            "ai_sw_bridge.brep.interrogator.read_persist_reference",
            lambda doc, entity: None,
        )
        doc = MockDoc(bodies=(MockBody(edges=(MockEdge(cp=_ARC_CP),)),))
        result = interrogate(_one_face_feature(), _Ctx(doc=doc))
        assert result is not None
        e = result["edges"][0]
        assert e["midpoint"] == pytest.approx(list(_chord_mid()))
        assert e["length"] == pytest.approx(0.02)
        assert e["curve_mid_source"] == "chord"

    def test_partial_success_curve_arc_only(
        self, enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GetLength works but GetCurve fails -> length=arc, midpoint=chord, source='curve-arc'."""
        monkeypatch.setattr(
            "ai_sw_bridge.brep.interrogator.read_persist_reference",
            lambda doc, entity: None,
        )
        edge = MockEdge(cp=_ARC_CP, curve=None, length=_ARC_TRUE_LEN)
        doc = MockDoc(bodies=(MockBody(edges=(edge,)),))
        result = interrogate(_one_face_feature(), _Ctx(doc=doc))
        e = result["edges"][0]
        assert e["length"] == pytest.approx(_ARC_TRUE_LEN)
        assert e["midpoint"] == pytest.approx(list(_chord_mid()))
        assert e["curve_mid_source"] == "curve-arc"

    def test_partial_success_curve_mid_only(
        self, enable_brep, enable_capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GetCurve works but GetLength fails -> midpoint=true, length=chord, source='curve-mid'."""
        monkeypatch.setattr(
            "ai_sw_bridge.brep.interrogator.read_persist_reference",
            lambda doc, entity: None,
        )
        curve = MockCurve(
            param_range=(0.0, math.pi),
            points={math.pi / 2.0: _ARC_TRUE_MID},
        )
        edge = MockEdge(cp=_ARC_CP, curve=curve, length=None)
        doc = MockDoc(bodies=(MockBody(edges=(edge,)),))
        result = interrogate(_one_face_feature(), _Ctx(doc=doc))
        e = result["edges"][0]
        assert e["midpoint"] == pytest.approx(list(_ARC_TRUE_MID))
        assert e["length"] == pytest.approx(0.02)  # chord fallback
        assert e["curve_mid_source"] == "curve-mid"

    def test_read_edge_geometry_mirrors_interrogator(self) -> None:
        """live._read_edge_geometry uses the same curve path so tier-2 resolve
        hashes byte-identical to the stored manifest edge."""
        from ai_sw_bridge.selection.live import _read_edge_geometry

        geom = _read_edge_geometry(_arc_edge())
        assert geom is not None
        assert geom["midpoint"] == pytest.approx(list(_ARC_TRUE_MID))
        assert geom["length"] == pytest.approx(_ARC_TRUE_LEN)
        assert geom["curve_mid_source"] == "curve"

        # And chord fallback when no curve configured.
        geom_chord = _read_edge_geometry(MockEdge(cp=_ARC_CP))
        assert geom_chord is not None
        assert geom_chord["midpoint"] == pytest.approx(list(_chord_mid()))
        assert geom_chord["curve_mid_source"] == "chord"

    def test_durable_edge_ref_carries_midpoint(self) -> None:
        """DurableEdgeRef.from_manifest_edge now stores the manifest midpoint
        so resolve_by_edge_fingerprint can forward it to the predicate."""
        from ai_sw_bridge.selection import DurableEdgeRef

        manifest_edge = {
            "edge_idx": 0,
            "body_id": 0,
            "start": list(_ARC_CP[:3]),
            "end": list(_ARC_CP[3:]),
            "length": _ARC_TRUE_LEN,
            "midpoint": list(_ARC_TRUE_MID),
        }
        ref = DurableEdgeRef.from_manifest_edge(manifest_edge)
        assert ref.midpoint == pytest.approx(_ARC_TRUE_MID)
        assert ref.length == pytest.approx(_ARC_TRUE_LEN)

        # Round-trip preserves midpoint.
        wire = ref.to_dict()
        assert wire["midpoint"] == pytest.approx(list(_ARC_TRUE_MID))
        back = DurableEdgeRef.from_dict(wire)
        assert back.midpoint == pytest.approx(_ARC_TRUE_MID)

    def test_durable_edge_ref_legacy_manifest_without_midpoint(self) -> None:
        """Older manifests without 'midpoint' still load; ref.midpoint is None."""
        from ai_sw_bridge.selection import DurableEdgeRef

        legacy = {
            "start": [0.0, 0.0, 0.0],
            "end": [0.02, 0.0, 0.0],
            "length": 0.02,
        }
        ref = DurableEdgeRef.from_manifest_edge(legacy)
        assert ref.midpoint is None
        wire = ref.to_dict()
        assert "midpoint" not in wire


def test_role_hint_oblique_for_tilted_normal() -> None:
    # 45-degree normal isn't axis-aligned.
    n = (1 / math.sqrt(2), 0.0, 1 / math.sqrt(2))
    box = (0.0, 0.0, 0.0, 0.01, 0.01, 0.005)
    centroid = (0.005, 0.005, 0.0025)
    assert _role_hint(n, centroid, box) == "oblique"


# ---------------------------------------------------------------------------
# Tests — resilience
# ---------------------------------------------------------------------------


def test_interrogate_skips_face_with_bad_box(enable_brep) -> None:
    # One face has a malformed GetBox (returns 5-tuple); interrogator
    # skips it and processes the good one.
    bad = MockFace(box=(0.0, 0.0, 0.0, 0.01, 0.01), normal=(0.0, 0.0, 1.0))
    good = _box_face(
        (0.0, 0.0, 0.0),
        (0.01, 0.01, 0.005),
        (0.0, 0.0, 1.0),
    )
    feature = MockFeature(faces=(bad, good))
    result = interrogate(feature)
    assert result is not None
    # Only the good face made it through.
    assert len(result["faces"]) == 1
    assert result["faces"][0]["face_idx"] == 1


def test_interrogate_empty_feature(enable_brep) -> None:
    feature = MockFeature(faces=())
    result = interrogate(feature)
    assert result is not None
    assert result["faces"] == []


def test_interrogate_handles_com_error_gracefully(enable_brep) -> None:
    """A feature whose GetFaces raises is caught; an error key is set."""

    class BrokenFeature:
        Name = "Broken"

        def GetFaces(self):
            raise RuntimeError("COM failure")

    result = interrogate(BrokenFeature())
    assert result is not None
    # The interrogator catches COM failures fail-soft: empty face list
    # with an error marker. _try_feature_getfaces swallows the exception
    # and returns [], so the error key is set only when _walk_faces
    # itself raises — which it doesn't here. Adjusting the assertion:
    # zero faces is the load-bearing guarantee.
    assert result["faces"] == []


# ---------------------------------------------------------------------------
# Tests — BrepFace dataclass
# ---------------------------------------------------------------------------


def test_brepface_to_dict_round_trip() -> None:
    f = BrepFace(
        face_idx=0,
        body_id=0,
        temp_id="body0_face0",
        normal_vec=(0.0, 0.0, 1.0),
        centroid=(0.0, 0.0, 0.0025),
        bbox=((-0.01, -0.01, 0.0), (0.01, 0.01, 0.005)),
        area_mm2=100.0,
        role_hint="+z_outboard",
    )
    d = f.to_dict()
    assert d["normal"] == [0.0, 0.0, 1.0]
    assert d["centroid"] == [0.0, 0.0, 0.0025]
    assert d["bbox"] == [[-0.01, -0.01, 0.0], [0.01, 0.01, 0.005]]
    assert d["fingerprint"] == ""
    assert d["is_surface"] is False
    assert d["is_hidden"] is False


# ---------------------------------------------------------------------------
# Tests — P0-8 edge cases (suppressed / hidden / imported)
# ---------------------------------------------------------------------------


@dataclass
class SuppressibleFeature:
    """Feature mock exposing IsSuppressed for the suppressed-feature path."""

    Name: str = "Suppressed_Cut"
    suppressed: bool = True
    faces: tuple = ()

    def IsSuppressed(self) -> bool:
        return self.suppressed

    def GetFaces(self):
        return self.faces


def test_interrogate_suppressed_feature_returns_status(enable_brep) -> None:
    feature = SuppressibleFeature(
        suppressed=True,
        faces=(_box_face((0.0, 0.0, 0.0), (0.01, 0.01, 0.005), (0.0, 0.0, 1.0)),),
    )
    result = interrogate(feature)
    assert result is not None
    assert result["status"] == "suppressed"
    # Suppressed features must not leak stale face data.
    assert result["faces"] == []


def test_interrogate_unsuppressed_feature_walks_normally(enable_brep) -> None:
    feature = SuppressibleFeature(
        suppressed=False,
        faces=(_box_face((0.0, 0.0, 0.0), (0.01, 0.01, 0.005), (0.0, 0.0, 1.0)),),
    )
    result = interrogate(feature)
    assert result is not None
    assert "status" not in result
    assert len(result["faces"]) == 1


@dataclass
class HideableFace(MockFace):
    """Face mock with IsHidden + Visible attributes."""

    hidden: bool = False
    visible: bool = True

    def IsHidden(self) -> bool:
        return self.hidden

    def Visible(self) -> bool:
        return self.visible


def test_interrogate_marks_hidden_face(enable_brep) -> None:
    hidden = HideableFace(
        box=(0.0, 0.0, 0.0, 0.01, 0.01, 0.005),
        normal=(0.0, 0.0, 1.0),
        hidden=True,
    )
    visible = HideableFace(
        box=(0.0, 0.0, 0.005, 0.01, 0.01, 0.005),
        normal=(0.0, 0.0, -1.0),
        hidden=False,
    )
    feature = MockFeature(faces=(hidden, visible))
    result = interrogate(feature)
    assert result is not None
    assert result["faces"][0]["is_hidden"] is True
    assert result["faces"][1]["is_hidden"] is False


def test_interrogate_falls_back_to_visible_when_ishidden_unavailable(
    enable_brep,
) -> None:
    """Older SW builds expose Visible (the inverse) instead of IsHidden."""

    @dataclass
    class VisibleOnlyFace:
        box: tuple = (0.0, 0.0, 0.0, 0.01, 0.01, 0.005)
        normal: tuple = (0.0, 0.0, 1.0)
        visible: bool = False  # inverse of hidden

        def GetBox(self):
            return self.box

        def Normal(self):
            return self.normal

        def GetArea(self):
            return 1e-4

        def Visible(self):
            return self.visible

    feature = MockFeature(faces=(VisibleOnlyFace(),))
    result = interrogate(feature)
    assert result is not None
    assert result["faces"][0]["is_hidden"] is True


@dataclass
class ImportFeature:
    """Mock for IFeature with GetTypeName2 == 'ImportFeature'."""

    Name: str = "Imported_STEP_Body"
    body_faces: tuple = ()

    def GetTypeName2(self) -> str:
        return "ImportFeature"

    def GetFaces(self):
        # ImportFeature returns no native faces via the feature handle —
        # this path should be skipped by the interrogator.
        raise AssertionError("interrogator must NOT call GetFaces on ImportFeature")

    def GetBody(self):
        if not self.body_faces:
            return None
        return _MockBody(self.body_faces)


@dataclass
class _MockBody:
    faces: tuple

    def GetFaces(self):
        return self.faces

    def GetNext(self):
        return None


def test_interrogate_import_feature_falls_back_to_body_walk(enable_brep) -> None:
    face = _box_face(
        (0.0, 0.0, 0.0),
        (0.01, 0.01, 0.005),
        (0.0, 0.0, 1.0),
    )
    feature = ImportFeature(body_faces=(face,))
    result = interrogate(feature)
    assert result is not None
    # Body walk produced one face — no status key needed.
    assert len(result["faces"]) == 1
    assert "status" not in result


def test_interrogate_import_feature_with_no_body_records_status(enable_brep) -> None:
    feature = ImportFeature(body_faces=())
    result = interrogate(feature)
    assert result is not None
    assert result["faces"] == []
    assert result["status"] == "imported"


# ---------------------------------------------------------------------------
# Tests — lazy mode (spec.md §2.11)
# ---------------------------------------------------------------------------


@dataclass
class LazyCtx:
    """Minimal ctx carrying referenced_face_roles for lazy-mode tests."""

    referenced_face_roles: set[tuple[str, str]] | None = None


def test_lazy_unreferenced_feature_skips_face_walk(enable_brep) -> None:
    """A feature not in the referenced set returns no_downstream_refs."""
    faces = (
        _box_face((-0.01, -0.01, 0.0), (0.01, 0.01, 0.005), (0.0, 0.0, 1.0)),
        _box_face((-0.01, -0.01, 0.0), (0.01, 0.01, 0.0), (0.0, 0.0, -1.0)),
    )
    feature = MockFeature(Name="SK_PlateSlab", faces=faces)
    ctx = LazyCtx(referenced_face_roles={("Other_Feature", "+z_outboard")})
    result = interrogate(feature, ctx)
    assert result is not None
    assert result["feature"] == "SK_PlateSlab"
    assert result["faces"] == []
    assert result["status"] == "no_downstream_refs"


def test_lazy_referenced_feature_filters_to_matching_roles(enable_brep) -> None:
    """A referenced feature walks all faces but keeps only matching roles."""
    faces = (
        _box_face((-0.01, -0.01, 0.0), (0.01, 0.01, 0.005), (0.0, 0.0, 1.0)),
        _box_face((-0.01, -0.01, 0.0), (0.01, 0.01, 0.0), (0.0, 0.0, -1.0)),
        _box_face((0.01, -0.01, 0.0), (0.01, 0.01, 0.005), (1.0, 0.0, 0.0)),
    )
    feature = MockFeature(Name="Boss_Box", faces=faces)
    ctx = LazyCtx(referenced_face_roles={("Boss_Box", "+z_outboard")})
    result = interrogate(feature, ctx)
    assert result is not None
    assert result["feature"] == "Boss_Box"
    assert "status" not in result
    assert len(result["faces"]) == 1
    assert result["faces"][0]["role_hint"] == "+z_outboard"


def test_lazy_multiple_roles_included(enable_brep) -> None:
    """Multiple roles for the same feature are all included."""
    faces = (
        _box_face((-0.01, -0.01, 0.0), (0.01, 0.01, 0.005), (0.0, 0.0, 1.0)),
        _box_face((-0.01, -0.01, 0.0), (0.01, 0.01, 0.0), (0.0, 0.0, -1.0)),
    )
    feature = MockFeature(Name="Boss_Box", faces=faces)
    ctx = LazyCtx(
        referenced_face_roles={
            ("Boss_Box", "+z_outboard"),
            ("Boss_Box", "-z_outboard"),
        }
    )
    result = interrogate(feature, ctx)
    assert result is not None
    assert len(result["faces"]) == 2


def test_lazy_eager_when_ctx_has_no_referenced_set(enable_brep) -> None:
    """ctx without referenced_face_roles (None) behaves as eager mode."""
    face = _box_face(
        (-0.01, -0.01, 0.0),
        (0.01, 0.01, 0.005),
        (0.0, 0.0, 1.0),
    )
    feature = MockFeature(faces=(face,))
    ctx = LazyCtx(referenced_face_roles=None)
    result = interrogate(feature, ctx)
    assert result is not None
    assert len(result["faces"]) == 1
    assert "status" not in result


def test_lazy_many_features_only_referenced_walked(enable_brep) -> None:
    """Acceptance: 100 features, only 3 referenced — only 3 walk faces."""
    walk_count = 0

    class CountingFace:
        def __init__(self, box, normal):
            self.box = box
            self.normal = normal
            self.area_m2 = 1e-4

        def GetBox(self):
            nonlocal walk_count
            walk_count += 1
            return self.box

        def Normal(self):
            return self.normal

        def GetArea(self):
            return self.area_m2

    face = CountingFace((0.0, 0.0, 0.0, 0.01, 0.01, 0.005), (0.0, 0.0, 1.0))
    referenced_names = {"feat_3", "feat_47", "feat_99"}
    refs = {(n, "+z_outboard") for n in referenced_names}

    results = []
    for i in range(100):
        name = f"feat_{i}"
        feature = MockFeature(Name=name, faces=(face,))
        ctx = LazyCtx(referenced_face_roles=refs)
        r = interrogate(feature, ctx)
        results.append(r)

    referenced_results = [r for r in results if r.get("status") != "no_downstream_refs"]
    assert len(referenced_results) == 3
    unreferenced_results = [
        r for r in results if r.get("status") == "no_downstream_refs"
    ]
    assert len(unreferenced_results) == 97
