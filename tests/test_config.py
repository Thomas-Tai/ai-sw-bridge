"""Tests for ai_sw_bridge.config (SW-free layer).

Covers the offline scaffold: parse_variants, apply_overrides,
validate_overrides, and the schema definitions.  The COM-touching
``create_all`` / ``_create_one`` are seat-gated and not tested here.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.config import (
    VARIANTS_BLOCK_SCHEMA,
    VARIANT_ENTRY_SCHEMA,
    VARIANT_OVERRIDE_SCHEMA,
    ConfigResult,
    ConfigVariant,
    VariantOverride,
    apply_overrides,
    deep_merge,
    parse_variants,
    validate_overrides,
)


# ---------------------------------------------------------------------------
# parse_variants()
# ---------------------------------------------------------------------------


def test_parse_variants_basic() -> None:
    block = [
        {"name": "Small", "overrides": {"WIDTH": "20.0", "HEIGHT": "30.0"}},
        {"name": "Large", "overrides": {"WIDTH": "50.0"}},
    ]
    variants = parse_variants(block)
    assert len(variants) == 2
    assert variants[0].name == "Small"
    assert len(variants[0].overrides) == 2
    assert variants[1].name == "Large"
    assert len(variants[1].overrides) == 1


def test_parse_variants_empty_overrides() -> None:
    block = [{"name": "Default"}]
    variants = parse_variants(block)
    assert len(variants) == 1
    assert variants[0].overrides == []
    assert variants[0].description == ""


def test_parse_variants_with_description() -> None:
    block = [
        {
            "name": "Production",
            "overrides": {"D": "100.0"},
            "description": "Heavy-duty variant",
        }
    ]
    variants = parse_variants(block)
    assert variants[0].description == "Heavy-duty variant"


def test_parse_variants_rejects_duplicate_names() -> None:
    block = [{"name": "A"}, {"name": "A"}]
    with pytest.raises(ValueError, match="duplicate"):
        parse_variants(block)


def test_parse_variants_rejects_missing_name() -> None:
    block = [{"overrides": {"X": "1.0"}}]
    with pytest.raises(ValueError, match="missing"):
        parse_variants(block)


def test_parse_variants_non_string_expression_becomes_nested() -> None:
    """Non-string override values trigger the nested (multifile) path."""
    block = [{"name": "Mixed", "overrides": {"X": 42}}]
    variants = parse_variants(block)
    assert len(variants) == 1
    assert variants[0].spec_overrides == {"X": 42}
    assert variants[0].overrides == []


def test_parse_variants_rejects_non_dict_overrides() -> None:
    block = [{"name": "Bad", "overrides": "not-a-dict"}]
    with pytest.raises(ValueError, match="must be an object"):
        parse_variants(block)


def test_parse_variants_rejects_non_list_block() -> None:
    with pytest.raises(ValueError, match="must be an array"):
        parse_variants({"name": "NotAList"})


def test_parse_variants_preserves_override_order() -> None:
    block = [
        {
            "name": "V1",
            "overrides": {"A": "1.0", "B": "2.0", "C": "3.0"},
        }
    ]
    variants = parse_variants(block)
    names = [ov.variable for ov in variants[0].overrides]
    assert names == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# apply_overrides()
# ---------------------------------------------------------------------------


BASE_LOCALS = '"WIDTH" = 30.0\n"HEIGHT" = 40.0\n"DEPTH" = 10.0\n'


def test_apply_overrides_replaces_existing() -> None:
    overrides = [
        VariantOverride(variable="WIDTH", expression="50.0"),
        VariantOverride(variable="HEIGHT", expression="80.0"),
    ]
    result = apply_overrides(BASE_LOCALS, overrides)
    assert '"WIDTH" = 50.0' in result
    assert '"HEIGHT" = 80.0' in result
    assert '"DEPTH" = 10.0' in result


def test_apply_overrides_appends_new_variable() -> None:
    overrides = [VariantOverride(variable="NEW_VAR", expression="99.0")]
    result = apply_overrides(BASE_LOCALS, overrides)
    assert '"NEW_VAR" = 99.0' in result
    assert '"WIDTH" = 30.0' in result


def test_apply_overrides_empty_overrides_is_identity() -> None:
    result = apply_overrides(BASE_LOCALS, [])
    assert result == BASE_LOCALS


def test_apply_overrides_preserves_formatting() -> None:
    text = '# comment\n"X"          = 5.0\n"Y" = 10.0\n'
    overrides = [VariantOverride(variable="X", expression="99.0")]
    result = apply_overrides(text, overrides)
    assert "# comment" in result
    assert '"Y" = 10.0' in result


def test_apply_overrides_expression_with_references() -> None:
    overrides = [
        VariantOverride(variable="WIDTH", expression='"HEIGHT" + 10'),
    ]
    result = apply_overrides(BASE_LOCALS, overrides)
    assert '"WIDTH" = "HEIGHT" + 10' in result


def test_apply_overrides_does_not_mutate_base() -> None:
    original = BASE_LOCALS
    apply_overrides(BASE_LOCALS, [VariantOverride("WIDTH", "999")])
    assert BASE_LOCALS == original


# ---------------------------------------------------------------------------
# validate_overrides()
# ---------------------------------------------------------------------------


def test_validate_overrides_all_known() -> None:
    variants = [
        ConfigVariant(
            name="V1",
            overrides=[VariantOverride("WIDTH", "50.0")],
        )
    ]
    errors = validate_overrides(BASE_LOCALS, variants)
    assert errors == []


def test_validate_overrides_unknown_variable() -> None:
    variants = [
        ConfigVariant(
            name="V1",
            overrides=[VariantOverride("NONEXISTENT", "50.0")],
        )
    ]
    errors = validate_overrides(BASE_LOCALS, variants)
    assert len(errors) == 1
    assert "NONEXISTENT" in errors[0]
    assert "V1" in errors[0]


def test_validate_overrides_multiple_unknowns() -> None:
    variants = [
        ConfigVariant(
            name="V1",
            overrides=[
                VariantOverride("WIDTH", "50.0"),
                VariantOverride("BAD1", "1.0"),
                VariantOverride("BAD2", "2.0"),
            ],
        ),
        ConfigVariant(
            name="V2",
            overrides=[VariantOverride("BAD3", "3.0")],
        ),
    ]
    errors = validate_overrides(BASE_LOCALS, variants)
    assert len(errors) == 3


def test_validate_overrides_empty_variants() -> None:
    errors = validate_overrides(BASE_LOCALS, [])
    assert errors == []


# ---------------------------------------------------------------------------
# ConfigResult
# ---------------------------------------------------------------------------


def test_config_result_to_dict_ok() -> None:
    r = ConfigResult(variant="Small", ok=True)
    d = r.to_dict()
    assert d == {"variant": "Small", "ok": True}
    assert "error" not in d
    assert "path" not in d
    assert "volume_mm3" not in d


def test_config_result_to_dict_with_path_and_volume() -> None:
    r = ConfigResult(
        variant="Small", ok=True, path="/tmp/Small.sldprt", volume_mm3=125000.0
    )
    d = r.to_dict()
    assert d == {
        "variant": "Small",
        "ok": True,
        "path": "/tmp/Small.sldprt",
        "volume_mm3": 125000.0,
    }


def test_config_result_to_dict_error() -> None:
    r = ConfigResult(variant="Bad", ok=False, error="boom")
    d = r.to_dict()
    assert d == {"variant": "Bad", "ok": False, "error": "boom"}


# ---------------------------------------------------------------------------
# Schema fragments
# ---------------------------------------------------------------------------


def test_variants_block_schema_structure() -> None:
    assert VARIANTS_BLOCK_SCHEMA["type"] == "array"
    assert VARIANTS_BLOCK_SCHEMA["minItems"] == 1


def test_variant_entry_schema_requires_name() -> None:
    assert "name" in VARIANT_ENTRY_SCHEMA["required"]


def test_variant_override_schema_is_string_map() -> None:
    assert VARIANT_OVERRIDE_SCHEMA["type"] == "object"
    assert VARIANT_OVERRIDE_SCHEMA["additionalProperties"] == {"type": "string"}


# ---------------------------------------------------------------------------
# deep_merge()
# ---------------------------------------------------------------------------


def test_deep_merge_basic_replace() -> None:
    base = {"name": "Box", "features": [{"width": 20.0}]}
    overrides = {"name": "BigBox"}
    result = deep_merge(base, overrides)
    assert result["name"] == "BigBox"
    assert result["features"] == [{"width": 20.0}]


def test_deep_merge_nested_dict() -> None:
    base = {
        "name": "Box",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK_Box", "width": 20.0}
        ],
    }
    # Lists are replaced entirely by deep_merge (not element-merged)
    overrides = {
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK_Box", "width": 50.0}
        ]
    }
    result = deep_merge(base, overrides)
    assert result["features"][0]["width"] == 50.0
    assert result["features"][0]["type"] == "sketch_rectangle_on_plane"
    assert result["name"] == "Box"  # non-overridden keys preserved


def test_deep_merge_does_not_mutate_base() -> None:
    base = {"a": {"b": 1}, "c": 2}
    overrides = {"a": {"b": 99}}
    result = deep_merge(base, overrides)
    assert result["a"]["b"] == 99
    assert base["a"]["b"] == 1  # base unchanged


def test_deep_merge_list_replace() -> None:
    base = {"features": [{"name": "A"}, {"name": "B"}]}
    overrides = {"features": [{"name": "C"}]}
    result = deep_merge(base, overrides)
    assert result["features"] == [{"name": "C"}]


def test_deep_merge_empty_overrides_is_identity() -> None:
    base = {"x": 1, "y": {"z": 2}}
    result = deep_merge(base, {})
    assert result == base
    assert result is not base  # fresh copy


def test_deep_merge_adds_new_keys() -> None:
    base = {"a": 1}
    overrides = {"b": 2, "c": {"d": 3}}
    result = deep_merge(base, overrides)
    assert result == {"a": 1, "b": 2, "c": {"d": 3}}


# ---------------------------------------------------------------------------
# parse_variants() — nested dict overrides (multifile)
# ---------------------------------------------------------------------------


def test_parse_variants_nested_dict_overrides() -> None:
    block = [
        {
            "name": "Large",
            "overrides": {
                "features": [
                    {"type": "sketch_rectangle_on_plane", "width": 50.0}
                ]
            },
        }
    ]
    variants = parse_variants(block)
    assert len(variants) == 1
    assert variants[0].name == "Large"
    assert variants[0].spec_overrides == {
        "features": [{"type": "sketch_rectangle_on_plane", "width": 50.0}]
    }
    assert variants[0].overrides == []  # no locals overrides


def test_parse_variants_flat_string_overrides_unchanged() -> None:
    block = [
        {"name": "Small", "overrides": {"WIDTH": "20.0", "HEIGHT": "30.0"}}
    ]
    variants = parse_variants(block)
    assert len(variants) == 1
    assert len(variants[0].overrides) == 2
    assert variants[0].spec_overrides == {}  # no nested overrides
