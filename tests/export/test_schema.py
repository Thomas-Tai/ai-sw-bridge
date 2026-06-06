"""Tests for the export block JSON-Schema fragment."""

from __future__ import annotations

import jsonschema
import pytest

from ai_sw_bridge.export.formats import EXPORT_FORMAT_NAMES
from ai_sw_bridge.export.schema import (
    EXPORT_BLOCK_SCHEMA,
    EXPORT_ENTRY_SCHEMA,
)


class TestExportBlockSchema:
    """Schema structural integrity."""

    def test_block_schema_is_array(self) -> None:
        assert EXPORT_BLOCK_SCHEMA["type"] == "array"
        assert EXPORT_BLOCK_SCHEMA["minItems"] == 1

    def test_entry_schema_requires_format(self) -> None:
        assert "format" in EXPORT_ENTRY_SCHEMA["required"]
        assert EXPORT_ENTRY_SCHEMA["additionalProperties"] is False

    def test_format_enum_matches_registry(self) -> None:
        enum_vals = set(EXPORT_ENTRY_SCHEMA["properties"]["format"]["enum"])
        assert enum_vals == EXPORT_FORMAT_NAMES

    def test_valid_export_block(self) -> None:
        block = [
            {"format": "step214"},
            {"format": "pdf"},
            {"format": "stl", "filename": "rev_B"},
        ]
        jsonschema.validate(block, EXPORT_BLOCK_SCHEMA)

    def test_empty_block_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([], EXPORT_BLOCK_SCHEMA)

    def test_unknown_format_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([{"format": "vrml"}], EXPORT_BLOCK_SCHEMA)

    def test_additional_properties_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                [{"format": "stl", "unknown_field": True}],
                EXPORT_BLOCK_SCHEMA,
            )

    def test_format_required(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([{"filename": "no_format"}], EXPORT_BLOCK_SCHEMA)

    def test_sheets_all_valid(self) -> None:
        block = [{"format": "pdf", "sheets": "all"}]
        jsonschema.validate(block, EXPORT_BLOCK_SCHEMA)

    def test_sheets_list_valid(self) -> None:
        block = [{"format": "pdf", "sheets": ["Overview", "Detail"]}]
        jsonschema.validate(block, EXPORT_BLOCK_SCHEMA)

    def test_sheets_empty_list_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                [{"format": "pdf", "sheets": []}],
                EXPORT_BLOCK_SCHEMA,
            )

    def test_sheets_invalid_string_rejected(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                [{"format": "pdf", "sheets": "current"}],
                EXPORT_BLOCK_SCHEMA,
            )

    def test_sheets_optional(self) -> None:
        block = [{"format": "pdf"}]
        jsonschema.validate(block, EXPORT_BLOCK_SCHEMA)

    def test_sheets_on_step_ignored_by_schema(self) -> None:
        """Schema allows 'sheets' on any format; dispatch validates."""
        block = [{"format": "step214", "sheets": "all"}]
        jsonschema.validate(block, EXPORT_BLOCK_SCHEMA)
