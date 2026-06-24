"""X5 (FR-1/FR-2): schema v1->v2 version-routing tests.

Covers:
  - v1 specs validate exactly as before (flag OFF, the default).
  - a v2 spec carrying the new blocks validates when the `schema_v2` flag is ON
    (validated-but-inert -- no builder behaviour keys off it here).
  - a v2 spec is REJECTED when the flag is OFF (v2 stays sealed).
  - a v2 spec with a malformed new block is REJECTED (grammar is checked).
  - additionalProperties:false still rejects unknown keys under BOTH versions.
"""

from __future__ import annotations

import copy

import jsonschema
import pytest

from ai_sw_bridge.spec.schema import (
    SCHEMA,
    SCHEMA_V2,
    SCHEMA_VERSION,
    SCHEMA_VERSION_V2,
    SUPPORTED_SCHEMA_VERSIONS,
    schema_for_version,
)
from ai_sw_bridge.spec.validator import ValidationError, _check_schema


# A minimal, valid v1 feature list shared by the fixtures below.
_FEATURES = [
    {
        "type": "sketch_rectangle_on_plane",
        "name": "SK_Box",
        "plane": "Front",
        "width": 10.0,
        "height": 10.0,
    },
    {
        "type": "boss_extrude_blind",
        "name": "Extrude_Box",
        "sketch": "SK_Box",
        "depth": 5.0,
    },
]


def _v1_spec() -> dict:
    return {"schema_version": 1, "name": "v1part", "features": copy.deepcopy(_FEATURES)}


def _v2_spec() -> dict:
    return {
        "schema_version": 2,
        "name": "v2part",
        "material": "AISI 1020",
        "units": "mm",
        "drawing": {"enabled": True, "sheet_size": "A3"},
        "export": [{"format": "step214"}, {"format": "stl", "filename": "rev_B"}],
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
                "tolerance": {"plus": 0.1, "minus": 0.05},
            },
            {
                "type": "boss_extrude_blind",
                "name": "Extrude_Box",
                "sketch": "SK_Box",
                "depth": 5.0,
                "tolerance": 0.2,
            },
        ],
    }


@pytest.fixture()
def v2_on(monkeypatch):
    """Turn the `schema_v2` flag ON via the env override (highest-but-CLI)."""
    monkeypatch.setenv("AI_SW_BRIDGE_FLAG_SCHEMA_V2", "1")


@pytest.fixture()
def v2_off(monkeypatch):
    """Force the `schema_v2` flag OFF explicitly (it also defaults OFF)."""
    monkeypatch.setenv("AI_SW_BRIDGE_FLAG_SCHEMA_V2", "0")


# ---------------------------------------------------------------------------
# Constants / routing function
# ---------------------------------------------------------------------------


def test_supported_versions():
    assert SUPPORTED_SCHEMA_VERSIONS == (1, 2)
    assert SCHEMA_VERSION == 1
    assert SCHEMA_VERSION_V2 == 2


def test_routing_v1_always_v1_schema():
    assert schema_for_version(1, v2_enabled=True) is SCHEMA
    assert schema_for_version(1, v2_enabled=False) is SCHEMA


def test_routing_v2_requires_flag():
    assert schema_for_version(2, v2_enabled=True) is SCHEMA_V2
    # Flag OFF -> falls back to v1 schema, whose const:1 will reject a v2 spec.
    assert schema_for_version(2, v2_enabled=False) is SCHEMA


def test_routing_unknown_version_falls_back_to_v1():
    assert schema_for_version(99, v2_enabled=True) is SCHEMA


def test_v2_is_superset_of_v1_properties():
    v1_props = set(SCHEMA["properties"])
    v2_props = set(SCHEMA_V2["properties"])
    assert v1_props <= v2_props
    assert {"material", "units", "drawing", "export"} <= v2_props


def test_v1_feature_fragments_unmutated():
    """Building the v2 schema must not splice `tolerance` into v1 fragments."""
    for frag in SCHEMA["properties"]["features"]["items"]["oneOf"]:
        assert "tolerance" not in frag["properties"]


# ---------------------------------------------------------------------------
# v1 behaviour is identical (default flag state = OFF)
# ---------------------------------------------------------------------------


def test_v1_spec_validates_default_flag():
    _check_schema(_v1_spec())


def test_v1_spec_validates_with_flag_on(v2_on):
    """Turning v2 ON must not change how v1 specs validate."""
    _check_schema(_v1_spec())


def test_v1_unknown_key_rejected_default():
    spec = _v1_spec()
    spec["bogus_top_level"] = True
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v1_unknown_key_rejected_with_flag_on(v2_on):
    spec = _v1_spec()
    spec["bogus_top_level"] = True
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v1_rejects_v2_only_block():
    """A v1 spec carrying a v2-only block (material) is rejected by v1's
    additionalProperties:false."""
    spec = _v1_spec()
    spec["material"] = "AISI 1020"
    with pytest.raises(ValidationError):
        _check_schema(spec)


# ---------------------------------------------------------------------------
# v2 acceptance is gated behind the flag
# ---------------------------------------------------------------------------


def test_v2_spec_rejected_when_flag_off(v2_off):
    with pytest.raises(ValidationError):
        _check_schema(_v2_spec())


def test_v2_spec_rejected_by_default():
    """No env set -> registry default OFF -> v2 rejected."""
    with pytest.raises(ValidationError):
        _check_schema(_v2_spec())


def test_v2_spec_validates_when_flag_on(v2_on):
    _check_schema(_v2_spec())


def test_v2_minimal_validates_when_flag_on(v2_on):
    """A v2 spec with no optional blocks (just version bump) is valid."""
    spec = {"schema_version": 2, "name": "v2min", "features": copy.deepcopy(_FEATURES)}
    _check_schema(spec)


# ---------------------------------------------------------------------------
# v2 grammar is actually checked (malformed blocks rejected)
# ---------------------------------------------------------------------------


def test_v2_bad_units_rejected(v2_on):
    spec = _v2_spec()
    spec["units"] = "furlongs"
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v2_bad_export_format_rejected(v2_on):
    spec = _v2_spec()
    spec["export"] = [{"format": "not_a_real_format"}]
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v2_bad_drawing_sheet_rejected(v2_on):
    spec = _v2_spec()
    spec["drawing"] = {"sheet_size": "A99"}
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v2_bad_drawing_extra_key_rejected(v2_on):
    spec = _v2_spec()
    spec["drawing"] = {"enabled": True, "bogus": 1}
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v2_empty_material_rejected(v2_on):
    spec = _v2_spec()
    spec["material"] = ""
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v2_bad_tolerance_object_rejected(v2_on):
    spec = _v2_spec()
    spec["features"][0]["tolerance"] = {"plus": 0.1}  # missing `minus`
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v2_negative_tolerance_rejected(v2_on):
    spec = _v2_spec()
    spec["features"][1]["tolerance"] = -0.5
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v2_unknown_top_level_key_rejected(v2_on):
    spec = _v2_spec()
    spec["bogus_top_level"] = True
    with pytest.raises(ValidationError):
        _check_schema(spec)


def test_v2_unknown_feature_key_rejected(v2_on):
    """additionalProperties:false still rejects unknown per-feature keys in v2."""
    spec = _v2_spec()
    spec["features"][0]["bogus_field"] = 1
    with pytest.raises(ValidationError):
        _check_schema(spec)


# ---------------------------------------------------------------------------
# Direct jsonschema sanity on the assembled v2 schema (no flag involved)
# ---------------------------------------------------------------------------


def test_v2_schema_accepts_full_block_directly():
    jsonschema.validate(instance=_v2_spec(), schema=SCHEMA_V2)
