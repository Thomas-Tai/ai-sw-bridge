"""Guardrail: all six extrusion faces are sketchable (locks known_limitations #2).

The docs once claimed ``+x``/``-x``/``+y``/``-y`` faces raise
``NotImplementedError``. They do not -- ``_face_frame`` computes a part-frame
transform for every face. This test fires all six offline (pure geometry, no
COM) so the doc claim and the code can't diverge again. Side faces additionally
require a rectangular, ``+z``-axis (Front Plane) parent, which the fixture
provides.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_sw_bridge.spec._build_context import BuiltFeature
from ai_sw_bridge.spec._face_geometry import (
    FaceFrame,
    _face_frame,
    _sketch_uv_to_part,
)

_ROOT = Path(__file__).resolve().parents[2]

_EXPECTED_NORMAL = {
    "+z": (0.0, 0.0, 1.0),
    "-z": (0.0, 0.0, -1.0),
    "+x": (1.0, 0.0, 0.0),
    "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 1.0, 0.0),
    "-y": (0.0, -1.0, 0.0),
}


def _rectangular_plusz_parent() -> BuiltFeature:
    # A 20x20x10mm box extruded +z on the Front Plane, centered on the origin --
    # the parent orientation/profile that makes all six faces addressable.
    return BuiltFeature(
        name="Extrude_Box",
        type="boss_extrude_blind",
        extrude_axis=(0.0, 0.0, 1.0),
        extrude_origin=(0.0, 0.0, 0.0),
        extrude_depth_m=0.010,
        extrude_flip=False,
        sketch_extent_uv=(0.010, 0.010),
    )


@pytest.mark.parametrize("face", ["+z", "-z", "+x", "-x", "+y", "-y"])
def test_all_six_faces_resolve_a_frame(face: str) -> None:
    frame = _face_frame(_rectangular_plusz_parent(), face)
    assert isinstance(frame, FaceFrame)
    assert frame.out_normal == _EXPECTED_NORMAL[face]


# --- Side faces of Top/Right-plane (±y/±x-axis) parents (Tasks #14/#15).
# face_center + out_normal are measured-correct (so fillet/chamfer semantic edge
# selection resolves, #14), and the sketch u/v frames for the +y/+x (non-flipped)
# orientations are SW's own calibrated frames (#15), so sketch-on-face works too.
# Face names are sketch-LOCAL (+x/+y = the +u/+v side), so on non-Front parents
# they map to different PART axes. All values measured on a live seat.
_SIDE_NORMALS_TOP = {  # Top plane, axis +y: u->+x, v->+z
    "+x": (1.0, 0.0, 0.0),
    "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 0.0, 1.0),
    "-y": (0.0, 0.0, -1.0),
}
_SIDE_NORMALS_RIGHT = {  # Right plane, axis +x: u->+z, v->+y
    "+x": (0.0, 0.0, 1.0),
    "-x": (0.0, 0.0, -1.0),
    "+y": (0.0, 1.0, 0.0),
    "-y": (0.0, -1.0, 0.0),
}
# SW's native sketch (u, v) axes on each side face (#15 ISketch transform read).
_SIDE_UV_TOP = {
    "+x": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    "-x": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    "+y": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "-y": ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}
_SIDE_UV_RIGHT = {
    "+x": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "-x": ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "+y": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "-y": ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
}


def _parent(axis: tuple[float, float, float]) -> BuiltFeature:
    return BuiltFeature(
        name="Extrude_Box",
        type="boss_extrude_blind",
        extrude_axis=axis,
        extrude_origin=(0.0, 0.0, 0.0),
        extrude_depth_m=0.010,
        extrude_flip=False,
        sketch_extent_uv=(0.020, 0.010),
    )


@pytest.mark.parametrize("face", ["+x", "-x", "+y", "-y"])
def test_top_plane_side_faces_calibrated(face: str) -> None:
    frame = _face_frame(_parent((0.0, 1.0, 0.0)), face)
    assert frame.out_normal == _SIDE_NORMALS_TOP[face]
    assert frame.uv_calibrated is True
    assert (frame.u_axis, frame.v_axis) == _SIDE_UV_TOP[face]
    # Face center sits mid-depth (y = +0.005) on the box surface.
    assert abs(frame.face_center[1] - 0.005) < 1e-9


@pytest.mark.parametrize("face", ["+x", "-x", "+y", "-y"])
def test_right_plane_side_faces_calibrated(face: str) -> None:
    frame = _face_frame(_parent((1.0, 0.0, 0.0)), face)
    assert frame.out_normal == _SIDE_NORMALS_RIGHT[face]
    assert frame.uv_calibrated is True
    assert (frame.u_axis, frame.v_axis) == _SIDE_UV_RIGHT[face]
    assert abs(frame.face_center[0] - 0.005) < 1e-9


def test_front_plane_side_faces_stay_calibrated() -> None:
    # Regression guard: Front-plane side faces keep the calibrated frame.
    frame = _face_frame(_rectangular_plusz_parent(), "+x")
    assert frame.uv_calibrated is True


def test_calibrated_side_face_places_child_sketch() -> None:
    # A Top-plane +x side face now accepts a child sketch: u along +z, v along
    # +y (into the face) from the origin projection at (0.02, 0, 0).
    frame = _face_frame(_parent((0.0, 1.0, 0.0)), "+x")
    px, py, pz = _sketch_uv_to_part(frame, 0.003, 0.002)
    assert abs(px - 0.020) < 1e-9  # on the +x face plane
    assert abs(py - 0.002) < 1e-9  # v -> +y
    assert abs(pz - 0.003) < 1e-9  # u -> +z


def test_unmeasured_orientation_refuses_sketch_on_face() -> None:
    # A -y-axis (flipped Top) parent is not among the measured orientations, so
    # its side faces stay uncalibrated and sketch-on-face is refused.
    frame = _face_frame(_parent((0.0, -1.0, 0.0)), "+x")
    assert frame.uv_calibrated is False
    with pytest.raises(RuntimeError, match="not yet supported"):
        _sketch_uv_to_part(frame, 0.001, 0.001)


def test_non_axis_aligned_parent_side_face_raises() -> None:
    parent = _parent((0.6, 0.8, 0.0))  # not axis-aligned
    with pytest.raises(RuntimeError, match="not axis-aligned"):
        _face_frame(parent, "+x")


def test_side_face_without_rect_extents_raises_documented_error() -> None:
    # A +z parent with no rectangular half-extents (e.g. a circle profile).
    parent = BuiltFeature(
        name="Extrude_Box",
        type="boss_extrude_blind",
        extrude_axis=(0.0, 0.0, 1.0),
        extrude_origin=(0.0, 0.0, 0.0),
        extrude_depth_m=0.010,
        extrude_flip=False,
        sketch_extent_uv=None,
    )
    with pytest.raises(RuntimeError, match="sketch_extent_uv"):
        _face_frame(parent, "+x")


def test_fillet_edge_error_string_quoted_in_doc_matches_source() -> None:
    # The fillet edge-selector string is raised behind a COM call (not unit-
    # reachable offline), so pin the doc quote to the source verbatim instead.
    # Lives in handlers/dress_up.py (Phase 3 Move 4), not builder.py.
    needle = "matches no edge within 1um"
    dress_up = (
        _ROOT / "src" / "ai_sw_bridge" / "spec" / "handlers" / "dress_up.py"
    ).read_text(encoding="utf-8")
    doc = (_ROOT / "docs" / "known_limitations.md").read_text(encoding="utf-8")
    assert (
        needle in dress_up
    ), "fillet edge-selector error string changed in dress_up.py"
    assert needle in doc, "known_limitations.md no longer quotes the live fillet error"
