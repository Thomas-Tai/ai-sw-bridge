"""Tests for ai_sw_bridge.spec.validator."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from ai_sw_bridge.spec.validator import (
    ValidationError,
    _strip_comments,
    validate,
)


# -----------------------------------------------------------------------------
# Happy path: example specs validate
# -----------------------------------------------------------------------------


def test_validate_accepts_cylinder_spec(
    cylinder_spec: dict, cylinder_spec_path: Path
) -> None:
    # Cylinder spec's `locals` is a relative path -- the validator resolves
    # it against the spec file's directory when spec_path is supplied.
    # Safety net: skip if the locals file is somehow missing (e.g. a fresh
    # checkout where the file wasn't pulled), mirroring the MMP pattern.
    resolved_locals = (cylinder_spec_path.parent / cylinder_spec["locals"]).resolve()
    if not resolved_locals.exists():
        pytest.skip(f"cylinder locals file not present: {resolved_locals}")
    validate(cylinder_spec, spec_path=cylinder_spec_path)


def test_validate_accepts_mmp_spec(mmp_spec: dict) -> None:
    # MMP spec references a locals file under the Lego Sorter repo. If that
    # file doesn't exist on this machine, skip rather than fail (it's an
    # integration-with-other-repo concern).
    if not Path(mmp_spec["locals"]).exists():
        pytest.skip(f"MMP locals file not present: {mmp_spec['locals']}")
    validate(mmp_spec)


# -----------------------------------------------------------------------------
# _strip_comments()
# -----------------------------------------------------------------------------


def test_strip_comments_removes_underscore_keys_at_top_level() -> None:
    node = {"_comment": "x", "name": "P", "features": []}
    out = _strip_comments(node)
    assert "_comment" not in out
    assert out == {"name": "P", "features": []}


def test_strip_comments_removes_underscore_keys_at_any_depth() -> None:
    node = {
        "features": [
            {"_comment": "nested", "type": "T", "sub": {"_note": "z", "ok": 1}},
        ],
    }
    out = _strip_comments(node)
    assert "_comment" not in out["features"][0]
    assert "_note" not in out["features"][0]["sub"]
    assert out["features"][0]["sub"] == {"ok": 1}


def test_strip_comments_preserves_non_dict_values() -> None:
    assert _strip_comments(5) == 5
    assert _strip_comments("hello") == "hello"
    assert _strip_comments([1, 2, 3]) == [1, 2, 3]


# -----------------------------------------------------------------------------
# Reference checks
# -----------------------------------------------------------------------------


def _minimal_spec() -> dict:
    """A clean minimal spec: one sketch + one extrude. All literal, no locals."""
    return {
        "schema_version": 1,
        "name": "MinSpec",
        "features": [
            {
                "type": "sketch_circle_on_plane",
                "name": "SK_A",
                "plane": "Front",
                "diameter": 25.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_A",
                "sketch": "SK_A",
                "depth": 10.0,
            },
        ],
    }


def test_reference_fails_when_sketch_points_to_unknown_feature() -> None:
    spec = _minimal_spec()
    spec["features"][1]["sketch"] = "DoesNotExist"
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "DoesNotExist" in str(exc.value)


def test_reference_fails_when_sketch_points_to_non_sketch() -> None:
    spec = _minimal_spec()
    # Add a second extrude pointing at the first extrude as its "sketch"
    spec["features"].append(
        {
            "type": "boss_extrude_blind",
            "name": "EX_B",
            "sketch": "EX_A",  # not a sketch
            "depth": 5.0,
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    msg = str(exc.value)
    assert "sketch" in msg.lower()
    assert "EX_A" in msg


def test_reference_fails_when_of_feature_points_to_non_extrusion() -> None:
    spec = _minimal_spec()
    # Add a circle-on-face that references a SKETCH (not an extrusion)
    spec["features"].append(
        {
            "type": "sketch_circle_on_face",
            "name": "SK_Hole",
            "of_feature": "SK_A",  # SK_A is a sketch, not an extrusion
            "face": "+z",
            "diameter": 5.0,
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    msg = str(exc.value)
    assert "extrusion" in msg.lower()
    assert "SK_A" in msg


def test_reference_enforces_topological_order() -> None:
    """The extrude must come AFTER its sketch in the features list."""
    spec = _minimal_spec()
    # Swap order: extrude before sketch
    spec["features"] = [spec["features"][1], spec["features"][0]]
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "earlier" in str(exc.value).lower() or "not" in str(exc.value).lower()


# -----------------------------------------------------------------------------
# Locals checks
# -----------------------------------------------------------------------------


def test_locals_fails_when_rhs_used_but_no_locals_path() -> None:
    spec = _minimal_spec()
    spec["features"][0]["diameter"] = {"rhs": '"FOO"'}
    # Intentionally NO `locals` key
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    msg = str(exc.value)
    assert "locals" in msg.lower()


def test_locals_fails_when_rhs_references_unknown_variable(tmp_path: Path) -> None:
    locals_file = tmp_path / "locals.txt"
    locals_file.write_text('"OTHER" = 1.0\n', encoding="utf-8")

    spec = _minimal_spec()
    spec["locals"] = str(locals_file)
    spec["features"][0]["diameter"] = {"rhs": '"MISSING"'}

    with pytest.raises(ValidationError) as exc:
        validate(spec)
    msg = str(exc.value)
    assert "MISSING" in msg


def test_locals_passes_when_all_refs_resolve(tmp_path: Path) -> None:
    locals_file = tmp_path / "locals.txt"
    locals_file.write_text(
        '"D" = 25.0\n"L" = 80.0\n',
        encoding="utf-8",
    )

    spec = _minimal_spec()
    spec["locals"] = str(locals_file)
    spec["features"][0]["diameter"] = {"rhs": '"D"'}
    spec["features"][1]["depth"] = {"rhs": '"L"'}

    # Should not raise
    validate(spec)


# -----------------------------------------------------------------------------
# ValidationError API (positional + kwargs constructor)
# -----------------------------------------------------------------------------


def test_validation_error_positional_constructor() -> None:
    err = ValidationError("something broke", "features/0/name")
    assert err.message == "something broke"
    assert err.path == "features/0/name"
    assert "features/0/name" in str(err)
    assert "something broke" in str(err)


def test_validation_error_kwargs_constructor() -> None:
    err = ValidationError(message="boom", path="$/locals")
    assert err.message == "boom"
    assert err.path == "$/locals"


def test_validation_error_is_exception_subclass() -> None:
    # @dataclass on Exception would break .args; verify it is intact.
    err = ValidationError("msg", "p")
    assert isinstance(err, Exception)
    assert err.args == ("msg",)


def test_validation_error_path_optional() -> None:
    err = ValidationError("msg")
    assert err.path == ""
    assert str(err) == "msg"


# -----------------------------------------------------------------------------
# v0.3 primitives: chamfer / linear_pattern / mirror_feature
# -----------------------------------------------------------------------------


def _spec_with_box_and(*extra_features: dict) -> dict:
    """Minimal spec: sketch + extrude + the extra features. The extra features
    reference 'EX_Box' as their seed/edge target when needed."""
    return {
        "schema_version": 1,
        "name": "BoxPlus",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 20.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 10.0,
            },
            *extra_features,
        ],
    }


# --- chamfer_edge -----------------------------------------------------------


def test_chamfer_equal_distance_accepts_distance_only() -> None:
    spec = _spec_with_box_and(
        {
            "type": "chamfer_edge",
            "name": "Ch1",
            "mode": "equal_distance",
            "distance": 1.0,
            "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}],
        }
    )
    validate(spec)


def test_chamfer_equal_distance_rejects_angle() -> None:
    spec = _spec_with_box_and(
        {
            "type": "chamfer_edge",
            "name": "Ch1",
            "mode": "equal_distance",
            "distance": 1.0,
            "angle": 45.0,
            "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}],
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "angle" in str(exc.value).lower()


def test_chamfer_distance_angle_requires_both() -> None:
    spec = _spec_with_box_and(
        {
            "type": "chamfer_edge",
            "name": "Ch1",
            "mode": "distance_angle",
            "distance": 1.0,
            # angle missing
            "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}],
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "angle" in str(exc.value).lower()


def test_chamfer_distance_angle_accepts_both() -> None:
    spec = _spec_with_box_and(
        {
            "type": "chamfer_edge",
            "name": "Ch1",
            "mode": "distance_angle",
            "distance": 1.0,
            "angle": 30.0,
            "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}],
        }
    )
    validate(spec)


def test_chamfer_requires_at_least_one_edge() -> None:
    spec = _spec_with_box_and(
        {
            "type": "chamfer_edge",
            "name": "Ch1",
            "mode": "equal_distance",
            "distance": 1.0,
            "edges": [],
        }
    )
    with pytest.raises(ValidationError):
        validate(spec)


def test_chamfer_rejects_unknown_mode() -> None:
    spec = _spec_with_box_and(
        {
            "type": "chamfer_edge",
            "name": "Ch1",
            "mode": "vertex",  # not yet supported
            "distance": 1.0,
            "edges": [{"x": 10.0, "y": 0.0, "z": 10.0}],
        }
    )
    with pytest.raises(ValidationError):
        validate(spec)


# --- linear_pattern ---------------------------------------------------------


def test_linear_pattern_accepts_valid_spec() -> None:
    spec = _spec_with_box_and(
        {
            "type": "linear_pattern",
            "name": "LP1",
            "seed": "EX_Box",
            "direction": {"x": 10.0, "y": 0.0, "z": 10.0},
            "count": 3,
            "spacing": 5.0,
        }
    )
    validate(spec)


def test_linear_pattern_seed_must_exist() -> None:
    spec = _spec_with_box_and(
        {
            "type": "linear_pattern",
            "name": "LP1",
            "seed": "NotAFeature",
            "direction": {"x": 10.0, "y": 0.0, "z": 10.0},
            "count": 3,
            "spacing": 5.0,
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "NotAFeature" in str(exc.value)


def test_linear_pattern_count_must_be_at_least_2() -> None:
    spec = _spec_with_box_and(
        {
            "type": "linear_pattern",
            "name": "LP1",
            "seed": "EX_Box",
            "direction": {"x": 10.0, "y": 0.0, "z": 10.0},
            "count": 1,
            "spacing": 5.0,
        }
    )
    with pytest.raises(ValidationError):
        validate(spec)


def test_linear_pattern_requires_direction() -> None:
    spec = _spec_with_box_and(
        {
            "type": "linear_pattern",
            "name": "LP1",
            "seed": "EX_Box",
            # direction missing
            "count": 3,
            "spacing": 5.0,
        }
    )
    with pytest.raises(ValidationError):
        validate(spec)


# --- mirror_feature ---------------------------------------------------------


def test_mirror_feature_accepts_valid_spec() -> None:
    spec = _spec_with_box_and(
        {
            "type": "mirror_feature",
            "name": "Mir1",
            "seed": "EX_Box",
            "plane": "Right",
        }
    )
    validate(spec)


def test_mirror_feature_seed_must_exist() -> None:
    spec = _spec_with_box_and(
        {
            "type": "mirror_feature",
            "name": "Mir1",
            "seed": "Nope",
            "plane": "Front",
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "Nope" in str(exc.value)


def test_mirror_feature_rejects_unknown_plane() -> None:
    spec = _spec_with_box_and(
        {
            "type": "mirror_feature",
            "name": "Mir1",
            "seed": "EX_Box",
            "plane": "Diagonal",  # not a default plane
        }
    )
    with pytest.raises(ValidationError):
        validate(spec)


# --- revolve_boss -----------------------------------------------------------


def _revolve_spec_with(sketch: dict, revolve: dict) -> dict:
    return {
        "schema_version": 1,
        "name": "RevolveTest",
        "features": [sketch, revolve],
    }


def test_revolve_boss_accepts_sketch_with_centerline() -> None:
    spec = _revolve_spec_with(
        sketch={
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Prof",
            "plane": "Front",
            "width": 30.0,
            "height": 6.0,
            "center": {"x": 35.0, "y": 5.0},
            "centerline": {
                "start": {"x": -60.0, "y": 0.0},
                "end": {"x": 60.0, "y": 0.0},
            },
        },
        revolve={
            "type": "revolve_boss",
            "name": "REV1",
            "sketch": "SK_Prof",
            "angle": 360.0,
        },
    )
    validate(spec)


def test_revolve_boss_rejects_sketch_without_centerline() -> None:
    spec = _revolve_spec_with(
        sketch={
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Prof",
            "plane": "Front",
            "width": 30.0,
            "height": 6.0,
            "center": {"x": 35.0, "y": 5.0},
            # no centerline
        },
        revolve={
            "type": "revolve_boss",
            "name": "REV1",
            "sketch": "SK_Prof",
        },
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "centerline" in str(exc.value).lower()


def test_revolve_boss_rejects_missing_sketch_ref() -> None:
    spec = {
        "schema_version": 1,
        "name": "RevolveTest",
        "features": [
            {
                "type": "revolve_boss",
                "name": "REV1",
                "sketch": "SK_DoesNotExist",
            }
        ],
    }
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "earlier" in str(exc.value).lower() or "not" in str(exc.value).lower()


def test_revolve_boss_rejects_angle_above_360() -> None:
    spec = _revolve_spec_with(
        sketch={
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Prof",
            "plane": "Front",
            "width": 30.0,
            "height": 6.0,
            "center": {"x": 35.0, "y": 5.0},
            "centerline": {
                "start": {"x": -60.0, "y": 0.0},
                "end": {"x": 60.0, "y": 0.0},
            },
        },
        revolve={
            "type": "revolve_boss",
            "name": "REV1",
            "sketch": "SK_Prof",
            "angle": 450.0,  # > 360 -- schema rejects
        },
    )
    with pytest.raises(ValidationError):
        validate(spec)


# --- revolve_cut ------------------------------------------------------------
# Same shape as revolve_boss tests; revolve_cut shares schema structure with
# the boss variant (only the `type` const differs) and the same centerline
# validator rule.


def test_revolve_cut_accepts_sketch_with_centerline() -> None:
    spec = _revolve_spec_with(
        sketch={
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Prof",
            "plane": "Front",
            "width": 30.0,
            "height": 6.0,
            "center": {"x": 35.0, "y": 5.0},
            "centerline": {
                "start": {"x": -60.0, "y": 0.0},
                "end": {"x": 60.0, "y": 0.0},
            },
        },
        revolve={
            "type": "revolve_cut",
            "name": "CUT1",
            "sketch": "SK_Prof",
            "angle": 360.0,
        },
    )
    validate(spec)


def test_revolve_cut_rejects_sketch_without_centerline() -> None:
    spec = _revolve_spec_with(
        sketch={
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Prof",
            "plane": "Front",
            "width": 30.0,
            "height": 6.0,
            "center": {"x": 35.0, "y": 5.0},
        },
        revolve={
            "type": "revolve_cut",
            "name": "CUT1",
            "sketch": "SK_Prof",
        },
    )
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "centerline" in str(exc.value).lower()


def test_revolve_cut_rejects_missing_sketch_ref() -> None:
    spec = {
        "schema_version": 1,
        "name": "RevolveCutTest",
        "features": [
            {
                "type": "revolve_cut",
                "name": "CUT1",
                "sketch": "SK_DoesNotExist",
            }
        ],
    }
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "earlier" in str(exc.value).lower() or "not" in str(exc.value).lower()


def test_revolve_cut_rejects_angle_above_360() -> None:
    spec = _revolve_spec_with(
        sketch={
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Prof",
            "plane": "Front",
            "width": 30.0,
            "height": 6.0,
            "center": {"x": 35.0, "y": 5.0},
            "centerline": {
                "start": {"x": -60.0, "y": 0.0},
                "end": {"x": 60.0, "y": 0.0},
            },
        },
        revolve={
            "type": "revolve_cut",
            "name": "CUT1",
            "sketch": "SK_Prof",
            "angle": 450.0,
        },
    )
    with pytest.raises(ValidationError):
        validate(spec)


# -----------------------------------------------------------------------------
# _expect block validation
# -----------------------------------------------------------------------------


def test_expect_with_valid_shape_passes() -> None:
    spec = _minimal_spec()
    spec["features"][0]["_expect"] = {"mass_delta_mm3": 490.9}
    spec["features"][1]["_expect"] = {"mass_delta_mm3": 4909.0, "tolerance_mm3": 10.0}
    validate(spec)


def test_expect_with_negative_tolerance_fails() -> None:
    spec = _minimal_spec()
    spec["features"][0]["_expect"] = {"mass_delta_mm3": 100.0, "tolerance_mm3": -5.0}
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "tolerance" in str(exc.value).lower() or "_expect" in str(exc.value)


def test_expect_missing_mass_delta_fails() -> None:
    spec = _minimal_spec()
    spec["features"][0]["_expect"] = {"tolerance_mm3": 5.0}
    with pytest.raises(ValidationError) as exc:
        validate(spec)
    assert "_expect" in str(exc.value)


def test_expect_on_feature_without_other_issues_does_not_break_validation() -> None:
    """A valid _expect block on a valid feature should not interfere."""
    spec = _minimal_spec()
    spec["features"][1]["_expect"] = {"mass_delta_mm3": 4909.0}
    validate(spec)  # should not raise


def test_expect_negative_mass_delta_passes() -> None:
    """Cuts have negative mass delta."""
    spec = {
        "schema_version": 1,
        "name": "CutTest",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 20.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 10.0,
                "_expect": {"mass_delta_mm3": 4000.0},
            },
            {
                "type": "sketch_circle_on_plane",
                "name": "SK_Hole",
                "plane": "Front",
                "diameter": 5.0,
            },
            {
                "type": "cut_extrude_through_all",
                "name": "CUT_Hole",
                "sketch": "SK_Hole",
                "_expect": {"mass_delta_mm3": -196.3, "tolerance_mm3": 2.0},
            },
        ],
    }
    validate(spec)
