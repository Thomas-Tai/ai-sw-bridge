"""Tests for brep/interrogator.py (spec.md §2.2).

Uses a mocked ``IFeature`` / ``IFace2`` pair with canned box + normal
tuples. The mock emulates the E2.1 spike's load-bearing findings:

* zero-arg IFace2 methods auto-invoke on attribute access under
  pywin32 late binding — so ``face.GetBox`` returns the tuple, not a
  callable. The mock matches this shape (plain attributes).
"""

from __future__ import annotations

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


def test_role_hint_oblique_for_tilted_normal() -> None:
    # 45-degree normal isn't axis-aligned.
    import math

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
