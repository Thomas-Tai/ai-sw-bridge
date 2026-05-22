"""Schema validation tests: all shipped examples pass schema check."""

import json
from pathlib import Path

import pytest

from ai_sw_bridge.spec.schema import SCHEMA, SCHEMA_VERSION, EXPECT_SCHEMA
from ai_sw_bridge.spec.validator import _check_schema

import jsonschema

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _load_spec(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Path C specs (minimal_cylinder) use a different schema format and are
# excluded from v0.2 schema validation.
PATH_C_DIRS = frozenset({"minimal_cylinder"})


def _shipped_specs():
    """All v0.2 spec.json files in example folders."""
    for spec_path in sorted(EXAMPLES_DIR.rglob("spec.json")):
        if spec_path.parent.name in PATH_C_DIRS:
            continue
        yield pytest.param(spec_path, id=str(spec_path.relative_to(EXAMPLES_DIR)))


@pytest.mark.parametrize("spec_path", list(_shipped_specs()))
def test_shipped_spec_passes_schema(spec_path):
    spec = _load_spec(spec_path)
    _check_schema(spec)


def test_schema_version_is_1():
    assert SCHEMA_VERSION == 1


def test_top_level_requires_name_version_features():
    with pytest.raises(Exception):
        _check_schema({})


def test_empty_features_array_rejected():
    with pytest.raises(Exception):
        _check_schema(
            {
                "schema_version": 1,
                "name": "test",
                "features": [],
            }
        )


def test_unknown_feature_type_rejected():
    with pytest.raises(Exception):
        _check_schema(
            {
                "schema_version": 1,
                "name": "test",
                "features": [
                    {"type": "does_not_exist", "name": "X"},
                ],
            }
        )


def test_comment_fields_stripped():
    """_comment fields should not trigger additionalProperties=false."""
    spec = {
        "schema_version": 1,
        "name": "test",
        "_comment": "top-level comment should be stripped",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
                "_comment": "feature-level comment should be stripped",
            },
            {
                "type": "boss_extrude_blind",
                "name": "Extrude_Box",
                "sketch": "SK_Box",
                "depth": 5.0,
            },
        ],
    }
    _check_schema(spec)


# -----------------------------------------------------------------------------
# EXPECT_SCHEMA (_expect block)
# -----------------------------------------------------------------------------


def test_expect_schema_accepts_valid_block():
    jsonschema.validate(instance={"mass_delta_mm3": 27000.0}, schema=EXPECT_SCHEMA)


def test_expect_schema_accepts_with_tolerance():
    jsonschema.validate(
        instance={"mass_delta_mm3": -500.0, "tolerance_mm3": 5.0},
        schema=EXPECT_SCHEMA,
    )


def test_expect_schema_rejects_negative_tolerance():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"mass_delta_mm3": 100.0, "tolerance_mm3": -1.0},
            schema=EXPECT_SCHEMA,
        )


def test_expect_schema_rejects_missing_mass_delta():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance={"tolerance_mm3": 5.0}, schema=EXPECT_SCHEMA)


def test_expect_schema_rejects_extra_keys():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"mass_delta_mm3": 100.0, "bogus": True},
            schema=EXPECT_SCHEMA,
        )
