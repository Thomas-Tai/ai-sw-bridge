"""Tests for drawing spec schema + validator + lifecycle (Wave-16/W19).

Pure-Python -- no SOLIDWORKS required. Covers structural schema rejection,
semantic validation, view mapping, and the propose pipeline.
"""

from __future__ import annotations

import pytest

from ai_sw_bridge.drawing.spec_schema import DRAWING_SPEC_SCHEMA


def _drawing_spec(**overrides: object) -> dict:
    base: dict = {
        "kind": "drawing",
        "name": "test_drawing",
        "model": "test.sldasm",
        "views": ["front", "top", "right", "isometric"],
    }
    base.update(overrides)
    return base


# ---- Schema-level ----


class TestDrawingSchemaValidation:
    def test_accepts_minimal(self) -> None:
        import jsonschema
        jsonschema.validate(_drawing_spec(), DRAWING_SPEC_SCHEMA)

    def test_accepts_with_sheet(self) -> None:
        import jsonschema
        jsonschema.validate(
            _drawing_spec(sheet={"template_size": "A3"}),
            DRAWING_SPEC_SCHEMA,
        )

    def test_rejects_missing_kind(self) -> None:
        import jsonschema
        spec = _drawing_spec()
        del spec["kind"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)

    def test_rejects_wrong_kind(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_drawing_spec(kind="part"), DRAWING_SPEC_SCHEMA)

    def test_rejects_missing_model(self) -> None:
        import jsonschema
        spec = _drawing_spec()
        del spec["model"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, DRAWING_SPEC_SCHEMA)

    def test_rejects_empty_views(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_drawing_spec(views=[]), DRAWING_SPEC_SCHEMA)

    def test_rejects_unknown_view(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", "xray"]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_unknown_sheet_size(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(sheet={"template_size": "XXL"}),
                DRAWING_SPEC_SCHEMA,
            )


# ---- Semantic validation ----


class TestDrawingSemanticValidation:
    def test_accepts_valid(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        validate_drawing_spec(_drawing_spec())

    def test_rejects_wrong_kind(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="kind"):
            validate_drawing_spec(_drawing_spec(kind="part"))

    def test_rejects_empty_name(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="name"):
            validate_drawing_spec(_drawing_spec(name=""))

    def test_rejects_empty_model(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="model"):
            validate_drawing_spec(_drawing_spec(model=""))

    def test_rejects_empty_views(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="views"):
            validate_drawing_spec(_drawing_spec(views=[]))


# ---- Dry run ----


class TestDrawingDryRun:
    def test_rejects_missing_model(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import dry_run_drawing
        result = dry_run_drawing(_drawing_spec(model="/nonexistent/path.sldasm"))
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_accepts_existing_model(self, tmp_path) -> None:
        from ai_sw_bridge.drawing.lifecycle import dry_run_drawing
        model = tmp_path / "test.sldasm"
        model.write_text("dummy")
        result = dry_run_drawing(_drawing_spec(model=str(model)))
        assert result["ok"] is True


# ---- Propose pipeline ----


class TestDrawingPropose:
    def test_propose_accepts_valid(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(_drawing_spec())
        assert result["ok"] is True
        assert result["proposal_id"] is not None
        assert result["kind"] == "drawing"

    def test_propose_rejects_schema_error(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing({"kind": "part", "name": "x"})
        assert result["ok"] is False
        assert "schema" in result["error"]

    def test_dry_run_rejects_missing_model(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing, sw_dry_run_drawing
        p = sw_propose_drawing(_drawing_spec(model="/nonexistent.sldasm"))
        assert p["ok"] is True
        d = sw_dry_run_drawing(p["proposal_id"])
        assert d["ok"] is False
        assert "not found" in d["error"]

    def test_dry_run_accepts_existing(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing, sw_dry_run_drawing
        model = tmp_path / "test.sldasm"
        model.write_text("dummy")
        p = sw_propose_drawing(_drawing_spec(model=str(model)))
        d = sw_dry_run_drawing(p["proposal_id"])
        assert d["ok"] is True
        assert d["state"] == "dry_run_ok"

    def test_commit_rejects_without_dry_run(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing, sw_commit_drawing
        p = sw_propose_drawing(_drawing_spec())
        c = sw_commit_drawing(p["proposal_id"], str(tmp_path / "out.SLDDRW"))
        assert c["ok"] is False
        assert "dry_run" in c["error"]


# ---- View mapping ----


class TestViewMapping:
    def test_all_standard_views_resolve(self) -> None:
        from ai_sw_bridge.drawing.formats import resolve_format
        for name in ("front", "top", "right", "isometric"):
            fmt = resolve_format(name)
            assert fmt.view_name.startswith("*")

    def test_unknown_view_raises(self) -> None:
        from ai_sw_bridge.drawing.formats import resolve_format
        with pytest.raises(ValueError, match="Unknown"):
            resolve_format("xray")


# ---- CLI smoke ----


class TestDrawingCli:
    def test_cli_propose_smoke(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        spec_file = tmp_path / "drawing.json"
        spec_file.write_text(
            '{"kind":"drawing","name":"cli_test",'
            '"model":"x.sldasm","views":["front"]}'
        )
        import argparse
        from ai_sw_bridge.cli.drawing import _run_propose
        args = argparse.Namespace(spec=str(spec_file))
        result = _run_propose(args)
        assert result["ok"] is True


# ---- W17: dimensions flag ----


class TestDimensionsSchema:
    def test_accepts_dimensions_true(self) -> None:
        import jsonschema
        jsonschema.validate(
            _drawing_spec(dimensions=True), DRAWING_SPEC_SCHEMA
        )

    def test_accepts_dimensions_false(self) -> None:
        import jsonschema
        jsonschema.validate(
            _drawing_spec(dimensions=False), DRAWING_SPEC_SCHEMA
        )

    def test_rejects_dimensions_string(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(dimensions="yes"), DRAWING_SPEC_SCHEMA
            )

    def test_rejects_dimensions_int(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(dimensions=1), DRAWING_SPEC_SCHEMA
            )

    def test_dimensions_optional(self) -> None:
        import jsonschema
        jsonschema.validate(_drawing_spec(), DRAWING_SPEC_SCHEMA)


class TestDimensionsPropose:
    def test_propose_with_dimensions_true(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(_drawing_spec(dimensions=True))
        assert result["ok"] is True
        assert result["kind"] == "drawing"

    def test_propose_with_dimensions_false(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(_drawing_spec(dimensions=False))
        assert result["ok"] is True


# ---- W18: bom flag ----


class TestBomSchema:
    def test_accepts_bom_true(self) -> None:
        import jsonschema
        jsonschema.validate(_drawing_spec(bom=True), DRAWING_SPEC_SCHEMA)

    def test_accepts_bom_false(self) -> None:
        import jsonschema
        jsonschema.validate(_drawing_spec(bom=False), DRAWING_SPEC_SCHEMA)

    def test_bom_optional_absent(self) -> None:
        import jsonschema
        jsonschema.validate(_drawing_spec(), DRAWING_SPEC_SCHEMA)

    def test_rejects_bom_string(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_drawing_spec(bom="yes"), DRAWING_SPEC_SCHEMA)

    def test_rejects_bom_int(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_drawing_spec(bom=1), DRAWING_SPEC_SCHEMA)


class TestBomSemanticValidation:
    def test_accepts_bom_true_with_sldasm(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        validate_drawing_spec(_drawing_spec(model="asm.sldasm", bom=True))

    def test_accepts_bom_false_with_sldprt(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        validate_drawing_spec(_drawing_spec(model="part.sldprt", bom=False))

    def test_accepts_bom_absent_with_sldprt(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        validate_drawing_spec(_drawing_spec(model="part.sldprt"))

    def test_rejects_bom_true_with_sldprt(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="assembly model"):
            validate_drawing_spec(_drawing_spec(model="part.sldprt", bom=True))

    def test_rejects_bom_true_with_uppercase_sldprt(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="assembly model"):
            validate_drawing_spec(_drawing_spec(model="Part.SLDPRT", bom=True))

    def test_rejects_bom_non_bool(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="bom must be a boolean"):
            validate_drawing_spec(_drawing_spec(bom="yes"))


class TestBomPropose:
    def test_propose_bom_true_with_sldasm(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(_drawing_spec(model="asm.sldasm", bom=True))
        assert result["ok"] is True

    def test_propose_bom_true_with_sldprt_fails(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(_drawing_spec(model="part.sldprt", bom=True))
        assert result["ok"] is False
        assert "assembly model" in result["error"]

    def test_propose_bom_false_with_sldprt_ok(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(_drawing_spec(model="part.sldprt", bom=False))
        assert result["ok"] is True


# ---- W19: section + detail views ----

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
    "center": [0.5, 0.5],
    "radius": 0.25,
}


class TestSectionDetailSchema:
    """jsonschema structural checks for the oneOf views items (W19)."""

    def test_accepts_section_object(self) -> None:
        import jsonschema
        jsonschema.validate(
            _drawing_spec(views=["front", _SECTION_VIEW]),
            DRAWING_SPEC_SCHEMA,
        )

    def test_accepts_detail_object(self) -> None:
        import jsonschema
        jsonschema.validate(
            _drawing_spec(views=["front", _DETAIL_VIEW]),
            DRAWING_SPEC_SCHEMA,
        )

    def test_accepts_mixed_views(self) -> None:
        import jsonschema
        jsonschema.validate(
            _drawing_spec(views=["front", _SECTION_VIEW, _DETAIL_VIEW]),
            DRAWING_SPEC_SCHEMA,
        )

    def test_accepts_section_without_cut(self) -> None:
        # Schema does NOT enforce cut presence -- that's semantic validation
        import jsonschema
        spec = dict(_SECTION_VIEW)
        del spec["cut"]
        jsonschema.validate(
            _drawing_spec(views=["front", spec]),
            DRAWING_SPEC_SCHEMA,
        )

    def test_accepts_detail_minimal(self) -> None:
        # center and radius are optional at schema level
        import jsonschema
        jsonschema.validate(
            _drawing_spec(views=["front", {"type": "detail", "name": "B", "parent": "front"}]),
            DRAWING_SPEC_SCHEMA,
        )

    def test_rejects_unknown_type(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", {"type": "auxiliary", "name": "C", "parent": "front"}]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_missing_name(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", {"type": "section", "parent": "front", "cut": "vertical"}]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_missing_parent(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", {"type": "section", "name": "A", "cut": "vertical"}]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_extra_properties(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", {**_SECTION_VIEW, "unknown_key": 99}]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_invalid_cut_value(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", {**_SECTION_VIEW, "cut": "diagonal"}]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_center_wrong_length(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", {**_DETAIL_VIEW, "center": [0.5]}]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_negative_radius(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", {**_DETAIL_VIEW, "radius": -1.0}]),
                DRAWING_SPEC_SCHEMA,
            )

    def test_rejects_zero_radius(self) -> None:
        import jsonschema
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                _drawing_spec(views=["front", {**_DETAIL_VIEW, "radius": 0}]),
                DRAWING_SPEC_SCHEMA,
            )


class TestSectionDetailSemanticValidation:
    """validate_drawing_spec cross-field checks for derived views (W19)."""

    def test_accepts_section_with_valid_parent(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        validate_drawing_spec(_drawing_spec(views=["front", _SECTION_VIEW]))

    def test_accepts_detail_with_valid_parent(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        validate_drawing_spec(_drawing_spec(views=["front", _DETAIL_VIEW]))

    def test_accepts_mixed_views(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        validate_drawing_spec(
            _drawing_spec(views=["front", "top", _SECTION_VIEW, _DETAIL_VIEW])
        )

    def test_accepts_horizontal_cut(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        v = {**_SECTION_VIEW, "cut": "horizontal"}
        validate_drawing_spec(_drawing_spec(views=["front", v]))

    def test_accepts_detail_without_center_radius(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        validate_drawing_spec(
            _drawing_spec(views=["front", {"type": "detail", "name": "B", "parent": "front"}])
        )

    def test_rejects_forward_ref_parent(self) -> None:
        # section comes before its parent string view
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="earlier"):
            validate_drawing_spec(
                _drawing_spec(views=[_SECTION_VIEW, "front"])
            )

    def test_rejects_unknown_parent(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        v = {**_SECTION_VIEW, "parent": "bottom"}
        with pytest.raises(ValueError, match="earlier"):
            validate_drawing_spec(_drawing_spec(views=["front", v]))

    def test_rejects_section_without_cut(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        v = {k: val for k, val in _SECTION_VIEW.items() if k != "cut"}
        with pytest.raises(ValueError, match="cut"):
            validate_drawing_spec(_drawing_spec(views=["front", v]))

    def test_rejects_section_invalid_cut(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        v = {**_SECTION_VIEW, "cut": "diagonal"}
        with pytest.raises(ValueError, match="cut"):
            validate_drawing_spec(_drawing_spec(views=["front", v]))

    def test_rejects_section_of_section(self) -> None:
        # derived view cannot reference another derived view as parent
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        sec2 = {"type": "section", "name": "B", "parent": "A", "cut": "horizontal"}
        with pytest.raises(ValueError, match="earlier"):
            validate_drawing_spec(
                _drawing_spec(views=["front", _SECTION_VIEW, sec2])
            )

    def test_rejects_detail_bad_center_length(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        v = {**_DETAIL_VIEW, "center": [0.5]}
        with pytest.raises(ValueError, match="center"):
            validate_drawing_spec(_drawing_spec(views=["front", v]))

    def test_rejects_detail_negative_radius(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        v = {**_DETAIL_VIEW, "radius": -0.1}
        with pytest.raises(ValueError, match="radius"):
            validate_drawing_spec(_drawing_spec(views=["front", v]))

    def test_rejects_non_string_non_dict_entry(self) -> None:
        from ai_sw_bridge.drawing.lifecycle import validate_drawing_spec
        with pytest.raises(ValueError, match="string or object"):
            validate_drawing_spec(_drawing_spec(views=["front", 42]))


class TestSectionDetailPropose:
    """Propose pipeline passes for specs containing derived views (W19)."""

    def test_propose_section_ok(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(
            _drawing_spec(views=["front", _SECTION_VIEW])
        )
        assert result["ok"] is True
        assert result["kind"] == "drawing"

    def test_propose_detail_ok(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(
            _drawing_spec(views=["front", _DETAIL_VIEW])
        )
        assert result["ok"] is True

    def test_propose_mixed_views_ok(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(
            _drawing_spec(views=["front", "top", _SECTION_VIEW, _DETAIL_VIEW])
        )
        assert result["ok"] is True

    def test_propose_forward_ref_fails(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.mutate import sw_propose_drawing
        result = sw_propose_drawing(
            _drawing_spec(views=[_SECTION_VIEW, "front"])
        )
        assert result["ok"] is False
        assert "earlier" in result["error"]
