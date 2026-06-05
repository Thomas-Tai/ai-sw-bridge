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

    def test_accepts_zero_rpy(self) -> None:
        # Phase 1 is translation-only: a zero rotation is allowed.
        spec = _minimal_assembly()
        spec["components"][0]["transform"]["rpy_deg"] = [0, 0, 0]
        validate_assembly(spec)

    def test_rejects_nonzero_rpy_phase1(self) -> None:
        # Non-zero rotation is rejected fail-closed (rotation unsupported in P1).
        spec = _minimal_assembly()
        spec["components"][0]["transform"]["rpy_deg"] = [0, 0, 90]
        with pytest.raises(AssemblyValidationError, match="rotation"):
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


# ---- Phase-2 mate type validation (distance, concentric, parallel, perpendicular) ----

def _mate_spec(mtype: str, **kwargs) -> dict:
    """Helper to build a mate spec with the given type."""
    base = {
        "type": mtype,
        "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
        "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
    }
    base.update(kwargs)
    return base


def _assembly_with_mate(mate: dict) -> dict:
    """Helper to build a minimal assembly with one mate."""
    return {
        "kind": "assembly",
        "name": "test_assy",
        "components": [
            {"id": "a", "part": "a.sldprt", "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": "b.sldprt", "transform": {"xyz_mm": [0, 0, 50]}},
        ],
        "mates": [mate],
    }


class TestPhase2MateValidation:
    """Phase-2 mate type validation rules."""

    def test_accepts_distance_with_value_mm(self) -> None:
        mate = _mate_spec("distance", value_mm=10.0)
        spec = _assembly_with_mate(mate)
        validate_assembly(spec)  # should not raise

    def test_rejects_distance_without_value_mm(self) -> None:
        mate = _mate_spec("distance")
        spec = _assembly_with_mate(mate)
        with pytest.raises(AssemblyValidationError, match="distance mate requires"):
            validate_assembly(spec)

    def test_rejects_distance_negative_value(self) -> None:
        mate = _mate_spec("distance", value_mm=-5.0)
        spec = _assembly_with_mate(mate)
        with pytest.raises(AssemblyValidationError, match="positive number"):
            validate_assembly(spec)

    def test_rejects_distance_zero_value(self) -> None:
        mate = _mate_spec("distance", value_mm=0)
        spec = _assembly_with_mate(mate)
        with pytest.raises(AssemblyValidationError, match="positive number"):
            validate_assembly(spec)

    def test_accepts_concentric_without_value(self) -> None:
        mate = _mate_spec("concentric")
        spec = _assembly_with_mate(mate)
        validate_assembly(spec)  # should not raise

    def test_rejects_concentric_with_value_mm(self) -> None:
        mate = _mate_spec("concentric", value_mm=5.0)
        spec = _assembly_with_mate(mate)
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)

    def test_accepts_parallel_without_value(self) -> None:
        mate = _mate_spec("parallel")
        spec = _assembly_with_mate(mate)
        validate_assembly(spec)  # should not raise

    def test_rejects_parallel_with_value_mm(self) -> None:
        mate = _mate_spec("parallel", value_mm=5.0)
        spec = _assembly_with_mate(mate)
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)

    def test_accepts_perpendicular_without_value(self) -> None:
        mate = _mate_spec("perpendicular")
        spec = _assembly_with_mate(mate)
        validate_assembly(spec)  # should not raise

    def test_rejects_perpendicular_with_value_mm(self) -> None:
        mate = _mate_spec("perpendicular", value_mm=5.0)
        spec = _assembly_with_mate(mate)
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)


# ---- Phase-3 mate type validation (tangent, angle, limit) ----
# Seat-proven W11: tangent (MateTangent), angle (MatePlanarAngleDim, deg->rad),
# limit on distance/angle (Min/Max variation). Width remains de-advertised
# (needs a separate two-reference-set handler path — see DEFERRED.md).

class TestPhase3MateValidation:
    """Phase-3 mate type validation rules (tangent / angle / limit)."""

    def test_tangent_is_advertised(self) -> None:
        assert "tangent" in MATE_TYPES

    def test_angle_is_advertised(self) -> None:
        assert "angle" in MATE_TYPES

    def test_width_is_not_advertised(self) -> None:
        # Width is seat-proven in spike but not production-wired (different
        # selection structure); it must stay gated until its handler ships.
        assert "width" not in MATE_TYPES

    # --- tangent: geometric, no scalar ---

    def test_accepts_tangent_without_value(self) -> None:
        spec = _assembly_with_mate(_mate_spec("tangent"))
        validate_assembly(spec)  # should not raise

    def test_rejects_tangent_with_value_mm(self) -> None:
        spec = _assembly_with_mate(_mate_spec("tangent", value_mm=5.0))
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)

    def test_rejects_tangent_with_value_deg(self) -> None:
        spec = _assembly_with_mate(_mate_spec("tangent", value_deg=30.0))
        with pytest.raises(AssemblyValidationError, match="does not accept 'value_deg'"):
            validate_assembly(spec)

    # --- angle: requires value_deg, rejects value_mm ---

    def test_accepts_angle_with_value_deg(self) -> None:
        spec = _assembly_with_mate(_mate_spec("angle", value_deg=45.0))
        validate_assembly(spec)  # should not raise

    def test_rejects_angle_without_value_deg(self) -> None:
        spec = _assembly_with_mate(_mate_spec("angle"))
        with pytest.raises(AssemblyValidationError, match="angle mate requires 'value_deg'"):
            validate_assembly(spec)

    def test_rejects_angle_with_value_mm(self) -> None:
        spec = _assembly_with_mate(_mate_spec("angle", value_deg=45.0, value_mm=5.0))
        with pytest.raises(AssemblyValidationError, match="does not accept 'value_mm'"):
            validate_assembly(spec)

    # --- limit: distance/angle only, both bounds, min < max ---

    def test_accepts_distance_limit(self) -> None:
        mate = _mate_spec("distance", value_mm=5.0, limit={"min_mm": 3.0, "max_mm": 7.0})
        validate_assembly(_assembly_with_mate(mate))  # should not raise

    def test_accepts_angle_limit(self) -> None:
        mate = _mate_spec("angle", value_deg=45.0, limit={"min_deg": 30.0, "max_deg": 60.0})
        validate_assembly(_assembly_with_mate(mate))  # should not raise

    def test_rejects_limit_on_non_distance_angle(self) -> None:
        mate = _mate_spec("parallel", limit={"min_mm": 3.0, "max_mm": 7.0})
        with pytest.raises(AssemblyValidationError, match="only supported for distance and angle"):
            validate_assembly(_assembly_with_mate(mate))

    def test_rejects_distance_limit_missing_bound(self) -> None:
        mate = _mate_spec("distance", value_mm=5.0, limit={"min_mm": 3.0})
        with pytest.raises(AssemblyValidationError, match="requires both 'min_mm' and 'max_mm'"):
            validate_assembly(_assembly_with_mate(mate))

    def test_rejects_distance_limit_min_ge_max(self) -> None:
        mate = _mate_spec("distance", value_mm=5.0, limit={"min_mm": 7.0, "max_mm": 3.0})
        with pytest.raises(AssemblyValidationError, match="must be less than"):
            validate_assembly(_assembly_with_mate(mate))

    def test_rejects_angle_limit_min_ge_max(self) -> None:
        mate = _mate_spec("angle", value_deg=45.0, limit={"min_deg": 60.0, "max_deg": 30.0})
        with pytest.raises(AssemblyValidationError, match="must be less than"):
            validate_assembly(_assembly_with_mate(mate))
