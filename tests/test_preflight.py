from __future__ import annotations

import pytest

from ai_sw_bridge.spec.preflight import (
    map_plane_point,
    coordinate_mapping_report,
)


def test_map_front_is_identity_xy():
    assert map_plane_point("Front", 10.0, 5.0, 0.0) == (10.0, 5.0, 0.0)


def test_map_top_v_maps_to_negative_z():
    # Top (XZ, normal +Y): u->X, v->-Z, offset->Y
    assert map_plane_point("Top", 10.0, 5.0, 40.0) == (10.0, 40.0, -5.0)


def test_map_right_u_maps_to_negative_z():
    # Right (YZ, normal +X): u->-Z, v->Y, offset->X
    assert map_plane_point("Right", 10.0, 5.0, 0.0) == (0.0, 5.0, -10.0)


def test_coordinate_echo_reports_part_spans_for_top_rect():
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Groove",
                "plane": "Top",
                "width": 40.0,
                "height": 30.0,
            }
        ]
    }
    findings = coordinate_mapping_report(spec)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "info"
    # width(u)->X spans [-20,20]; height(v)->-Z spans [-15,15]
    assert "X[-20.0, 20.0]" in f.message
    assert "Z[-15.0, 15.0]" in f.message


def test_coordinate_echo_ignores_on_face_sketches():
    # on-face sketches have no plane; they are Component-2 territory
    spec = {"features": [{"type": "simple_hole", "name": "H", "face": "+z"}]}
    assert coordinate_mapping_report(spec) == []


def test_top_rect_with_offset_center_shifts_z_span():
    # O-ring groove at mid-length of a +Z shaft: Top plane, center z=40.
    # center.z must map through v->-Z so the span centers on Z=40, not 0.
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Groove",
                "plane": "Top",
                "width": 40.0,
                "height": 30.0,
                "center": {"x": 0.0, "z": 40.0},
            }
        ]
    }
    f = coordinate_mapping_report(spec)[0]
    assert "Z[25.0, 55.0]" in f.message  # 40 +/- 15, not [-15, 15]


def test_map_plane_point_unknown_plane_raises():
    with pytest.raises(KeyError):
        map_plane_point("Bogus", 0.0, 0.0, 0.0)
