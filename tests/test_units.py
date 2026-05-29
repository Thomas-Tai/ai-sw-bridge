"""Tests for ai_sw_bridge.units — the inch→mm conversion chokepoint.

Pure-Python module; no SOLIDWORKS, no filesystem, no network. Every test
runs under the mock adapter (i.e. in plain CI)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.units import (
    DEFAULT_UNIT,
    LENGTH_FIELDS,
    MM_PER_INCH,
    SpecUnit,
    convert_spec_units,
    inch_to_mm,
    parse_unit,
)


# -----------------------------------------------------------------------------
# parse_unit
# -----------------------------------------------------------------------------


def test_parse_unit_none_returns_default() -> None:
    assert parse_unit(None) is DEFAULT_UNIT
    assert DEFAULT_UNIT is SpecUnit.MM


def test_parse_unit_accepts_enum_member_directly() -> None:
    assert parse_unit(SpecUnit.INCH) is SpecUnit.INCH
    assert parse_unit(SpecUnit.MM) is SpecUnit.MM


def test_parse_unit_accepts_lowercase_strings() -> None:
    assert parse_unit("mm") is SpecUnit.MM
    assert parse_unit("inch") is SpecUnit.INCH


def test_parse_unit_is_case_insensitive_and_strips_whitespace() -> None:
    assert parse_unit("Inch") is SpecUnit.INCH
    assert parse_unit("  INCH  ") is SpecUnit.INCH
    assert parse_unit("MM") is SpecUnit.MM


def test_parse_unit_rejects_unknown_string() -> None:
    with pytest.raises(ValueError):
        parse_unit("cm")
    with pytest.raises(ValueError):
        parse_unit("")


def test_parse_unit_rejects_non_string_types() -> None:
    for bad in (1, 1.0, True, [], {}):
        with pytest.raises(ValueError):
            parse_unit(bad)


# -----------------------------------------------------------------------------
# inch_to_mm
# -----------------------------------------------------------------------------


def test_inch_to_mm_zero_is_exact() -> None:
    assert inch_to_mm(0.0) == 0.0
    assert inch_to_mm(0) == 0.0


def test_inch_to_mm_one_is_exact_25_4() -> None:
    # 1 international inch is exactly 25.4 mm (NIST definition).
    assert inch_to_mm(1.0) == 25.4
    assert inch_to_mm(1) == 25.4


def test_inch_to_mm_common_fractional_values() -> None:
    # 1/16" is a machinist's staple — must land within float-ULP of 1.5875 mm.
    assert inch_to_mm(1 / 16) == pytest.approx(1.5875)
    assert inch_to_mm(0.5) == pytest.approx(12.7)
    assert inch_to_mm(2.5) == pytest.approx(63.5)


def test_inch_to_mm_roundtrip_with_inverse() -> None:
    value_in = 3.14159
    mm = inch_to_mm(value_in)
    back = mm / MM_PER_INCH
    assert back == pytest.approx(value_in)


def test_inch_to_mm_preserves_sign_and_handles_negative() -> None:
    # Negative lengths aren't typical in specs, but the math must be odd
    # (sign-preserving) so offset arithmetic works.
    assert inch_to_mm(-1.0) == pytest.approx(-25.4)


def test_inch_to_mm_rejects_non_numeric() -> None:
    for bad in ("1.0", None, [1.0], {"rhs": "1"}, object()):
        with pytest.raises(TypeError):
            inch_to_mm(bad)  # type: ignore[arg-type]


def test_inch_to_mm_rejects_bool() -> None:
    # bool is a subclass of int in Python; we must not silently treat True
    # as 1 inch.
    with pytest.raises(TypeError):
        inch_to_mm(True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        inch_to_mm(False)  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# LENGTH_FIELDS
# -----------------------------------------------------------------------------


def test_length_fields_includes_v1_length_names() -> None:
    # Every LENGTH_SCHEMA-tagged field in spec/schema.py must be listed.
    for name in ("width", "height", "depth", "radius", "diameter"):
        assert name in LENGTH_FIELDS


def test_length_fields_includes_positional_coords() -> None:
    # center u/v, edge xyz, centerline start/end xy.
    for name in ("x", "y", "z", "u", "v"):
        assert name in LENGTH_FIELDS


def test_length_fields_is_frozen() -> None:
    assert isinstance(LENGTH_FIELDS, frozenset)


# -----------------------------------------------------------------------------
# convert_spec_units — mm is a true no-op
# -----------------------------------------------------------------------------


def test_convert_returns_input_unchanged_for_mm() -> None:
    spec = {"schema_version": 1, "features": [{"depth": 10.0}]}
    out = convert_spec_units(spec, "mm")
    # Same object — no copy, no allocation.
    assert out is spec


def test_convert_returns_input_unchanged_for_none() -> None:
    spec = {"schema_version": 1, "features": [{"depth": 10.0}]}
    assert convert_spec_units(spec, None) is spec


def test_convert_returns_input_unchanged_for_default_enum() -> None:
    spec = {"schema_version": 1}
    assert convert_spec_units(spec, SpecUnit.MM) is spec


# -----------------------------------------------------------------------------
# convert_spec_units — inch scales every length field, recursively
# -----------------------------------------------------------------------------


def test_convert_inch_scales_top_level_lengths() -> None:
    spec = {"width": 2.0, "height": 1.0, "name": "plate"}
    out = convert_spec_units(spec, "inch")
    assert out["width"] == pytest.approx(50.8)
    assert out["height"] == pytest.approx(25.4)
    # Non-length fields untouched.
    assert out["name"] == "plate"


def test_convert_inch_is_a_deep_copy() -> None:
    spec = {"features": [{"depth": 1.0}]}
    out = convert_spec_units(spec, "inch")
    assert out is not spec
    assert out["features"] is not spec["features"]
    assert out["features"][0] is not spec["features"][0]
    # Source unchanged.
    assert spec["features"][0]["depth"] == 1.0


def test_convert_inch_walks_into_nested_features() -> None:
    spec = {
        "schema_version": 1,
        "features": [
            {"type": "sketch_rectangle_on_plane", "width": 4.0, "height": 2.0},
            {"type": "boss_extrude_blind", "depth": 0.5},
            {"type": "fillet_constant_radius", "radius": 0.125},
        ],
    }
    out = convert_spec_units(spec, "inch")
    feats = out["features"]
    assert feats[0]["width"] == pytest.approx(101.6)
    assert feats[0]["height"] == pytest.approx(50.8)
    assert feats[1]["depth"] == pytest.approx(12.7)
    assert feats[2]["radius"] == pytest.approx(3.175)


def test_convert_inch_walks_into_arrays_of_objects() -> None:
    # sketch_circles_on_face carries a circles[] array with diameter per
    # entry — the walker must descend into list items.
    spec = {
        "features": [
            {
                "type": "sketch_circles_on_face",
                "circles": [
                    {"u": 0.0, "v": 0.0, "diameter": 0.25},
                    {"u": 1.0, "v": 0.5, "diameter": 0.5},
                ],
            }
        ]
    }
    out = convert_spec_units(spec, "inch")
    circles = out["features"][0]["circles"]
    assert circles[0]["diameter"] == pytest.approx(6.35)
    assert circles[1]["diameter"] == pytest.approx(12.7)
    # Positional u/v also scaled.
    assert circles[1]["u"] == pytest.approx(25.4)
    assert circles[1]["v"] == pytest.approx(12.7)


def test_convert_inch_passes_through_rhs_bindings() -> None:
    # A {"rhs": "..."} binding must not be multiplied — it resolves to a
    # number later (in _resolve_rhs_in_spec, which the builder chains
    # *before* this conversion for --no-dim mode).
    spec = {
        "features": [
            {
                "type": "boss_extrude_blind",
                "depth": {"rhs": '"PLATE_THICKNESS"'},
            }
        ]
    }
    out = convert_spec_units(spec, "inch")
    assert out["features"][0]["depth"] == {"rhs": '"PLATE_THICKNESS"'}


def test_convert_inch_passes_through_non_length_string_fields() -> None:
    # The "locals" path is a string under a non-length key; the walker
    # must leave it alone (it's not inside a LENGTH_FIELDS key).
    spec = {"locals": r"C:\work\plate_locals.txt", "features": []}
    out = convert_spec_units(spec, "inch")
    assert out["locals"] == spec["locals"]


def test_convert_inch_raises_on_non_numeric_length_value() -> None:
    spec = {"features": [{"depth": "ten"}]}
    with pytest.raises(TypeError):
        convert_spec_units(spec, "inch")


def test_convert_rejects_unknown_unit() -> None:
    with pytest.raises(ValueError):
        convert_spec_units({}, "cm")


def test_convert_preserves_meta_fields() -> None:
    # name, type, schema_version, plane — none of these are lengths;
    # all must survive the walk untouched.
    spec = {
        "schema_version": 1,
        "name": "motor_mount_plate",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Base",
                "plane": "Front",
                "width": 2.0,
                "height": 1.0,
            }
        ],
    }
    out = convert_spec_units(spec, "inch")
    assert out["schema_version"] == 1
    assert out["name"] == "motor_mount_plate"
    feat = out["features"][0]
    assert feat["type"] == "sketch_rectangle_on_plane"
    assert feat["name"] == "SK_Base"
    assert feat["plane"] == "Front"


# -----------------------------------------------------------------------------
# End-to-end: a v1 spec authored in inches scales as a whole
# -----------------------------------------------------------------------------


def test_convert_full_minimal_box_authored_in_inches() -> None:
    # 2" x 2" x 1" box.
    spec = {
        "schema_version": 1,
        "name": "Box",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 2.0,
                "height": 2.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 1.0,
            },
        ],
    }
    out = convert_spec_units(spec, "inch")
    assert out["features"][0]["width"] == pytest.approx(50.8)
    assert out["features"][0]["height"] == pytest.approx(50.8)
    assert out["features"][1]["depth"] == pytest.approx(25.4)
