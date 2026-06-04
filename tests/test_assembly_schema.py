"""Tests for assembly spec schema + validator + propose (Wave-9 Slice 1).

Pure-Python — no SOLIDWORKS required. Covers structural schema rejection,
semantic validation (duplicate ids, part/part_spec XOR, mate cross-refs),
and the propose gate (de-advertised, fail-closed on malformed specs).
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.assembly.schema import ASSEMBLY_SCHEMA, MATE_ALIGNMENTS, MATE_TYPES
from ai_sw_bridge.assembly.validator import (
    AssemblyValidationError,
    validate_assembly,
)


def _minimal_assembly(**overrides: object) -> dict:
    spec: dict = {
        "kind": "assembly",
        "name": "test_assy",
        "components": [
            {"id": "a", "part": "a.sldprt", "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": "b.sldprt", "transform": {"xyz_mm": [10, 0, 0]}},
        ],
    }
    spec.update(overrides)
    return spec


def _with_mate(spec: dict, **mate_overrides: object) -> dict:
    mate: dict = {
        "type": "coincident",
        "alignment": "aligned",
        "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
        "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
    }
    mate.update(mate_overrides)
    spec["mates"] = [mate]
    return spec


# ---- Schema-level ----------------------------------------------------------


class TestSchemaConstants:
    def test_mate_types(self) -> None:
        assert "coincident" in MATE_TYPES

    def test_mate_alignments(self) -> None:
        assert MATE_ALIGNMENTS == {"aligned", "anti_aligned", "closest"}


# ---- Structural (jsonschema) -----------------------------------------------


class TestSchemaValidation:
    def test_accepts_minimal(self) -> None:
        import jsonschema
        jsonschema.validate(_minimal_assembly(), ASSEMBLY_SCHEMA)

    def test_rejects_missing_kind(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        del spec["kind"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_wrong_kind(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_minimal_assembly(kind="part"), ASSEMBLY_SCHEMA)

    def test_rejects_empty_components(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_minimal_assembly(components=[]), ASSEMBLY_SCHEMA)

    def test_rejects_component_without_id(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _minimal_assembly(components=[{"part": "x.sldprt"}]),
                ASSEMBLY_SCHEMA,
            )

    def test_rejects_unknown_mate_type(self) -> None:
        import jsonschema
        spec = _with_mate(_minimal_assembly(), type="weld")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_unknown_alignment(self) -> None:
        import jsonschema
        spec = _with_mate(_minimal_assembly(), alignment="sideways")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)


# ---- Semantic (validate_assembly) ------------------------------------------


class TestValidateAssembly:
    def test_accepts_minimal(self) -> None:
        validate_assembly(_minimal_assembly())

    def test_accepts_with_mate(self) -> None:
        validate_assembly(_with_mate(_minimal_assembly()))

    def test_accepts_part_spec_source(self) -> None:
        spec = _minimal_assembly()
        spec["components"][0] = {
            "id": "a",
            "part_spec": "shaft.aisw.json",
            "transform": {"xyz_mm": [0, 0, 0]},
        }
        validate_assembly(spec)

    def test_accepts_transform_with_rpy(self) -> None:
        spec = _minimal_assembly()
        spec["components"][0]["transform"]["rpy_deg"] = [0, 0, 90]
        validate_assembly(spec)

    def test_accepts_no_transform(self) -> None:
        spec = _minimal_assembly()
        del spec["components"][0]["transform"]
        validate_assembly(spec)

    def test_accepts_empty_mates(self) -> None:
        validate_assembly(_minimal_assembly(mates=[]))

    def test_rejects_duplicate_component_id(self) -> None:
        spec = _minimal_assembly()
        spec["components"][1]["id"] = "a"
        with pytest.raises(AssemblyValidationError, match="duplicate"):
            validate_assembly(spec)

    def test_rejects_both_part_and_part_spec(self) -> None:
        spec = _minimal_assembly()
        spec["components"][0]["part_spec"] = "also.json"
        with pytest.raises(AssemblyValidationError, match="both"):
            validate_assembly(spec)

    def test_rejects_neither_part_nor_part_spec(self) -> None:
        spec = _minimal_assembly()
        del spec["components"][0]["part"]
        with pytest.raises(AssemblyValidationError, match="either"):
            validate_assembly(spec)

    def test_rejects_bad_xyz_mm(self) -> None:
        spec = _minimal_assembly()
        spec["components"][0]["transform"]["xyz_mm"] = [1, 2]
        with pytest.raises(AssemblyValidationError, match="xyz_mm"):
            validate_assembly(spec)

    def test_rejects_bad_rpy_deg(self) -> None:
        spec = _minimal_assembly()
        spec["components"][0]["transform"]["rpy_deg"] = [0, 0]
        with pytest.raises(AssemblyValidationError, match="rpy_deg"):
            validate_assembly(spec)

    def test_rejects_mate_unknown_component_a(self) -> None:
        spec = _with_mate(_minimal_assembly())
        spec["mates"][0]["a"]["component"] = "nonexistent"
        with pytest.raises(AssemblyValidationError, match="nonexistent"):
            validate_assembly(spec)

    def test_rejects_mate_unknown_component_b(self) -> None:
        spec = _with_mate(_minimal_assembly())
        spec["mates"][0]["b"]["component"] = "ghost"
        with pytest.raises(AssemblyValidationError, match="ghost"):
            validate_assembly(spec)

    def test_rejects_mate_empty_face_ref(self) -> None:
        spec = _with_mate(_minimal_assembly())
        spec["mates"][0]["a"]["face_ref"] = {}
        with pytest.raises(AssemblyValidationError, match="face_ref"):
            validate_assembly(spec)

    def test_rejects_coincident_without_alignment(self) -> None:
        spec = _with_mate(_minimal_assembly())
        del spec["mates"][0]["alignment"]
        with pytest.raises(AssemblyValidationError, match="alignment"):
            validate_assembly(spec)


# ---- Propose gate (de-advertised, fail-closed) -----------------------------


class TestProposeAssembly:
    def test_propose_accepts_valid(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_assembly
        result = sw_propose_assembly(_minimal_assembly())
        assert result["ok"] is True
        assert result["proposal_id"] is not None
        assert result["kind"] == "assembly"

    def test_propose_rejects_schema_error(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_assembly
        result = sw_propose_assembly({"kind": "part", "name": "x"})
        assert result["ok"] is False
        assert "schema" in result["error"]

    def test_propose_rejects_semantic_error(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_assembly
        spec = _minimal_assembly()
        spec["components"][1]["id"] = "a"  # duplicate
        result = sw_propose_assembly(spec)
        assert result["ok"] is False
        assert "duplicate" in result["error"]

    def test_propose_rejects_non_dict(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_assembly
        result = sw_propose_assembly("not a dict")  # type: ignore[arg-type]
        assert result["ok"] is False

    def test_feature_add_does_not_accept_assembly(self, tmp_path, monkeypatch) -> None:
        """Assembly is de-advertised — feature_add must fail-closed for it."""
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_feature_add
        result = sw_propose_feature_add(
            "dummy.sldprt",
            {"type": "assembly"},
            {"components": []},
        )
        assert result["ok"] is False
        assert "unsupported" in result["error"]
