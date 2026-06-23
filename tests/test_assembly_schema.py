"""Tests for assembly spec schema + validator + propose (Wave-9 Slice 1).

Pure-Python — no SOLIDWORKS required. Covers structural schema rejection,
semantic validation (duplicate ids, part/part_spec XOR, mate cross-refs),
and the propose gate (de-advertised, fail-closed on malformed specs).
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.assembly.schema import (
    ASSEMBLY_SCHEMA,
    HINGE_MATE_SCHEMA,
    MATE_ALIGNMENTS,
    MATE_TYPES,
    WIDTH_MATE_SCHEMA,
)
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

    def test_accepts_nonzero_rpy(self) -> None:
        # Rotation is now supported (W13 proven via Transform2 pipeline).
        spec = _minimal_assembly()
        spec["components"][0]["transform"]["rpy_deg"] = [0, 0, 90]
        validate_assembly(spec)  # should not raise

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
        from ai_sw_bridge.mutate import _sw_propose_feature_add_impl
        result = _sw_propose_feature_add_impl(
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

    def test_width_is_advertised(self) -> None:
        # Width mate PAE cleared in W12 — production handler proven.
        assert "width" in MATE_TYPES

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


# ---- Width mate validation (Wave-12) ----
# Width uses width_faces / tab_faces (2 refs each) instead of a / b.
# De-advertised ("width" not in MATE_TYPES) until the production PAE clears.


def _width_mate_spec(**overrides: object) -> dict:
    """Build a well-formed width mate spec."""
    base: dict = {
        "type": "width",
        "width_faces": [
            {"component": "a", "face_ref": {"normal": [-1, 0, 0]}},
            {"component": "a", "face_ref": {"normal": [1, 0, 0]}},
        ],
        "tab_faces": [
            {"component": "b", "face_ref": {"normal": [-1, 0, 0]}},
            {"component": "b", "face_ref": {"normal": [1, 0, 0]}},
        ],
    }
    base.update(overrides)
    return base


def _assembly_with_width_mate(mate: dict | None = None) -> dict:
    """Minimal assembly with one width mate."""
    if mate is None:
        mate = _width_mate_spec()
    return {
        "kind": "assembly",
        "name": "test_width",
        "components": [
            {"id": "a", "part": "slot.sldprt", "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": "tab.sldprt", "transform": {"xyz_mm": [0, 0, 50]}},
        ],
        "mates": [mate],
    }


class TestWidthMateSchemaValidation:
    """Structural (jsonschema) tests for the width mate schema."""

    def test_width_schema_accepts_well_formed(self) -> None:
        import jsonschema
        jsonschema.validate(_width_mate_spec(), WIDTH_MATE_SCHEMA)

    def test_width_schema_rejects_one_width_face(self) -> None:
        import jsonschema
        spec = _width_mate_spec(width_faces=[
            {"component": "a", "face_ref": {"normal": [-1, 0, 0]}},
        ])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, WIDTH_MATE_SCHEMA)

    def test_width_schema_rejects_three_tab_faces(self) -> None:
        import jsonschema
        spec = _width_mate_spec(tab_faces=[
            {"component": "b", "face_ref": {"normal": [-1, 0, 0]}},
            {"component": "b", "face_ref": {"normal": [1, 0, 0]}},
            {"component": "b", "face_ref": {"normal": [0, 1, 0]}},
        ])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, WIDTH_MATE_SCHEMA)

    def test_width_schema_rejects_stray_alignment(self) -> None:
        import jsonschema
        spec = _width_mate_spec(alignment="aligned")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, WIDTH_MATE_SCHEMA)

    def test_assembly_schema_accepts_width_mate(self) -> None:
        import jsonschema
        jsonschema.validate(_assembly_with_width_mate(), ASSEMBLY_SCHEMA)


class TestWidthMateValidation:
    """Semantic (validate_assembly) tests for width mate rules."""

    def test_accepts_well_formed(self) -> None:
        validate_assembly(_assembly_with_width_mate())

    def test_rejects_missing_width_faces(self) -> None:
        mate = _width_mate_spec()
        del mate["width_faces"]
        mate["width_faces"] = None  # type: ignore[typeddict-item]
        # jsonschema rejects None; validator catches missing set
        mate = {"type": "width", "tab_faces": _width_mate_spec()["tab_faces"]}
        # Use a raw dict to bypass schema — test the validator directly
        spec = _assembly_with_width_mate(mate)
        # Validator should catch missing width_faces
        with pytest.raises(Exception):
            validate_assembly(spec)

    def test_rejects_wrong_count_width_faces(self) -> None:
        mate = _width_mate_spec(width_faces=[
            {"component": "a", "face_ref": {"normal": [-1, 0, 0]}},
        ])
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(Exception):
            validate_assembly(spec)

    def test_rejects_stray_value_mm(self) -> None:
        mate = _width_mate_spec(value_mm=5.0)
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)

    def test_rejects_stray_value_deg(self) -> None:
        mate = _width_mate_spec(value_deg=30.0)
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)

    def test_rejects_stray_limit(self) -> None:
        mate = _width_mate_spec(limit={"min_mm": 3.0, "max_mm": 7.0})
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)

    def test_rejects_stray_a(self) -> None:
        mate = _width_mate_spec(a={"component": "a", "face_ref": {"normal": [0, 0, 1]}})
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)

    def test_rejects_stray_b(self) -> None:
        mate = _width_mate_spec(b={"component": "b", "face_ref": {"normal": [0, 0, 1]}})
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(spec)

    def test_rejects_unknown_component_in_width_faces(self) -> None:
        mate = _width_mate_spec(width_faces=[
            {"component": "ghost", "face_ref": {"normal": [-1, 0, 0]}},
            {"component": "a", "face_ref": {"normal": [1, 0, 0]}},
        ])
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(AssemblyValidationError, match="ghost"):
            validate_assembly(spec)

    def test_rejects_unknown_component_in_tab_faces(self) -> None:
        mate = _width_mate_spec(tab_faces=[
            {"component": "b", "face_ref": {"normal": [-1, 0, 0]}},
            {"component": "ghost", "face_ref": {"normal": [1, 0, 0]}},
        ])
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(AssemblyValidationError, match="ghost"):
            validate_assembly(spec)

    def test_rejects_empty_face_ref_in_width_faces(self) -> None:
        mate = _width_mate_spec(width_faces=[
            {"component": "a", "face_ref": {}},
            {"component": "a", "face_ref": {"normal": [1, 0, 0]}},
        ])
        spec = _assembly_with_width_mate(mate)
        with pytest.raises(AssemblyValidationError, match="face_ref"):
            validate_assembly(spec)


# ---- RPY convention pin (Wave-13) ----
# The rpy_to_transform helper must produce the correct SW IMathTransform
# layout for known rotations. Convention: R = Rz(yaw) . Ry(pitch) . Rx(roll).


class TestRpyConvention:
    """Pin the rpy_deg → 16-element transform matrix convention."""

    def test_identity(self) -> None:
        from ai_sw_bridge.assembly.handlers import _rpy_to_transform
        m = _rpy_to_transform(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        expected = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
        assert [round(v, 6) for v in m] == expected

    def test_90_deg_about_z(self) -> None:
        from ai_sw_bridge.assembly.handlers import _rpy_to_transform
        m = _rpy_to_transform(0.0, 0.0, 90.0, 0.0, 0.0, 0.0)
        # Rz(90°) = [[0,-1,0],[1,0,0],[0,0,1]]
        rot = [round(v, 6) for v in m[:9]]
        assert rot == [0, -1, 0, 1, 0, 0, 0, 0, 1]

    def test_90_deg_about_x(self) -> None:
        from ai_sw_bridge.assembly.handlers import _rpy_to_transform
        m = _rpy_to_transform(90.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        # Rx(90°) = [[1,0,0],[0,0,-1],[0,1,0]]
        rot = [round(v, 6) for v in m[:9]]
        assert rot == [1, 0, 0, 0, 0, -1, 0, 1, 0]

    def test_translation_in_metres(self) -> None:
        from ai_sw_bridge.assembly.handlers import _rpy_to_transform
        m = _rpy_to_transform(0.0, 0.0, 0.0, 0.05, 0.1, 0.2)
        tx, ty, tz = m[9], m[10], m[11]
        assert abs(tx - 0.05) < 1e-9
        assert abs(ty - 0.1) < 1e-9
        assert abs(tz - 0.2) < 1e-9

    def test_scale_is_one(self) -> None:
        from ai_sw_bridge.assembly.handlers import _rpy_to_transform
        m = _rpy_to_transform(45.0, 30.0, 60.0, 1.0, 2.0, 3.0)
        assert m[12] == 1.0


# ---- Component patterns (mirror) -------------------------------------------


class TestComponentPatternsSchema:
    def test_accepts_mirror_pattern(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "a", "plane": "right"},
        ]
        jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_accepts_with_name_modifier(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "a", "plane": "front", "name_modifier": 2},
        ]
        jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_unknown_type(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "linear", "seed": "a", "plane": "right"},
        ]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_invalid_plane(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "a", "plane": "xy"},
        ]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_missing_seed(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "plane": "right"},
        ]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_negative_name_modifier(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "a", "plane": "right", "name_modifier": -1},
        ]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_accepts_no_patterns(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        jsonschema.validate(spec, ASSEMBLY_SCHEMA)


class TestComponentPatternsValidator:
    def test_accepts_valid_mirror(self) -> None:
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "a", "plane": "right"},
        ]
        validate_assembly(spec)

    def test_rejects_unknown_seed(self) -> None:
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "nonexistent", "plane": "right"},
        ]
        with pytest.raises(AssemblyValidationError, match="not found"):
            validate_assembly(spec)

    def test_rejects_unknown_pattern_type(self) -> None:
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "circular", "seed": "a", "plane": "right"},
        ]
        with pytest.raises(AssemblyValidationError, match="unknown pattern type"):
            validate_assembly(spec)

    def test_rejects_bad_plane(self) -> None:
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "a", "plane": "xy"},
        ]
        with pytest.raises(AssemblyValidationError, match="plane must be"):
            validate_assembly(spec)

    def test_rejects_negative_name_modifier(self) -> None:
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "a", "plane": "right", "name_modifier": -1},
        ]
        with pytest.raises(AssemblyValidationError, match="non-negative"):
            validate_assembly(spec)

    def test_accepts_multiple_mirrors(self) -> None:
        spec = _minimal_assembly()
        spec["component_patterns"] = [
            {"type": "mirror", "seed": "a", "plane": "right"},
            {"type": "mirror", "seed": "b", "plane": "front"},
        ]
        validate_assembly(spec)


# ---- Component arrays (linear + circular) ---------------------------------


class TestComponentArraysSchema:
    def test_accepts_linear_array(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "rail", "type": "linear", "part": "r.sldprt",
             "count": 5, "spacing_mm": 40, "direction": [1, 0, 0]},
        ]
        jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_accepts_circular_array(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "bolt", "type": "circular", "part": "b.sldprt",
             "count": 6, "radius_mm": 50, "axis": [0, 0, 1]},
        ]
        jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_count_less_than_2(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "r", "type": "linear", "part": "r.sldprt",
             "count": 1, "spacing_mm": 40, "direction": [1, 0, 0]},
        ]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_zero_spacing(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "r", "type": "linear", "part": "r.sldprt",
             "count": 3, "spacing_mm": 0, "direction": [1, 0, 0]},
        ]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_rejects_unknown_type(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "x", "type": "spiral", "part": "x.sldprt",
             "count": 3, "radius_mm": 50, "axis": [0, 0, 1]},
        ]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, ASSEMBLY_SCHEMA)

    def test_accepts_no_arrays(self) -> None:
        import jsonschema
        spec = _minimal_assembly()
        jsonschema.validate(spec, ASSEMBLY_SCHEMA)


class TestComponentArraysValidator:
    def test_accepts_valid_linear(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "rail", "type": "linear", "part": "r.sldprt",
             "count": 3, "spacing_mm": 40, "direction": [1, 0, 0]},
        ]
        validate_assembly(spec)

    def test_accepts_valid_circular(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "bolt", "type": "circular", "part": "b.sldprt",
             "count": 4, "radius_mm": 50, "axis": [0, 0, 1], "angle_deg": 360},
        ]
        validate_assembly(spec)

    def test_rejects_unknown_type(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "x", "type": "grid", "part": "x.sldprt",
             "count": 3, "spacing_mm": 10, "direction": [1, 0, 0]},
        ]
        with pytest.raises(AssemblyValidationError, match="unknown array type"):
            validate_assembly(spec)

    def test_rejects_count_less_than_2(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "r", "type": "linear", "part": "r.sldprt",
             "count": 1, "spacing_mm": 10, "direction": [1, 0, 0]},
        ]
        with pytest.raises(AssemblyValidationError, match="count must be"):
            validate_assembly(spec)

    def test_rejects_negative_spacing(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "r", "type": "linear", "part": "r.sldprt",
             "count": 3, "spacing_mm": -5, "direction": [1, 0, 0]},
        ]
        with pytest.raises(AssemblyValidationError, match="positive"):
            validate_assembly(spec)

    def test_rejects_zero_direction(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "r", "type": "linear", "part": "r.sldprt",
             "count": 3, "spacing_mm": 10, "direction": [0, 0, 0]},
        ]
        with pytest.raises(AssemblyValidationError, match="non-zero"):
            validate_assembly(spec)

    def test_rejects_zero_axis(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "b", "type": "circular", "part": "b.sldprt",
             "count": 4, "radius_mm": 50, "axis": [0, 0, 0]},
        ]
        with pytest.raises(AssemblyValidationError, match="non-zero"):
            validate_assembly(spec)

    def test_rejects_negative_radius(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "b", "type": "circular", "part": "b.sldprt",
             "count": 4, "radius_mm": -10, "axis": [0, 0, 1]},
        ]
        with pytest.raises(AssemblyValidationError, match="positive"):
            validate_assembly(spec)

    def test_rejects_id_collision(self) -> None:
        """Array expanded id 'a_0' collides with existing component 'a_0'."""
        spec = {
            "kind": "assembly",
            "name": "test",
            "components": [
                {"id": "a_0", "part": "a.sldprt"},
                {"id": "b", "part": "b.sldprt"},
            ],
            "component_arrays": [
                {"id": "a", "type": "linear", "part": "r.sldprt",
                 "count": 3, "spacing_mm": 10, "direction": [1, 0, 0]},
            ],
        }
        with pytest.raises(AssemblyValidationError, match="collides"):
            validate_assembly(spec)

    def test_rejects_missing_part(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "r", "type": "linear",
             "count": 3, "spacing_mm": 10, "direction": [1, 0, 0]},
        ]
        with pytest.raises(AssemblyValidationError, match="part"):
            validate_assembly(spec)

    def test_rejects_duplicate_array_id(self) -> None:
        spec = _minimal_assembly()
        spec["component_arrays"] = [
            {"id": "r", "type": "linear", "part": "r.sldprt",
             "count": 2, "spacing_mm": 10, "direction": [1, 0, 0]},
            {"id": "r", "type": "linear", "part": "r.sldprt",
             "count": 2, "spacing_mm": 10, "direction": [0, 1, 0]},
        ]
        with pytest.raises(AssemblyValidationError, match="duplicate"):
            validate_assembly(spec)


# ---- Exploded views -------------------------------------------------------


def _with_exploded_view(
    spec: dict, *, name: str = "Default", steps: list | None = None
) -> dict:
    if steps is None:
        steps = [
            {
                "components": ["b"],
                "distance_mm": 50.0,
                "direction": "front",
            },
        ]
    spec["exploded_views"] = [{"name": name, "steps": steps}]
    return spec


class TestExplodedViewsSchema:
    def test_accepts_valid_exploded_view(self) -> None:
        spec = _with_exploded_view(_minimal_assembly())
        validate_assembly(spec)

    def test_accepts_multiple_steps(self) -> None:
        spec = _minimal_assembly()
        spec = _with_exploded_view(spec, steps=[
            {"components": ["a"], "distance_mm": 30.0, "direction": "top"},
            {"components": ["b"], "distance_mm": 50.0, "direction": "front",
             "reverse": True},
        ])
        validate_assembly(spec)

    def test_rejects_unknown_direction(self) -> None:
        spec = _with_exploded_view(_minimal_assembly(), steps=[
            {"components": ["b"], "distance_mm": 50.0, "direction": "diagonal"},
        ])
        with pytest.raises(Exception, match="direction"):
            validate_assembly(spec)

    def test_rejects_zero_distance(self) -> None:
        spec = _with_exploded_view(_minimal_assembly(), steps=[
            {"components": ["b"], "distance_mm": 0, "direction": "front"},
        ])
        with pytest.raises(Exception):
            validate_assembly(spec)

    def test_rejects_unknown_component(self) -> None:
        spec = _with_exploded_view(_minimal_assembly(), steps=[
            {"components": ["nonexistent"], "distance_mm": 50.0, "direction": "front"},
        ])
        with pytest.raises(AssemblyValidationError, match="not found"):
            validate_assembly(spec)

    def test_rejects_empty_components(self) -> None:
        spec = _with_exploded_view(_minimal_assembly(), steps=[
            {"components": [], "distance_mm": 50.0, "direction": "front"},
        ])
        with pytest.raises(Exception):
            validate_assembly(spec)

    def test_rejects_empty_steps(self) -> None:
        spec = _minimal_assembly()
        spec["exploded_views"] = [{"name": "Default", "steps": []}]
        with pytest.raises(AssemblyValidationError, match="at least one step"):
            validate_assembly(spec)

    def test_rejects_duplicate_view_name(self) -> None:
        spec = _minimal_assembly()
        step = {"components": ["b"], "distance_mm": 50.0, "direction": "front"}
        spec["exploded_views"] = [
            {"name": "Default", "steps": [step]},
            {"name": "Default", "steps": [step]},
        ]
        with pytest.raises(AssemblyValidationError, match="duplicate"):
            validate_assembly(spec)

    def test_accepts_reverse_boolean(self) -> None:
        spec = _with_exploded_view(_minimal_assembly(), steps=[
            {"components": ["b"], "distance_mm": 50.0, "direction": "right",
             "reverse": False},
        ])
        validate_assembly(spec)

    def test_rejects_non_boolean_reverse(self) -> None:
        spec = _with_exploded_view(_minimal_assembly(), steps=[
            {"components": ["b"], "distance_mm": 50.0, "direction": "front",
             "reverse": "yes"},
        ])
        with pytest.raises(AssemblyValidationError, match="reverse"):
            validate_assembly(spec)

    def test_all_directions_accepted(self) -> None:
        for d in ("front", "top", "right"):
            spec = _with_exploded_view(_minimal_assembly(), steps=[
                {"components": ["b"], "distance_mm": 50.0, "direction": d},
            ])
            validate_assembly(spec)


# ---- W48 Tier-3: slot + hinge ----------------------------------------------


def _slot_mate(**ov: object) -> dict:
    m: dict = {
        "type": "slot",
        "a": {"component": "a", "face_ref": {"is_cylinder": True}},
        "b": {"component": "b", "face_ref": {"is_cylinder": True}},
    }
    m.update(ov)
    return m


def _hinge_mate(**ov: object) -> dict:
    m: dict = {
        "type": "hinge",
        "concentric_faces": [
            {"component": "a", "face_ref": {"is_cylinder": True}},
            {"component": "b", "face_ref": {"is_cylinder": True}},
        ],
        "coincident_faces": [
            {"component": "a", "face_ref": {"planar_normal": [0, 0, 1]}},
            {"component": "b", "face_ref": {"planar_normal": [0, 0, -1]}},
        ],
    }
    m.update(ov)
    return m


def _assembly_with(mate: dict) -> dict:
    spec = _minimal_assembly()
    spec["mates"] = [mate]
    return spec


class TestTier3MateTypes:
    def test_slot_and_hinge_in_mate_types(self) -> None:
        assert "slot" in MATE_TYPES
        assert "hinge" in MATE_TYPES


class TestSlotMateValidation:
    def test_accepts_default_free(self) -> None:
        validate_assembly(_assembly_with(_slot_mate()))

    def test_accepts_centered(self) -> None:
        validate_assembly(_assembly_with(_slot_mate(constraint="centered")))

    def test_accepts_distance_with_scalar(self) -> None:
        validate_assembly(
            _assembly_with(_slot_mate(constraint="distance", distance_mm=5.0))
        )

    def test_rejects_distance_without_scalar(self) -> None:
        with pytest.raises(AssemblyValidationError, match="distance_mm"):
            validate_assembly(_assembly_with(_slot_mate(constraint="distance")))

    def test_accepts_percent_with_scalar(self) -> None:
        validate_assembly(
            _assembly_with(_slot_mate(constraint="percent", percent=40.0))
        )

    def test_rejects_percent_out_of_range(self) -> None:
        with pytest.raises(AssemblyValidationError, match="percent"):
            validate_assembly(
                _assembly_with(_slot_mate(constraint="percent", percent=140.0))
            )

    def test_rejects_unknown_constraint(self) -> None:
        with pytest.raises(AssemblyValidationError, match="not in"):
            validate_assembly(_assembly_with(_slot_mate(constraint="bogus")))


class TestHingeMateSchemaValidation:
    def test_schema_accepts_well_formed(self) -> None:
        import jsonschema
        jsonschema.validate(_hinge_mate(), HINGE_MATE_SCHEMA)

    def test_schema_rejects_one_concentric_face(self) -> None:
        import jsonschema
        m = _hinge_mate(concentric_faces=[
            {"component": "a", "face_ref": {"is_cylinder": True}},
        ])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(m, HINGE_MATE_SCHEMA)

    def test_assembly_schema_accepts_hinge(self) -> None:
        import jsonschema
        jsonschema.validate(_assembly_with(_hinge_mate()), ASSEMBLY_SCHEMA)


class TestHingeMateValidation:
    def test_accepts_well_formed(self) -> None:
        validate_assembly(_assembly_with(_hinge_mate()))

    def test_accepts_alignment(self) -> None:
        validate_assembly(_assembly_with(_hinge_mate(alignment="closest")))

    def test_rejects_wrong_count_concentric(self) -> None:
        m = _hinge_mate(concentric_faces=[
            {"component": "a", "face_ref": {"is_cylinder": True}},
        ])
        with pytest.raises(AssemblyValidationError, match="exactly 2"):
            validate_assembly(_assembly_with(m))

    def test_rejects_stray_a(self) -> None:
        m = _hinge_mate(a={"component": "a", "face_ref": {"normal": [0, 0, 1]}})
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(_assembly_with(m))

    def test_rejects_unknown_component(self) -> None:
        m = _hinge_mate(concentric_faces=[
            {"component": "ghost", "face_ref": {"is_cylinder": True}},
            {"component": "b", "face_ref": {"is_cylinder": True}},
        ])
        with pytest.raises(AssemblyValidationError, match="not found"):
            validate_assembly(_assembly_with(m))


# ---------------------------------------------------------------------------
# W75 advanced mates — symmetric + profile_center
# ---------------------------------------------------------------------------

class TestAdvancedMatesW75Schema:
    """Schema-level acceptance for the W75 advanced mate pair."""

    def test_both_advertised(self) -> None:
        assert "symmetric" in MATE_TYPES
        assert "profile_center" in MATE_TYPES

    def test_assembly_accepts_symmetric(self) -> None:
        import jsonschema
        mate = _mate_spec("symmetric", symmetry_plane="Right Plane")
        jsonschema.validate(_assembly_with_mate(mate), ASSEMBLY_SCHEMA)

    def test_assembly_accepts_profile_center_bare(self) -> None:
        import jsonschema
        jsonschema.validate(
            _assembly_with_mate(_mate_spec("profile_center")), ASSEMBLY_SCHEMA)

    def test_assembly_accepts_profile_center_scalars(self) -> None:
        import jsonschema
        mate = _mate_spec("profile_center", offset_mm=5.0, flip=True,
                          lock_rotation=False)
        jsonschema.validate(_assembly_with_mate(mate), ASSEMBLY_SCHEMA)


class TestAdvancedMatesW75Validation:
    """Semantic (validate_assembly) rules for the W75 advanced mate pair."""

    def test_accepts_symmetric_well_formed(self) -> None:
        validate_assembly(_assembly_with_mate(
            _mate_spec("symmetric", symmetry_plane="Right Plane")))

    def test_symmetric_requires_symmetry_plane(self) -> None:
        with pytest.raises(AssemblyValidationError, match="symmetry_plane"):
            validate_assembly(_assembly_with_mate(_mate_spec("symmetric")))

    def test_symmetric_rejects_empty_symmetry_plane(self) -> None:
        with pytest.raises(AssemblyValidationError, match="symmetry_plane"):
            validate_assembly(_assembly_with_mate(
                _mate_spec("symmetric", symmetry_plane="  ")))

    def test_symmetric_rejects_value_mm(self) -> None:
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(_assembly_with_mate(
                _mate_spec("symmetric", symmetry_plane="Right Plane",
                           value_mm=5.0)))

    def test_symmetric_rejects_profile_center_scalars(self) -> None:
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(_assembly_with_mate(
                _mate_spec("symmetric", symmetry_plane="Right Plane",
                           offset_mm=3.0)))

    def test_accepts_profile_center_well_formed(self) -> None:
        validate_assembly(_assembly_with_mate(
            _mate_spec("profile_center", offset_mm=2.0, lock_rotation=True)))

    def test_profile_center_rejects_symmetry_plane(self) -> None:
        with pytest.raises(AssemblyValidationError, match="symmetry_plane"):
            validate_assembly(_assembly_with_mate(
                _mate_spec("profile_center", symmetry_plane="Right Plane")))

    def test_profile_center_rejects_value_mm(self) -> None:
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(_assembly_with_mate(
                _mate_spec("profile_center", value_mm=5.0)))

    def test_non_advanced_rejects_offset_mm(self) -> None:
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(_assembly_with_mate(
                _mate_spec("concentric", offset_mm=5.0)))


# ---------------------------------------------------------------------------
# W75b mechanical linkage — linear_coupler
# ---------------------------------------------------------------------------

def _lc_mate(**kw) -> dict:
    base = _mate_spec("linear_coupler", ratio_numerator=1.0, ratio_denominator=2.0)
    base["a"]["face_ref"] = {"linear_edge": True}
    base["b"]["face_ref"] = {"linear_edge": True}
    base.update(kw)
    return base


class TestLinearCouplerSchema:
    def test_advertised(self) -> None:
        assert "linear_coupler" in MATE_TYPES

    def test_assembly_accepts_linear_coupler(self) -> None:
        import jsonschema
        jsonschema.validate(_assembly_with_mate(_lc_mate(reverse=True)), ASSEMBLY_SCHEMA)


class TestLinearCouplerValidation:
    def test_accepts_well_formed(self) -> None:
        validate_assembly(_assembly_with_mate(_lc_mate()))

    def test_accepts_with_reverse(self) -> None:
        validate_assembly(_assembly_with_mate(_lc_mate(reverse=True)))

    def test_requires_numerator(self) -> None:
        mate = _lc_mate()
        del mate["ratio_numerator"]
        with pytest.raises(AssemblyValidationError, match="ratio_numerator"):
            validate_assembly(_assembly_with_mate(mate))

    def test_requires_denominator(self) -> None:
        mate = _lc_mate()
        del mate["ratio_denominator"]
        with pytest.raises(AssemblyValidationError, match="ratio_denominator"):
            validate_assembly(_assembly_with_mate(mate))

    def test_rejects_nonpositive_ratio(self) -> None:
        with pytest.raises(AssemblyValidationError, match="positive"):
            validate_assembly(_assembly_with_mate(_lc_mate(ratio_numerator=0)))

    def test_rejects_value_mm(self) -> None:
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(_assembly_with_mate(_lc_mate(value_mm=5.0)))

    def test_non_coupler_rejects_ratio_fields(self) -> None:
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(_assembly_with_mate(
                _mate_spec("concentric", ratio_numerator=1.0)))

    def test_non_coupler_rejects_reverse(self) -> None:
        with pytest.raises(AssemblyValidationError, match="does not accept"):
            validate_assembly(_assembly_with_mate(
                _mate_spec("concentric", reverse=True)))
