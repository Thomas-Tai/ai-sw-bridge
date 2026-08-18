from __future__ import annotations

import pytest

from ai_sw_bridge.spec.preflight import (
    map_plane_point,
    coordinate_mapping_report,
    material_envelope_scan,
    preflight,
    _degenerate_profile_checks,
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


_PLATE = {
    "type": "sketch_rectangle_on_plane",
    "name": "SK_Plate",
    "plane": "Front",
    "width": 40.0,
    "height": 30.0,
}
_BOSS = {
    "type": "boss_extrude_blind",
    "name": "EX_Plate",
    "sketch": "SK_Plate",
    "depth": 10.0,
}


def _sev(findings, sev):
    return [f for f in findings if f.severity == sev]


def test_clean_plate_with_on_material_hole_has_no_warn_or_error():
    spec = {
        "features": [
            _PLATE,
            _BOSS,
            {
                "type": "simple_hole",
                "name": "H1",
                "of_feature": "EX_Plate",
                "face": "+z",
                "center": {"u": 10.0, "v": 0.0},
                "diameter": 5.0,
            },
        ]
    }
    findings = material_envelope_scan(spec)
    assert _sev(findings, "warning") == []
    assert _sev(findings, "error") == []


def test_hole_off_the_face_warns():
    spec = {
        "features": [
            _PLATE,
            _BOSS,
            {
                "type": "simple_hole",
                "name": "H_off",
                "of_feature": "EX_Plate",
                "face": "+z",
                "center": {"u": 50.0, "v": 0.0},  # face is X in [-20, 20]
                "diameter": 5.0,
            },
        ]
    }
    warns = _sev(material_envelope_scan(spec), "warning")
    assert any("H_off" in f.message and "off" in f.message.lower() for f in warns)


def test_empty_air_cut_errors():
    spec = {
        "features": [
            _PLATE,
            _BOSS,
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Air",
                "plane": "Front",
                "width": 5.0,
                "height": 5.0,
                "center": {"x": 100.0, "y": 100.0},  # far from the plate
            },
            {
                "type": "cut_extrude_blind",
                "name": "CUT_Air",
                "sketch": "SK_Air",
                "depth": 5.0,
            },
        ]
    }
    errs = _sev(material_envelope_scan(spec), "error")
    assert any("CUT_Air" in f.message for f in errs)


def test_revolve_is_skipped_not_flagged():
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Rev",
                "plane": "Top",
                "width": 10.0,
                "height": 10.0,
                "centerline": True,
            },
            {"type": "revolve_boss", "name": "REV", "sketch": "SK_Rev"},
            {
                "type": "cut_extrude_blind",
                "name": "CUT_X",
                "sketch": "SK_Rev",
                "depth": 2.0,
            },
        ]
    }
    findings = material_envelope_scan(spec)
    assert _sev(findings, "error") == []  # no false ERROR after an unmodeled body
    assert any(f.severity == "info" and "skip" in f.message.lower() for f in findings)


def test_flipped_cut_into_material_is_not_flagged():
    # A cut sketched on the +Z top face (Front plane, center z=10) with
    # flip=True cuts INWARD into real material (Z[5, 10]); the tracker must
    # model -normal and NOT fire a false empty-air ERROR. With the old
    # +normal-only code the box was Z[10, 15] (disjoint) -> false ERROR.
    spec = {
        "features": [
            _PLATE,
            _BOSS,  # material Z in [0, 10]
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_TopCut",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
                "center": {"z": 10.0},  # top face of the plate
            },
            {
                "type": "cut_extrude_blind",
                "name": "CUT_In",
                "sketch": "SK_TopCut",
                "depth": 5.0,
                "flip": True,  # cut -Z, into the plate
            },
        ]
    }
    assert _sev(material_envelope_scan(spec), "error") == []


def test_start_offset_boss_honest_skips_no_false_empty_air_error():
    # F1 regression: boss_extrude_blind's start_offset displaces the REAL
    # body along the plane normal (spec/handlers/extrude.py), but the
    # un-offset axis-aligned box model doesn't know that. Un-offset modeled
    # box would be Z[0, 10]; the real body is Z[20, 30]. A later cut that
    # really lands in the displaced material (Z[20, 25]) is disjoint from
    # the wrongly-placed un-offset box -> false empty-air ERROR on current
    # code. The boss must honest-skip (INFO) instead, so no false ERROR.
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "sk_base",
                "plane": "Front",
                "width": 40.0,
                "height": 40.0,
                "center": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            {
                "type": "boss_extrude_blind",
                "name": "base",
                "sketch": "sk_base",
                "depth": 10.0,
                "start_offset": 20.0,
            },
            {
                "type": "sketch_rectangle_on_plane",
                "name": "sk_cut",
                "plane": "Front",
                "width": 40.0,
                "height": 40.0,
                "center": {"x": 0.0, "y": 0.0, "z": 25.0},
            },
            {
                "type": "cut_extrude_blind",
                "name": "pocket",
                "sketch": "sk_cut",
                "depth": 5.0,
                "flip": True,
            },
        ]
    }
    findings = material_envelope_scan(spec)
    assert _sev(findings, "error") == []  # no false ERROR
    infos = _sev(findings, "info")
    assert any("base" in f.message and "skip" in f.message.lower() for f in infos)


def test_open_polyline_consumed_by_boss_warns():
    spec = {
        "features": [
            {
                "type": "sketch_polyline_on_plane",
                "name": "SK_Open",
                "plane": "Front",
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}],
                "closed": False,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX",
                "sketch": "SK_Open",
                "depth": 5.0,
            },
        ]
    }
    warns = [f for f in _degenerate_profile_checks(spec) if f.severity == "warning"]
    assert any("SK_Open" in f.message and "closed" in f.message.lower() for f in warns)


def test_preflight_aggregates_all_three_analyzers():
    spec = {"features": [_PLATE, _BOSS]}
    findings = preflight(spec)
    # coordinate echo (info) present, no warning/error on a clean plate
    assert any(f.severity == "info" for f in findings)
    assert [f for f in findings if f.severity in ("warning", "error")] == []


def test_unconsumed_construction_polyline_is_not_flagged():
    # A lone construction polyline that no boss/cut consumes must NOT warn --
    # the construction-only check is gated on being consumed, like its sibling.
    spec = {
        "features": [
            {
                "type": "sketch_polyline_on_plane",
                "name": "SK_Ref",
                "plane": "Front",
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}],
                "construction": True,
            }
        ]
    }
    warns = [f for f in _degenerate_profile_checks(spec) if f.severity == "warning"]
    assert warns == []


def test_consumed_construction_polyline_warns():
    # A construction polyline consumed by a boss has no real entities to sweep.
    spec = {
        "features": [
            {
                "type": "sketch_polyline_on_plane",
                "name": "SK_Con",
                "plane": "Front",
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}],
                "construction": True,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX",
                "sketch": "SK_Con",
                "depth": 5.0,
            },
        ]
    }
    warns = [f for f in _degenerate_profile_checks(spec) if f.severity == "warning"]
    assert any(
        "SK_Con" in f.message and "construction" in f.message.lower() for f in warns
    )


# Regression tests for rhs-driven dimensions (Task 4 crash-fix).
# The crash-fix adds _as_float() to handle {"rhs": "..."} locals references
# instead of crashing with TypeError: float() argument must be a string or a real number, not 'dict'.


def test_rhs_driven_rectangle_width_is_skipped_not_crashed():
    """Regression: coordinate_mapping_report must not crash on rhs-driven width.

    Pre-fix: float({"rhs": "X"}) -> TypeError.
    Post-fix: _as_float({"rhs": "X"}) -> None, feature is skipped (extent=None).
    """
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_RHS_Width",
                "plane": "Front",
                "width": {"rhs": "SOME_LOCAL"},  # unresolved locals ref
                "height": 30.0,
            }
        ]
    }
    # Must not raise TypeError.
    findings = coordinate_mapping_report(spec)
    # Feature skipped (no coordinate echo), so no ERROR/WARNING either.
    assert all(f.severity != "error" for f in findings)
    assert all(f.severity != "warning" for f in findings)


def test_rhs_driven_rectangle_height_is_skipped_not_crashed():
    """Regression: coordinate_mapping_report must not crash on rhs-driven height."""
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_RHS_Height",
                "plane": "Top",
                "width": 40.0,
                "height": {"rhs": "GROOVE_DEPTH"},  # unresolved locals ref
            }
        ]
    }
    # Must not raise TypeError.
    findings = coordinate_mapping_report(spec)
    # Feature skipped, so no ERROR/WARNING either.
    assert all(f.severity != "error" for f in findings)
    assert all(f.severity != "warning" for f in findings)


def test_rhs_driven_circle_diameter_is_skipped_not_crashed():
    """Regression: coordinate_mapping_report must not crash on rhs-driven diameter."""
    spec = {
        "features": [
            {
                "type": "sketch_circle_on_plane",
                "name": "SK_RHS_Diameter",
                "plane": "Front",
                "diameter": {"rhs": "BORE_SIZE"},  # unresolved locals ref
            }
        ]
    }
    # Must not raise TypeError.
    findings = coordinate_mapping_report(spec)
    # Feature skipped, so no ERROR/WARNING either.
    assert all(f.severity != "error" for f in findings)
    assert all(f.severity != "warning" for f in findings)


def test_rhs_driven_extrude_depth_is_skipped_not_crashed():
    """Regression: material_envelope_scan must not crash on rhs-driven depth.

    Pre-fix: float({"rhs": "X"}) -> TypeError in _rect_uv_extent or material_envelope_scan.
    Post-fix: _as_float({"rhs": "X"}) -> None, feature marked incomplete (modeled_complete=False).
    """
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Plate",
                "plane": "Front",
                "width": 40.0,
                "height": 30.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_RHS_Depth",
                "sketch": "SK_Plate",
                "depth": {"rhs": "EXTRUDE_LENGTH"},  # unresolved locals ref
            },
        ]
    }
    # Must not raise TypeError.
    findings = material_envelope_scan(spec)
    # Feature skipped (depth unresolved), marked incomplete; no false ERROR/WARNING.
    assert all(f.severity != "error" for f in findings)
    assert all(f.severity != "warning" for f in findings)


def test_rhs_driven_cut_depth_is_skipped_not_crashed():
    """Regression: material_envelope_scan must not crash on rhs-driven cut depth."""
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Plate",
                "plane": "Front",
                "width": 40.0,
                "height": 30.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Plate",
                "sketch": "SK_Plate",
                "depth": 10.0,
            },
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Pocket",
                "plane": "Front",
                "width": 5.0,
                "height": 5.0,
                "center": {"x": 0.0, "y": 0.0},
            },
            {
                "type": "cut_extrude_blind",
                "name": "CUT_RHS_Depth",
                "sketch": "SK_Pocket",
                "depth": {"rhs": "POCKET_DEPTH"},  # unresolved locals ref
            },
        ]
    }
    # Must not raise TypeError.
    findings = material_envelope_scan(spec)
    # Feature skipped (depth unresolved), marked incomplete; no false ERROR.
    assert all(f.severity != "error" for f in findings)
