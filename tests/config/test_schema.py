"""Tests for the variants block JSON-Schema fragment."""

from __future__ import annotations

import jsonschema
import pytest

from ai_sw_bridge.config.schema import (
    VARIANTS_BLOCK_SCHEMA,
    VARIANT_ENTRY_SCHEMA,
    VARIANT_OVERRIDE_SCHEMA,
)


class TestVariantsBlockSchema:
    """Schema structural integrity."""

    def test_block_schema_is_array(self) -> None:
        assert VARIANTS_BLOCK_SCHEMA["type"] == "array"
        assert VARIANTS_BLOCK_SCHEMA["minItems"] == 1

    def test_entry_schema_requires_name(self) -> None:
        assert "name" in VARIANT_ENTRY_SCHEMA["required"]
        assert VARIANT_ENTRY_SCHEMA["additionalProperties"] is False

    def test_overrides_schema_is_object_with_string_values(self) -> None:
        assert VARIANT_OVERRIDE_SCHEMA["type"] == "object"
        assert VARIANT_OVERRIDE_SCHEMA["additionalProperties"] == {"type": "string"}

    def test_valid_variants_block(self) -> None:
        block = [
            {"name": "Small", "overrides": {"WIDTH": "20.0"}},
            {
                "name": "Large",
                "overrides": {"WIDTH": "50.0", "HEIGHT": "80.0"},
                "description": "Heavy-duty variant",
            },
        ]
        jsonschema.validate(block, VARIANTS_BLOCK_SCHEMA)

    def test_empty_block_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([], VARIANTS_BLOCK_SCHEMA)

    def test_missing_name_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([{"overrides": {"X": "1"}}], VARIANTS_BLOCK_SCHEMA)

    def test_additional_properties_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                [{"name": "A", "unknown_field": True}],
                VARIANTS_BLOCK_SCHEMA,
            )

    def test_non_string_override_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                [{"name": "A", "overrides": {"X": 42}}],
                VARIANTS_BLOCK_SCHEMA,
            )

    def test_variant_without_overrides_valid(self) -> None:
        jsonschema.validate([{"name": "Default"}], VARIANTS_BLOCK_SCHEMA)

    def test_name_required_non_empty(self) -> None:
        # minLength: 1 on name
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([{"name": ""}], VARIANTS_BLOCK_SCHEMA)
