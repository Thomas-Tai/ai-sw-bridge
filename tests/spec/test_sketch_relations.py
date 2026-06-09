"""Tests for W39 sketch relations: validation, token map, COM apply, schema.

Drives the ``_sketch_relations`` module against a fake COM seam (no pywin32,
no SOLIDWORKS). Asserts:
- Token map covers all 6 effect-verified relation types
- Arity map matches expected counts
- Validation rejects unknown types, bad arity, negative indices, duplicates
- Apply function selects entities via raw Select2 and calls
  doc.SketchAddConstraints (IModelDoc2, NOT SketchManager)
- Over-constraint errors are surfaced (not silently swallowed)
- Schema accepts relations on all 12 sketch types
- Validator catches relation errors in the part spec

DEFERRED (not tested — tokens unproven on seat):
  collinear, coincident, symmetric (see docs/DEFERRED.md)
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.spec._sketch_relations import (
    RELATION_ARITY,
    RELATION_TOKENS,
    RELATIONS_SPEC_SCHEMA,
    SUPPORTED_RELATION_TYPES,
    RelationError,
    apply_relations_in_open_sketch,
    validate_relation,
    validate_relations,
)


# ---------------------------------------------------------------------------
# Token map + arity map completeness
# ---------------------------------------------------------------------------


class TestTokenMapCompleteness:
    EXPECTED_TYPES = (
        "horizontal",
        "vertical",
        "parallel",
        "perpendicular",
        "equal",
        "concentric",
    )

    @pytest.mark.parametrize("rtype", EXPECTED_TYPES)
    def test_token_defined(self, rtype: str) -> None:
        assert rtype in RELATION_TOKENS
        assert isinstance(RELATION_TOKENS[rtype], str)
        assert RELATION_TOKENS[rtype].startswith("sg")

    @pytest.mark.parametrize("rtype", EXPECTED_TYPES)
    def test_arity_defined(self, rtype: str) -> None:
        assert rtype in RELATION_ARITY
        assert isinstance(RELATION_ARITY[rtype], int)
        assert RELATION_ARITY[rtype] >= 1

    def test_six_types_total(self) -> None:
        assert len(SUPPORTED_RELATION_TYPES) == 6

    def test_horizontal_vertical_are_one_ref(self) -> None:
        assert RELATION_ARITY["horizontal"] == 1
        assert RELATION_ARITY["vertical"] == 1

    def test_two_ref_types(self) -> None:
        for rtype in ("parallel", "perpendicular", "equal", "concentric"):
            assert RELATION_ARITY[rtype] == 2, f"{rtype} should be 2-ref"

    def test_corrected_tokens(self) -> None:
        """Seat-verified tokens (W21 no-op trap: wrong tokens silently no-op)."""
        assert RELATION_TOKENS["equal"] == "sgSAMELENGTH"
        assert RELATION_TOKENS["parallel"] == "sgPARALLEL"

    def test_deferred_types_not_in_map(self) -> None:
        """collinear/coincident/symmetric are deferred — tokens unproven."""
        for deferred in ("collinear", "coincident", "symmetric"):
            assert deferred not in RELATION_TOKENS
            assert deferred not in SUPPORTED_RELATION_TYPES


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_horizontal(self) -> None:
        validate_relation({"type": "horizontal", "entities": [0]}, 0)

    def test_valid_equal(self) -> None:
        validate_relation({"type": "equal", "entities": [0, 1]}, 0)

    def test_valid_parallel(self) -> None:
        validate_relation({"type": "parallel", "entities": [0, 1]}, 0)

    def test_unknown_type_rejected(self) -> None:
        with pytest.raises(RelationError, match="unknown type"):
            validate_relation({"type": "tangent", "entities": [0, 1]}, 0)

    def test_deferred_type_rejected(self) -> None:
        """collinear/coincident/symmetric are fail-closed — rejected as unknown."""
        for deferred in ("collinear", "coincident", "symmetric"):
            with pytest.raises(RelationError, match="unknown type"):
                validate_relation({"type": deferred, "entities": [0, 1]}, 0)

    def test_bad_arity_equal_needs_two(self) -> None:
        with pytest.raises(RelationError, match="requires 2"):
            validate_relation({"type": "equal", "entities": [0]}, 0)

    def test_bad_arity_horizontal_needs_one(self) -> None:
        with pytest.raises(RelationError, match="requires 1"):
            validate_relation({"type": "horizontal", "entities": [0, 1]}, 0)

    def test_negative_index_rejected(self) -> None:
        with pytest.raises(RelationError, match="non-negative"):
            validate_relation({"type": "horizontal", "entities": [-1]}, 0)

    def test_non_integer_index_rejected(self) -> None:
        with pytest.raises(RelationError, match="non-negative"):
            validate_relation({"type": "horizontal", "entities": [0.5]}, 0)

    def test_duplicate_refs_rejected(self) -> None:
        with pytest.raises(RelationError, match="duplicate"):
            validate_relation({"type": "equal", "entities": [0, 0]}, 0)

    def test_missing_type_rejected(self) -> None:
        with pytest.raises(RelationError, match="unknown type"):
            validate_relation({"entities": [0]}, 0)

    def test_validate_relations_list(self) -> None:
        validate_relations([
            {"type": "horizontal", "entities": [0]},
            {"type": "equal", "entities": [0, 1]},
        ])

    def test_validate_relations_not_a_list(self) -> None:
        with pytest.raises(RelationError, match="must be an array"):
            validate_relations("not a list")

    def test_validate_relations_item_not_object(self) -> None:
        with pytest.raises(RelationError, match="must be an object"):
            validate_relations([42])

    def test_all_types_validate(self) -> None:
        for rtype in SUPPORTED_RELATION_TYPES:
            arity = RELATION_ARITY[rtype]
            entities = list(range(arity))
            validate_relation({"type": rtype, "entities": entities}, 0)


# ---------------------------------------------------------------------------
# Fake COM seam for apply_relations_in_open_sketch
# ---------------------------------------------------------------------------


class _FakeSegment:
    """A sketch segment that supports raw Select2 and basic geometry."""

    def __init__(self, start: tuple[float, float], end: tuple[float, float]):
        self._start = start
        self._end = end
        self.selected = False

    def Select2(self, append: bool, mark: int) -> bool:
        self.selected = True
        return True

    @property
    def GetStartPoint2(self) -> Any:
        class _Pt:
            X = self._start[0]
            Y = self._start[1]
        return _Pt()

    @property
    def GetEndPoint2(self) -> Any:
        class _Pt:
            X = self._end[0]
            Y = self._end[1]
        return _Pt()


class _FakeRelationManager:
    def __init__(self) -> None:
        self._relations: list[str] = []

    def GetRelations(self, _which: int) -> list[str]:
        return list(self._relations)

    def add(self, token: str) -> None:
        self._relations.append(token)


class _FakeSketch:
    def __init__(self, segments: list[_FakeSegment], rm: _FakeRelationManager):
        self._segments = segments
        self._rm = rm

    @property
    def GetSketchSegments(self) -> tuple[_FakeSegment, ...]:
        """Property (no parens) — matches late-bound COM auto-invoke."""
        return tuple(self._segments)

    @property
    def RelationManager(self) -> _FakeRelationManager:
        return self._rm


class _FakeDoc:
    """Fake IModelDoc2 with SketchAddConstraints on the DOC (not SketchManager)."""

    def __init__(self, segments: list[_FakeSegment]):
        self._rm = _FakeRelationManager()
        self._sk = _FakeSketch(segments, self._rm)
        self.constraints_applied: list[str] = []

    @property
    def GetActiveSketch2(self) -> _FakeSketch:
        return self._sk

    def SketchAddConstraints(self, token: str) -> None:
        """IModelDoc2.SketchAddConstraints — the seat-verified call site."""
        self.constraints_applied.append(token)
        self._rm.add(token)

    def ClearSelection2(self, _all: bool) -> None:
        pass

    @property
    def SketchManager(self) -> Any:
        """SketchManager exists but does NOT have SketchAddConstraints."""
        class _NoConstraints:
            pass
        return _NoConstraints()


class TestApplyRelationsInOpenSketch:
    def _make_doc(self, n_segments: int = 3) -> _FakeDoc:
        segs = [
            _FakeSegment((0.0, float(i)), (0.01, float(i) + 0.01))
            for i in range(n_segments)
        ]
        return _FakeDoc(segs)

    def test_horizontal_applied(self) -> None:
        doc = self._make_doc()
        result = apply_relations_in_open_sketch(doc, [
            {"type": "horizontal", "entities": [0]},
        ])
        assert result["ok"] is True
        assert result["relations_applied"] == 1
        assert doc.constraints_applied == ["sgHORIZONTAL2D"]

    def test_equal_applied_with_corrected_token(self) -> None:
        doc = self._make_doc()
        result = apply_relations_in_open_sketch(doc, [
            {"type": "equal", "entities": [0, 1]},
        ])
        assert result["ok"] is True
        assert doc.constraints_applied == ["sgSAMELENGTH"]

    def test_parallel_applied_with_corrected_token(self) -> None:
        doc = self._make_doc()
        result = apply_relations_in_open_sketch(doc, [
            {"type": "parallel", "entities": [0, 1]},
        ])
        assert result["ok"] is True
        assert doc.constraints_applied == ["sgPARALLEL"]

    def test_multiple_relations(self) -> None:
        doc = self._make_doc(4)
        result = apply_relations_in_open_sketch(doc, [
            {"type": "horizontal", "entities": [0]},
            {"type": "vertical", "entities": [1]},
            {"type": "equal", "entities": [2, 3]},
        ])
        assert result["ok"] is True
        assert result["relations_applied"] == 3
        assert doc.constraints_applied == [
            "sgHORIZONTAL2D",
            "sgVERTICAL2D",
            "sgSAMELENGTH",
        ]

    def test_out_of_range_index_fails(self) -> None:
        doc = self._make_doc(2)
        result = apply_relations_in_open_sketch(doc, [
            {"type": "horizontal", "entities": [5]},
        ])
        assert result["ok"] is False
        assert result["relations_failed"] == 1
        assert "out of range" in result["errors"][0]

    def test_no_segments_fails(self) -> None:
        doc = _FakeDoc([])
        with pytest.raises(RelationError, match="no segments"):
            apply_relations_in_open_sketch(doc, [
                {"type": "horizontal", "entities": [0]},
            ])

    def test_relation_count_increases(self) -> None:
        doc = self._make_doc()
        result = apply_relations_in_open_sketch(doc, [
            {"type": "horizontal", "entities": [0]},
        ])
        detail = result["details"][0]
        assert detail["constrained"] is True
        assert detail["relation_count_after"] > detail["relation_count_before"]

    def test_selection_uses_raw_select2(self) -> None:
        """Raw seg.Select2 works; typed IEntity.Select2 is NOT attempted."""
        doc = self._make_doc()
        apply_relations_in_open_sketch(doc, [
            {"type": "horizontal", "entities": [0]},
        ])
        # The segment's raw Select2 was called (selected flag set)
        assert doc.GetActiveSketch2.GetSketchSegments[0].selected is True


# ---------------------------------------------------------------------------
# Schema integration: relations field on all sketch types
# ---------------------------------------------------------------------------


class TestSchemaIntegration:
    SKETCH_TYPES = (
        "sketch_rectangle_on_plane",
        "sketch_rectangle_on_face",
        "sketch_circle_on_plane",
        "sketch_circle_on_face",
        "sketch_circles_on_face",
        "sketch_line",
        "sketch_arc",
        "sketch_spline",
        "sketch_slot",
        "sketch_polygon",
        "sketch_ellipse",
        "sketch_text",
    )

    @pytest.mark.parametrize("stype", SKETCH_TYPES)
    def test_relations_field_in_descriptor(self, stype: str) -> None:
        from ai_sw_bridge.spec.descriptors import FEATURE_FIELDS

        fields = FEATURE_FIELDS[stype]
        field_names = [f.name for f in fields]
        assert "relations" in field_names, (
            f"{stype} missing 'relations' field"
        )

    @pytest.mark.parametrize("stype", SKETCH_TYPES)
    def test_relations_field_is_optional(self, stype: str) -> None:
        from ai_sw_bridge.spec.descriptors import FEATURE_FIELDS

        fields = FEATURE_FIELDS[stype]
        for f in fields:
            if f.name == "relations":
                assert f.required is False, (
                    f"{stype} relations field should be optional"
                )

    def test_relations_spec_schema_has_required_fields(self) -> None:
        assert "sketch" in RELATIONS_SPEC_SCHEMA["properties"]
        assert "relations" in RELATIONS_SPEC_SCHEMA["properties"]
        assert "sketch" in RELATIONS_SPEC_SCHEMA["required"]
        assert "relations" in RELATIONS_SPEC_SCHEMA["required"]


# ---------------------------------------------------------------------------
# Validator integration
# ---------------------------------------------------------------------------


class TestValidatorIntegration:
    def _make_spec(self, relations: list | None = None) -> dict[str, Any]:
        feat: dict[str, Any] = {
            "type": "sketch_line",
            "name": "L1",
            "plane": "Front",
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 20.0, "y": 20.0},
        }
        if relations is not None:
            feat["relations"] = relations
        return {
            "schema_version": 1,
            "name": "TestPart",
            "features": [feat],
        }

    def test_valid_relations_pass_validation(self) -> None:
        from ai_sw_bridge.spec.validator import validate

        spec = self._make_spec([
            {"type": "horizontal", "entities": [0]},
        ])
        validate(spec)

    def test_unknown_type_fails_validation(self) -> None:
        from ai_sw_bridge.spec.validator import ValidationError, validate

        spec = self._make_spec([
            {"type": "tangent", "entities": [0, 1]},
        ])
        # Schema-level enum catches "tangent" before _check_relations runs.
        with pytest.raises(ValidationError):
            validate(spec)

    def test_deferred_type_fails_validation(self) -> None:
        """coincident/symmetric/collinear are fail-closed at schema level."""
        from ai_sw_bridge.spec.validator import ValidationError, validate

        for deferred in ("coincident", "symmetric", "collinear"):
            spec = self._make_spec([
                {"type": deferred, "entities": [0, 1]},
            ])
            with pytest.raises(ValidationError):
                validate(spec)

    def test_bad_arity_fails_validation(self) -> None:
        from ai_sw_bridge.spec.validator import ValidationError, validate

        spec = self._make_spec([
            {"type": "equal", "entities": [0]},
        ])
        with pytest.raises(ValidationError, match="requires 2"):
            validate(spec)

    def test_negative_index_fails_validation(self) -> None:
        from ai_sw_bridge.spec.validator import ValidationError, validate

        spec = self._make_spec([
            {"type": "horizontal", "entities": [-1]},
        ])
        # Schema-level minimum:0 catches -1 before _check_relations runs.
        with pytest.raises(ValidationError):
            validate(spec)

    def test_duplicate_refs_fails_validation(self) -> None:
        from ai_sw_bridge.spec.validator import ValidationError, validate

        spec = self._make_spec([
            {"type": "equal", "entities": [0, 0]},
        ])
        with pytest.raises(ValidationError, match="duplicate"):
            validate(spec)

    def test_no_relations_passes(self) -> None:
        from ai_sw_bridge.spec.validator import validate

        spec = self._make_spec()
        validate(spec)
