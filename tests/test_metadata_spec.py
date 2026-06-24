"""Tests for metadata module (Wave-29, extended Wave-53).

Offline tests for:
  - spec_schema validation (v1 TEXT + v2 typed: number/date/yes_no)
  - resolve_prop_type_and_value resolver
  - lifecycle propose/dry_run (no SW touch)
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.metadata.spec_schema import (
    PROPERTIES_SPEC_SCHEMA,
    SW_CUSTOM_INFO_DATE,
    SW_CUSTOM_INFO_NUMBER,
    SW_CUSTOM_INFO_TEXT,
    SW_CUSTOM_INFO_TYPE_MAP,
    SW_CUSTOM_INFO_YES_OR_NO,
    resolve_prop_type_and_value,
    semantic_prop_match,
    validate_properties_spec,
)
from ai_sw_bridge.metadata.lifecycle import propose_properties, dry_run_properties


# ---- spec_schema tests (v1 TEXT — backwards compat) -------------------------


class TestPropertiesSpecSchema:
    """JSON-schema validation for kind: "properties" specs."""

    def test_valid_minimal_spec(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_valid_full_spec(self) -> None:
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

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_missing_kind_fails(self) -> None:
        spec = {
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_wrong_kind_fails(self) -> None:
        spec = {
            "kind": "part",
            "model": "/path/to/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_missing_model_fails(self) -> None:
        spec = {
            "kind": "properties",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_missing_properties_and_delete_rejected_semantically(self) -> None:
        """v3: ``properties`` is now OPTIONAL at the schema layer (delete-only
        specs are valid), so {kind, model} passes jsonschema — but the SEMANTIC
        validator rejects a spec that neither sets nor deletes anything."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)  # schema-valid now
        with pytest.raises(ValueError, match="at least one"):
            validate_properties_spec(spec)

    def test_empty_properties_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_non_string_property_value_fails(self) -> None:
        """Integer value matches neither string nor typed-object."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Count": 42},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_nested_property_value_fails(self) -> None:
        """Dict without type/value keys fails the typed-object branch."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Meta": {"nested": "value"}},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)


# ---- W53 typed property schema tests -----------------------------------------


class TestTypedPropertySchema:
    """JSON-schema validation for v2 typed property entries."""

    def test_typed_text_passes(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Note": {"type": "text", "value": "hello"}},
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_typed_number_passes(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Weight": {"type": "number", "value": "42.5"}},
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_typed_date_passes(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Created": {"type": "date", "value": "2024-06-15"}},
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_typed_yes_no_passes(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Approved": {"type": "yes_no", "value": "Yes"}},
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_mixed_plain_and_typed_passes(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {
                "PartNo": "BRK-001",
                "Weight": {"type": "number", "value": "12.5"},
                "Approved": {"type": "yes_no", "value": "No"},
            },
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_invalid_type_enum_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"X": {"type": "boolean", "value": "true"}},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_typed_missing_value_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"X": {"type": "number"}},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_typed_missing_type_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"X": {"value": "42"}},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_typed_empty_value_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"X": {"type": "text", "value": ""}},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_typed_extra_field_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"X": {"type": "text", "value": "hi", "extra": 1}},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)


# ---- W71 config-level + delete (CRUD completion) schema/semantic -------------


class TestConfigAndDeleteSchema:
    """v3: optional ``configuration`` + ``delete`` fields, properties optional."""

    def test_configuration_field_passes(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "configuration": "Config_B",
            "properties": {"PartNo": "BRK-001"},
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)
        validate_properties_spec(spec)

    def test_delete_field_passes(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Keep": "yes"},
            "delete": ["Old1", "Old2"],
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)
        validate_properties_spec(spec)

    def test_delete_only_spec_passes(self) -> None:
        """A delete-only spec (no properties) is valid."""
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "configuration": "Config_B",
            "delete": ["Temp"],
        }
        import jsonschema

        jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)
        validate_properties_spec(spec)

    def test_empty_delete_with_no_properties_rejected(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "delete": [],
        }
        with pytest.raises(ValueError, match="at least one"):
            validate_properties_spec(spec)

    def test_delete_non_unique_rejected_by_schema(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "delete": ["X", "X"],
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_delete_empty_string_rejected_by_schema(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "delete": [""],
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_configuration_non_string_rejected_by_schema(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "configuration": 5,
            "properties": {"A": "b"},
        }
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, PROPERTIES_SPEC_SCHEMA)

    def test_propose_reports_config_and_delete_counts(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/nonexistent/part.SLDPRT",
            "configuration": "Config_B",
            "properties": {"A": "b"},
            "delete": ["Old1", "Old2"],
        }
        result = propose_properties(spec)
        assert result["ok"] is True
        assert result["configuration"] == "Config_B"
        assert result["properties_count"] == 1
        assert result["delete_count"] == 2

    def test_propose_delete_only_ok(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/nonexistent/part.SLDPRT",
            "delete": ["Temp"],
        }
        result = propose_properties(spec)
        assert result["ok"] is True
        assert result["properties_count"] == 0
        assert result["delete_count"] == 1

    def test_linked_property_value_is_accepted(self) -> None:
        """Zero-code linked properties (W71): a quoted "Name@Source" link string
        is just a TEXT value — it validates and the kernel resolves it natively
        (seat-proven: "D1@Boss-Extrude1" -> "10.00")."""
        spec = {
            "kind": "properties",
            "model": "/nonexistent/part.SLDPRT",
            "properties": {
                "DepthLink": '"D1@Boss-Extrude1"',
                "MassLink": '"SW-Mass@part.SLDPRT"',
            },
        }
        result = propose_properties(spec)
        assert result["ok"] is True
        assert result["properties_count"] == 2


# ---- resolve_prop_type_and_value tests ---------------------------------------


class TestResolvePropTypeAndValue:
    """Unit tests for the type/value resolver."""

    def test_plain_string_resolves_to_text(self) -> None:
        type_id, value, type_name = resolve_prop_type_and_value("P", "hello")
        assert type_id == SW_CUSTOM_INFO_TEXT
        assert value == "hello"
        assert type_name == "text"

    def test_typed_text(self) -> None:
        type_id, value, type_name = resolve_prop_type_and_value(
            "P", {"type": "text", "value": "hello"}
        )
        assert type_id == SW_CUSTOM_INFO_TEXT
        assert value == "hello"
        assert type_name == "text"

    def test_typed_number(self) -> None:
        type_id, value, type_name = resolve_prop_type_and_value(
            "W", {"type": "number", "value": "42.5"}
        )
        assert type_id == SW_CUSTOM_INFO_NUMBER
        assert value == "42.5"
        assert type_name == "number"

    def test_typed_date(self) -> None:
        type_id, value, type_name = resolve_prop_type_and_value(
            "D", {"type": "date", "value": "2024-01-15"}
        )
        assert type_id == SW_CUSTOM_INFO_DATE
        assert value == "2024-01-15"
        assert type_name == "date"

    def test_typed_yes_no(self) -> None:
        type_id, value, type_name = resolve_prop_type_and_value(
            "A", {"type": "yes_no", "value": "Yes"}
        )
        assert type_id == SW_CUSTOM_INFO_YES_OR_NO
        assert value == "Yes"
        assert type_name == "yes_no"

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid type"):
            resolve_prop_type_and_value("X", {"type": "bool", "value": "true"})

    def test_non_string_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a string or a typed-object"):
            resolve_prop_type_and_value("X", 42)

    def test_empty_value_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            resolve_prop_type_and_value("X", {"type": "text", "value": ""})

    def test_non_string_value_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            resolve_prop_type_and_value("X", {"type": "number", "value": 42})

    def test_type_map_values(self) -> None:
        assert SW_CUSTOM_INFO_TYPE_MAP["text"] == 30
        assert SW_CUSTOM_INFO_TYPE_MAP["number"] == 5
        assert SW_CUSTOM_INFO_TYPE_MAP["date"] == 64
        assert SW_CUSTOM_INFO_TYPE_MAP["yes_no"] == 11


# ---- semantic validation with typed properties --------------------------------


class TestValidateTypedProperties:
    """Semantic validation for typed property values."""

    def test_valid_number_integer(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Count": {"type": "number", "value": "100"}},
        }
        validate_properties_spec(spec)

    def test_valid_number_decimal(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Weight": {"type": "number", "value": "12.5"}},
        }
        validate_properties_spec(spec)

    def test_valid_number_negative(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Offset": {"type": "number", "value": "-3.14"}},
        }
        validate_properties_spec(spec)

    def test_valid_number_scientific(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Tolerance": {"type": "number", "value": "1.5e-3"}},
        }
        validate_properties_spec(spec)

    def test_invalid_number_non_numeric(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Count": {"type": "number", "value": "abc"}},
        }
        with pytest.raises(ValueError, match="numeric string"):
            validate_properties_spec(spec)

    def test_valid_date_iso(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Created": {"type": "date", "value": "2024-06-15"}},
        }
        validate_properties_spec(spec)

    def test_valid_date_us(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Created": {"type": "date", "value": "6/15/2024"}},
        }
        validate_properties_spec(spec)

    def test_valid_date_eu(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Created": {"type": "date", "value": "15.06.2024"}},
        }
        validate_properties_spec(spec)

    def test_invalid_date_format(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Created": {"type": "date", "value": "June 15th"}},
        }
        with pytest.raises(ValueError, match="date string"):
            validate_properties_spec(spec)

    def test_valid_yes_no_yes(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Approved": {"type": "yes_no", "value": "Yes"}},
        }
        validate_properties_spec(spec)

    def test_valid_yes_no_no(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Approved": {"type": "yes_no", "value": "No"}},
        }
        validate_properties_spec(spec)

    def test_invalid_yes_no_lowercase(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Approved": {"type": "yes_no", "value": "yes"}},
        }
        with pytest.raises(ValueError, match="'Yes' or 'No'"):
            validate_properties_spec(spec)

    def test_invalid_yes_no_true(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {"Approved": {"type": "yes_no", "value": "True"}},
        }
        with pytest.raises(ValueError, match="'Yes' or 'No'"):
            validate_properties_spec(spec)

    def test_mixed_plain_and_typed_valid(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {
                "PartNo": "BRK-001",
                "Weight": {"type": "number", "value": "12.5"},
                "Created": {"type": "date", "value": "2024-01-15"},
                "Approved": {"type": "yes_no", "value": "Yes"},
            },
        }
        validate_properties_spec(spec)


# ---- lifecycle tests (offline) ------------------------------------------------


class TestProposeProperties:
    """Offline propose tests (no SW touch)."""

    def test_propose_valid_spec(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/nonexistent/path/part.SLDPRT",
            "properties": {"PartNo": "BRK-001", "Description": "Test"},
        }
        result = propose_properties(spec)
        assert result["ok"] is True
        assert result["properties_count"] == 2
        assert result["model"] == spec["model"]

    def test_propose_schema_invalid_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {},
        }
        result = propose_properties(spec)
        assert result["ok"] is False
        assert "schema validation" in result["error"]

    def test_propose_semantic_invalid_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/doc.pdf",
            "properties": {"PartNo": "BRK-001"},
        }
        result = propose_properties(spec)
        assert result["ok"] is False
        assert ".sldprt or .sldasm" in result["error"]

    def test_propose_typed_number_valid(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {
                "Weight": {"type": "number", "value": "42.5"},
            },
        }
        result = propose_properties(spec)
        assert result["ok"] is True

    def test_propose_typed_invalid_number_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {
                "Weight": {"type": "number", "value": "not-a-number"},
            },
        }
        result = propose_properties(spec)
        assert result["ok"] is False
        assert "numeric string" in result["error"]

    def test_propose_typed_yes_no_valid(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {
                "Approved": {"type": "yes_no", "value": "No"},
            },
        }
        result = propose_properties(spec)
        assert result["ok"] is True

    def test_propose_typed_date_valid(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/path/to/part.SLDPRT",
            "properties": {
                "Created": {"type": "date", "value": "2024-06-15"},
            },
        }
        result = propose_properties(spec)
        assert result["ok"] is True


class TestDryRunProperties:
    """Offline dry_run tests (file existence check)."""

    def test_dry_run_missing_file_fails(self) -> None:
        spec = {
            "kind": "properties",
            "model": "/nonexistent/path/part.SLDPRT",
            "properties": {"PartNo": "BRK-001"},
        }
        result = dry_run_properties(spec)
        assert result["ok"] is False
        assert "model file not found" in result["error"]

    def test_dry_run_existing_file_passes(self, tmp_path) -> None:
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


# ---- semantic_prop_match tests -----------------------------------------------


class TestSemanticPropMatch:
    """Unit tests for SW-normalized read-back comparison."""

    def test_text_exact_match(self) -> None:
        assert semantic_prop_match("text", "BRK-001", "BRK-001") is True

    def test_text_mismatch(self) -> None:
        assert semantic_prop_match("text", "BRK-001", "BRK-002") is False

    def test_number_exact_match(self) -> None:
        assert semantic_prop_match("number", "42.5", "42.5") is True

    def test_number_sw_normalized_six_decimal(self) -> None:
        assert semantic_prop_match("number", "42.5", "42.500000") is True

    def test_number_integer_normalized(self) -> None:
        assert semantic_prop_match("number", "100", "100.000000") is True

    def test_number_mismatch(self) -> None:
        assert semantic_prop_match("number", "42.5", "43.0") is False

    def test_number_non_numeric_got(self) -> None:
        assert semantic_prop_match("number", "42.5", "not-a-number") is False

    def test_date_exact_iso(self) -> None:
        assert semantic_prop_match("date", "2024-06-15", "2024-06-15") is True

    def test_date_iso_vs_us_locale(self) -> None:
        assert semantic_prop_match("date", "2024-06-15", "6/15/2024") is True

    def test_date_mismatch(self) -> None:
        assert semantic_prop_match("date", "2024-06-15", "2024-06-16") is False

    def test_date_unparseable_got(self) -> None:
        assert semantic_prop_match("date", "2024-06-15", "June 15th") is False

    def test_yes_no_exact_match(self) -> None:
        assert semantic_prop_match("yes_no", "Yes", "Yes") is True

    def test_yes_no_mismatch(self) -> None:
        assert semantic_prop_match("yes_no", "Yes", "No") is False
