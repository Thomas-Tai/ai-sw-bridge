"""Tests for the config variant data model and parser (SW-free)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.config.variants import (
    ConfigResult,
    ConfigVariant,
    VariantOverride,
    parse_variants,
)


class TestVariantOverride:
    def test_frozen(self) -> None:
        ov = VariantOverride(variable="WIDTH", expression="25.0")
        with pytest.raises(AttributeError):
            ov.variable = "HACKED"  # type: ignore[misc]

    def test_fields(self) -> None:
        ov = VariantOverride(variable="WIDTH", expression='"X" + 3')
        assert ov.variable == "WIDTH"
        assert ov.expression == '"X" + 3'


class TestConfigVariant:
    def test_frozen(self) -> None:
        v = ConfigVariant(name="Small")
        with pytest.raises(AttributeError):
            v.name = "HACKED"  # type: ignore[misc]

    def test_defaults(self) -> None:
        v = ConfigVariant(name="Default")
        assert v.overrides == []
        assert v.description == ""

    def test_with_overrides(self) -> None:
        v = ConfigVariant(
            name="Large",
            overrides=[
                VariantOverride("WIDTH", "50.0"),
                VariantOverride("HEIGHT", "80.0"),
            ],
            description="Heavy-duty variant",
        )
        assert len(v.overrides) == 2
        assert v.description == "Heavy-duty variant"


class TestConfigResult:
    def test_to_dict_success(self) -> None:
        r = ConfigResult(variant="Small", ok=True)
        d = r.to_dict()
        assert d == {"variant": "Small", "ok": True}
        assert "error" not in d

    def test_to_dict_failure(self) -> None:
        r = ConfigResult(variant="Small", ok=False, error="SEAT-gated")
        d = r.to_dict()
        assert d["error"] == "SEAT-gated"
        assert d["ok"] is False


class TestParseVariants:
    def test_empty_array(self) -> None:
        assert parse_variants([]) == []

    def test_single_variant_no_overrides(self) -> None:
        block = [{"name": "Default"}]
        variants = parse_variants(block)
        assert len(variants) == 1
        assert variants[0].name == "Default"
        assert variants[0].overrides == []

    def test_single_variant_with_overrides(self) -> None:
        block = [
            {
                "name": "Small",
                "overrides": {"WIDTH": "20.0", "HEIGHT": "30.0"},
            }
        ]
        variants = parse_variants(block)
        assert len(variants) == 1
        assert variants[0].name == "Small"
        assert len(variants[0].overrides) == 2
        vars_map = {o.variable: o.expression for o in variants[0].overrides}
        assert vars_map["WIDTH"] == "20.0"
        assert vars_map["HEIGHT"] == "30.0"

    def test_multiple_variants(self) -> None:
        block = [
            {"name": "A", "overrides": {"X": "1"}},
            {"name": "B", "overrides": {"X": "2"}},
        ]
        variants = parse_variants(block)
        assert len(variants) == 2
        assert variants[0].name == "A"
        assert variants[1].name == "B"

    def test_duplicate_name_rejected(self) -> None:
        block = [{"name": "A"}, {"name": "A"}]
        with pytest.raises(ValueError, match="duplicate variant name"):
            parse_variants(block)

    def test_missing_name_rejected(self) -> None:
        block = [{"overrides": {"X": "1"}}]
        with pytest.raises(ValueError, match="missing or non-string"):
            parse_variants(block)

    def test_empty_name_rejected(self) -> None:
        block = [{"name": ""}]
        with pytest.raises(ValueError, match="missing or non-string"):
            parse_variants(block)

    def test_non_dict_entry_rejected(self) -> None:
        block = ["not an object"]  # type: ignore[list-item]
        with pytest.raises(ValueError, match="must be an object"):
            parse_variants(block)

    def test_non_array_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be an array"):
            parse_variants({"name": "A"})  # type: ignore[arg-type]

    def test_non_string_expression_rejected(self) -> None:
        block = [{"name": "A", "overrides": {"X": 42}}]  # type: ignore[dict-item]
        with pytest.raises(ValueError, match="must be a string expression"):
            parse_variants(block)

    def test_non_dict_overrides_rejected(self) -> None:
        block = [{"name": "A", "overrides": "not a dict"}]  # type: ignore[dict-item]
        with pytest.raises(ValueError, match="must be an object"):
            parse_variants(block)

    def test_description_preserved(self) -> None:
        block = [{"name": "A", "description": "test desc"}]
        variants = parse_variants(block)
        assert variants[0].description == "test desc"

    def test_non_string_description_rejected(self) -> None:
        block = [{"name": "A", "description": 123}]  # type: ignore[dict-item]
        with pytest.raises(ValueError, match="must be a string"):
            parse_variants(block)
