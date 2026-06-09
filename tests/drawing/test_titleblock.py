"""Offline tests for the W38 title-block spec block.

Covers the jsonschema + semantic validation of ``title_block`` on a drawing
spec. The live COM-side authoring (Add3/Get4/SaveAs3/reopen) is exercised
by ``spikes/v0_2x/drawing_titleblock_pae.py`` (S1 seat test).
"""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest

from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
from ai_sw_bridge.drawing.spec_schema import (
    DRAWING_SPEC_SCHEMA,
    TITLE_BLOCK_KNOWN_FIELDS,
    validate_title_block,
)


def _base(**extra: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "kind": "drawing",
        "name": "D1",
        "model": "C:/x/p.sldprt",
        "views": ["front"],
    }
    spec.update(extra)
    return spec


class TestTitleBlockVocabulary:
    def test_known_fields_tuple(self) -> None:
        assert isinstance(TITLE_BLOCK_KNOWN_FIELDS, tuple)
        # DoD-known set: DrawingNo, Title, Revision, DrawnBy, Scale, Material
        # — at minimum these must be present.
        required = {"DrawingNo", "Title", "Revision", "DrawnBy", "Scale", "Material"}
        assert required.issubset(set(TITLE_BLOCK_KNOWN_FIELDS))

    def test_no_duplicates(self) -> None:
        assert len(set(TITLE_BLOCK_KNOWN_FIELDS)) == len(TITLE_BLOCK_KNOWN_FIELDS)


class TestTitleBlockSchema:
    def test_valid_full_block(self) -> None:
        spec = _base(
            title_block={
                "DrawingNo": "BRK-001",
                "Title": "Bracket",
                "Revision": "A",
                "DrawnBy": "TT",
                "Scale": "1:2",
                "Material": "6061-T6",
            }
        )
        jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)
        validate_drawing_spec(spec)

    def test_single_field_accepted(self) -> None:
        spec = _base(title_block={"Title": "X"})
        jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)
        validate_drawing_spec(spec)

    def test_unknown_field_rejected(self) -> None:
        spec = _base(title_block={"DrawingNo": "X", "FooBar": "bad"})
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)

    def test_empty_value_rejected(self) -> None:
        spec = _base(title_block={"DrawingNo": ""})
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)

    def test_empty_block_rejected(self) -> None:
        spec = _base(title_block={})
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)

    def test_non_string_value_rejected(self) -> None:
        spec = _base(title_block={"DrawingNo": 42})  # type: ignore[dict-item]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)

    def test_all_known_fields_accepted(self) -> None:
        tb = {n: f"V{i}" for i, n in enumerate(TITLE_BLOCK_KNOWN_FIELDS)}
        spec = _base(title_block=tb)
        jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)
        validate_drawing_spec(spec)


class TestTitleBlockMutualExclusion:
    def test_sheets_plus_title_block_rejected(self) -> None:
        spec: dict[str, Any] = {
            "kind": "drawing",
            "name": "D",
            "model": "C:/x/p.sldprt",
            "sheets": [{"views": ["front"]}],
            "title_block": {"Title": "X"},
        }
        jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)
        with pytest.raises(ValueError, match="title_block"):
            validate_drawing_spec(spec)

    def test_legacy_views_plus_title_block_ok(self) -> None:
        spec = _base(title_block={"Title": "X"})
        jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)
        validate_drawing_spec(spec)


class TestValidateTitleBlockHelper:
    def test_missing_key_is_silent(self) -> None:
        # A spec with no title_block passes — title_block is optional.
        validate_title_block({}, path="spec")

    def test_non_dict_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a dict"):
            validate_title_block({"title_block": "not a dict"}, path="spec")

    def test_empty_dict_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            validate_title_block({"title_block": {}}, path="spec")

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown field"):
            validate_title_block({"title_block": {"Bogus": "X"}}, path="spec")
