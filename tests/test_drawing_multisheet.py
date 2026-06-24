"""Multi-sheet drawing spec tests (Wave-23).

Pure-Python, no SOLIDWORKS required. Covers:

  - schema-level acceptance of the new ``sheets[]`` authoring mode,
  - semantic validator mutual-exclusion (``views`` XOR ``sheets``),
  - per-sheet view validation (same grammar as legacy mode),
  - cross-sheet parent-reference rejection (parent must be an earlier
    string view WITHIN THE SAME SHEET),
  - duplicate sheet-name rejection,
  - ``_normalize_sheets`` equivalence for legacy vs multi-sheet modes,
  - ``dry_run_drawing`` surfaces per-sheet counts.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_sw_bridge.drawing.lifecycle import (
    _normalize_sheets,
    dry_run_drawing,
    validate_drawing_spec,
)
from ai_sw_bridge.drawing.spec_schema import DRAWING_SPEC_SCHEMA


def _multi_sheet_spec(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "drawing",
        "name": "multisheet_test",
        "model": "test.sldasm",
        "sheets": [
            {
                "name": "Overview",
                "template_size": "A3",
                "views": ["front", "isometric"],
            },
            {
                "name": "Detail-A",
                "template_size": "A4",
                "views": ["front"],
            },
        ],
    }
    base.update(overrides)
    return base


def _legacy_spec(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "drawing",
        "name": "legacy_test",
        "model": "test.sldasm",
        "views": ["front", "top", "right", "isometric"],
    }
    base.update(overrides)
    return base


# ---- Schema-level ----


class TestMultiSheetSchema:
    def test_accepts_two_sheets(self) -> None:
        import jsonschema

        jsonschema.validate(_multi_sheet_spec(), DRAWING_SPEC_SCHEMA)

    def test_accepts_single_sheet_array(self) -> None:
        import jsonschema

        jsonschema.validate(
            _multi_sheet_spec(sheets=[{"views": ["front"]}]),
            DRAWING_SPEC_SCHEMA,
        )

    def test_rejects_empty_sheets_array(self) -> None:
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_multi_sheet_spec(sheets=[]), DRAWING_SPEC_SCHEMA)

    def test_rejects_sheet_without_views(self) -> None:
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _multi_sheet_spec(
                    sheets=[{"name": "A"}, {"name": "B", "views": ["front"]}]
                ),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_unknown_template_size(self) -> None:
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _multi_sheet_spec(
                    sheets=[
                        {"name": "A", "views": ["front"], "template_size": "LETTER"}
                    ]
                ),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_unknown_view_string(self) -> None:
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _multi_sheet_spec(sheets=[{"views": ["front", "xray"]}]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_unknown_extra_key_on_sheet(self) -> None:
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _multi_sheet_spec(
                    sheets=[{"views": ["front"], "orientation": "landscape"}]
                ),
                DRAWING_SPEC_SCHEMA,
            )

    def test_legacy_views_still_accepted(self) -> None:
        import jsonschema

        jsonschema.validate(_legacy_spec(), DRAWING_SPEC_SCHEMA)


# ---- Semantic validator: authoring mode rules ----


class TestMultiSheetValidatorMode:
    def test_rejects_both_modes_set(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            validate_drawing_spec(_multi_sheet_spec(views=["front"]))

    def test_rejects_neither_mode(self) -> None:
        with pytest.raises(ValueError, match="must declare"):
            validate_drawing_spec({"kind": "drawing", "name": "x", "model": "x.sldasm"})

    def test_rejects_sheet_key_with_sheets_array(self) -> None:
        with pytest.raises(ValueError, match="sheet"):
            validate_drawing_spec(_multi_sheet_spec(sheet={"template_size": "A3"}))

    def test_rejects_top_level_dimensions_with_sheets(self) -> None:
        with pytest.raises(ValueError, match="dimensions"):
            validate_drawing_spec(_multi_sheet_spec(dimensions=True))

    def test_rejects_top_level_bom_with_sheets(self) -> None:
        with pytest.raises(ValueError, match="bom"):
            validate_drawing_spec(_multi_sheet_spec(bom=True))

    def test_rejects_empty_sheets_array(self) -> None:
        # Schema rejects this too, but the validator provides a clear message
        # if the schema layer is bypassed.
        with pytest.raises(ValueError, match="sheets"):
            validate_drawing_spec(_multi_sheet_spec(sheets=[]))

    def test_rejects_duplicate_sheet_names(self) -> None:
        with pytest.raises(ValueError, match="duplicates"):
            validate_drawing_spec(
                _multi_sheet_spec(
                    sheets=[
                        {"name": "A", "views": ["front"]},
                        {"name": "A", "views": ["top"]},
                    ]
                )
            )

    def test_accepts_unnamed_sheets(self) -> None:
        validate_drawing_spec(
            _multi_sheet_spec(sheets=[{"views": ["front"]}, {"views": ["top"]}])
        )


# ---- Per-sheet view validation reuses the legacy grammar ----


_SECTION_VIEW = {
    "type": "section",
    "name": "A",
    "parent": "front",
    "cut": "vertical",
}
_DETAIL_VIEW = {
    "type": "detail",
    "name": "B",
    "parent": "front",
}


class TestMultiSheetViewValidation:
    def test_derived_view_ok_in_same_sheet(self) -> None:
        validate_drawing_spec(
            _multi_sheet_spec(
                sheets=[
                    {"name": "S1", "views": ["front", _SECTION_VIEW]},
                    {"name": "S2", "views": ["front", _DETAIL_VIEW]},
                ]
            )
        )

    def test_rejects_cross_sheet_parent(self) -> None:
        # Sheet 2 references "front" which lives on sheet 1 — must reject.
        # The per-sheet validator only sees the current sheet's seen-string-views.
        with pytest.raises(ValueError, match="earlier"):
            validate_drawing_spec(
                _multi_sheet_spec(
                    sheets=[
                        {"name": "S1", "views": ["front", _SECTION_VIEW]},
                        {
                            "name": "S2",
                            "views": [
                                "top",
                                {
                                    "type": "detail",
                                    "name": "B",
                                    "parent": "front",
                                },
                            ],
                        },
                    ]
                )
            )

    def test_rejects_forward_ref_within_same_sheet(self) -> None:
        with pytest.raises(ValueError, match="earlier"):
            validate_drawing_spec(
                _multi_sheet_spec(
                    sheets=[
                        {"name": "S1", "views": [_SECTION_VIEW, "front"]},
                    ]
                )
            )

    def test_rejects_unknown_view_in_sheet(self) -> None:
        with pytest.raises(ValueError, match="unknown view"):
            validate_drawing_spec(
                _multi_sheet_spec(sheets=[{"views": ["front", "xray"]}])
            )

    def test_bom_on_part_rejected_per_sheet(self) -> None:
        with pytest.raises(ValueError, match="assembly"):
            validate_drawing_spec(
                {
                    "kind": "drawing",
                    "name": "x",
                    "model": "box.SLDPRT",
                    "sheets": [
                        {"name": "S1", "views": ["front"], "bom": True},
                    ],
                }
            )


# ---- _normalize_sheets ----


class TestNormalizeSheets:
    def test_legacy_mode_returns_one_sheet(self) -> None:
        sheets = _normalize_sheets(_legacy_spec(sheet={"template_size": "A2"}))
        assert len(sheets) == 1
        assert sheets[0]["name"] is None
        assert sheets[0]["template_size"] == "A2"
        assert sheets[0]["views"] == ["front", "top", "right", "isometric"]

    def test_legacy_mode_defaults(self) -> None:
        sheets = _normalize_sheets(_legacy_spec())
        assert len(sheets) == 1
        assert sheets[0]["name"] is None
        assert sheets[0]["template_size"] is None
        assert sheets[0]["dimensions"] is False
        assert sheets[0]["bom"] is False

    def test_multisheet_preserves_array(self) -> None:
        spec = _multi_sheet_spec()
        sheets = _normalize_sheets(spec)
        assert len(sheets) == 2
        assert sheets[0]["name"] == "Overview"
        assert sheets[0]["template_size"] == "A3"
        assert sheets[0]["views"] == ["front", "isometric"]
        assert sheets[1]["name"] == "Detail-A"
        assert sheets[1]["template_size"] == "A4"
        assert sheets[1]["views"] == ["front"]

    def test_multisheet_fills_defaults(self) -> None:
        sheets = _normalize_sheets(_multi_sheet_spec(sheets=[{"views": ["front"]}]))
        assert sheets[0]["name"] is None
        assert sheets[0]["template_size"] is None
        assert sheets[0]["dimensions"] is False
        assert sheets[0]["bom"] is False


# ---- dry_run_drawing surfaces per-sheet info ----


class TestDryRunMultiSheet:
    def test_multisheet_reports_sheets(self, tmp_path) -> None:
        model = tmp_path / "test.sldasm"
        model.write_text("dummy")
        spec = _multi_sheet_spec(model=str(model))
        result = dry_run_drawing(spec)
        assert result["ok"] is True
        assert result["sheets_requested"] == 2
        assert result["views_per_sheet"] == [2, 1]
        assert "views_requested" not in result

    def test_legacy_reports_views(self, tmp_path) -> None:
        model = tmp_path / "test.sldasm"
        model.write_text("dummy")
        result = dry_run_drawing(_legacy_spec(model=str(model)))
        assert result["ok"] is True
        assert result["views_requested"] == [
            "front",
            "top",
            "right",
            "isometric",
        ]
        assert "sheets_requested" not in result
