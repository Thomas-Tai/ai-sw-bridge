"""Tests for metadata module (Wave-29).

Offline tests for:
  - spec_schema validation
  - lifecycle propose/dry_run (no SW touch)
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.metadata.spec_schema import (
    PROPERTIES_SPEC_SCHEMA,
    validate_properties_spec,
)
from ai_sw_bridge.metadata.lifecycle import propose_properties, dry_run_properties


# ---- spec_schema tests -------------------------------------------------------


class TestPropertiesSpecSchema:
    """JSON-schema validation for kind: "properties" specs."""

    def test_valid_minimal_spec(self) -> None:
        """Minimal valid spec passes schema validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema
        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)  # should not raise

    def test_valid_full_spec(self) -> None:
        """Full spec with overwrite passes schema validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/assembly.SLDASM",
            "properties": {
                "PartNo": "ASM-002",
                "Description": "Test assembly",
                "Revision": "A",
            },
            "overwrite": False,
        }
        import jsonschema
        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)  # should not raise

    def test_missing_kind_fails(self) -> None:
        """Missing kind field fails schema validation."""
        spec = {
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_wrong_kind_fails(self) -> None:
        """Wrong kind value fails schema validation."""
        spec = {
            "kind": "part",
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_missing_model_fails(self) -> None:
        """Missing model field fails schema validation."""
        spec = {
            "kind": "properties",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_missing_properties_fails(self) -> None:
        """Missing properties field fails schema validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
        }
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_empty_properties_fails(self) -> None:
        """Empty properties map fails schema validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {},
        }
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_non_string_property_value_fails(self) -> None:
        """Non-string property value fails schema validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Count": 42},
        }
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_nested_property_value_fails(self) -> None:
        """Nested property value fails schema validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Meta": {"nested": "value"}},
        }
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)


class TestValidatePropertiesSpec:
    """Semantic validation beyond JSON-schema."""

    def test_valid_part_extension(self) -> None:
        """Valid .sldprt extension passes semantic validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        validate_properties_spec(spec)  # should not raise

    def test_valid_asm_extension(self) -> None:
        """Valid .sldasm extension passes semantic validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/asm.SLDASM",
            "properties": {"PartNo": "ASM-001"},
        }
        validate_properties_spec(spec)  # should not raise

    def test_lowercase_extension_passes(self) -> None:
        """Lowercase extension passes semantic validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.sldprt",
            "properties": {"PartNo": "BRK-001"},
        }
        validate_properties_spec(spec)  # should not raise

    def test_wrong_extension_fails(self) -> None:
        """Wrong file extension fails semantic validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/doc.txt",
            "properties": {"PartNo": "BRK-001"},
        }
        with pytest.raises(ValueError, match="must be a .sldprt or .sldasm"):
            validate_properties_spec(spec)

    def test_no_extension_fails(self) -> None:
        """No file extension fails semantic validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part",
            "properties": {"PartNo": "BRK-001"},
        }
        with pytest.raises(ValueError, match="must be a .sldprt or .sldasm"):
            validate_properties_spec(spec)

    def test_non_bool_overwrite_fails(self) -> None:
        """Non-boolean overwrite fails semantic validation."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
            "overwrite": "yes",
        }
        with pytest.raises(ValueError, match="overwrite must be a boolean"):
            validate_properties_spec(spec)

    def test_non_dict_spec_fails(self) -> None:
        """Non-dict spec fails semantic validation."""
        with pytest.raises(ValueError, match="spec must be a dict"):
            validate_properties_spec("not a dict")

    def test_wrong_kind_fails(self) -> None:
        """Wrong kind fails semantic validation."""
        spec = {
            "kind": "drawing",
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        with pytest.raises(ValueError, match="kind must be 'properties'"):
            validate_properties_spec(spec)


# ---- lifecycle tests (offline) ------------------------------------------------


class TestProposeProperties:
    """Offline propose tests (no SW touch)."""

    def test_propose_valid_spec(self) -> None:
        """Valid spec returns ok=True."""
        spec = {
            "kind": "properties",
            "model": "/nonexistent/path/part.SLDPRT",  # doesn't need to exist for propose
            "properties": {"PartNo": "BRK-001", "Description": "Test"},
        }
        result = propose_properties(spec)
        assert result["ok"] is True
        assert result["properties_count"] == 2
        assert result["model"] == spec["model"]

    def test_propose_schema_invalid_fails(self) -> None:
        """Schema-invalid spec returns ok=False."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {},  # empty, fails minProperties
        }
        result = propose_properties(spec)
        assert result["ok"] is False
        assert "schema validation" in result["error"]

    def test_propose_semantic_invalid_fails(self) -> None:
        """Semantic-invalid spec returns ok=False."""
        spec = {
            "kind": "properties",
            "model": "/path/to/doc.pdf",  # wrong extension
            "properties": {"PartNo": "BRK-001"},
        }
        result = propose_properties(spec)
        assert result["ok"] is False
        assert ".sldprt or .sldasm" in result["error"]


class TestDryRunProperties:
    """Offline dry_run tests (file existence check)."""

    def test_dry_run_missing_file_fails(self) -> None:
        """Missing model file returns ok=False."""
        spec = {
            "kind": "properties",
            "model": "/nonexistent/path/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        result = dry_run_properties(spec)
        assert result["ok"] is False
        assert "model file not found" in result["error"]

    def test_dry_run_existing_file_passes(self, tmp_path) -> None:
        """Existing model file returns ok=True."""
        # Create a fake .sldprt file (just an empty file for dry_run check)
        fake_part = tmp_path / "test.SLDPRT"
        fake_part.touch()

        spec = {
            "kind": "properties",
            "model": str(fake_part),
            "properties": {"PartNo": "BRK-001", "Description": "Test"},
        }
        result = dry_run_properties(spec)
        assert result["ok"] is True
        assert result["properties_count"] == 2
        assert result["model_path"] == str(fake_part)