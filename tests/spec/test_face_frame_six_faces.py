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
from ai_sw_bridge.spec._face_geometry import FaceFrame, _face_frame

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


# --- Lock the two side-face error strings that known_limitations.md S2 quotes.
# These are the exact doc<->code drift this batch fixed: if the message text
# changes, the doc quote must change too, and these tests force that.


def test_side_face_on_non_frontplane_parent_raises_documented_error() -> None:
    # A Top-Plane (+y axis) parent: side faces are not addressable.
    parent = BuiltFeature(
        name="Extrude_Box",
        type="boss_extrude_blind",
        extrude_axis=(0.0, 1.0, 0.0),
        extrude_origin=(0.0, 0.0, 0.0),
        extrude_depth_m=0.010,
        extrude_flip=False,
        sketch_extent_uv=(0.010, 0.010),
    )
    with pytest.raises(RuntimeError, match="only supports"):
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
    needle = "matches no edge within 1um"
    builder = (_ROOT / "src" / "ai_sw_bridge" / "spec" / "builder.py").read_text(
        encoding="utf-8"
    )
    doc = (_ROOT / "docs" / "known_limitations.md").read_text(encoding="utf-8")
    assert needle in builder, "fillet edge-selector error string changed in builder.py"
    assert needle in doc, "known_limitations.md no longer quotes the live fillet error"
