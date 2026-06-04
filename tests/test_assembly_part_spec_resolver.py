"""Tests for assembly part_spec build-then-place resolver (Wave-9 Slice 8).

Verifies the lifecycle:
  - loads a part spec JSON file (parse + spec.validator.validate),
  - builds it to a .sldprt on disk via ``spec.builder.build`` (mocked here),
  - then places it as a component in the assembly.

dry_run validates only (no build). commit builds.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_sw_bridge.assembly.lifecycle import (
    _build_part_spec,
    _load_part_spec,
    commit_assembly,
    dry_run_assembly,
)


def _minimal_part_spec() -> dict:
    """The smallest spec that passes spec.validator.validate."""
    return {
        "schema_version": 1,
        "name": "tiny_box",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 5.0,
            },
        ],
    }


def _write_part_spec(path: Path, spec: dict | None = None) -> Path:
    data = spec if spec is not None else _minimal_part_spec()
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---- _load_part_spec -------------------------------------------------------


class TestLoadPartSpec:
    def test_loads_valid_spec(self, tmp_path: Path) -> None:
        p = _write_part_spec(tmp_path / "box.json")
        loaded = _load_part_spec(str(p))
        assert loaded["name"] == "tiny_box"
        assert len(loaded["features"]) == 2

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _load_part_spec(str(tmp_path / "nope.json"))

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{ not json", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid JSON"):
            _load_part_spec(str(p))

    def test_non_object_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "arr.json"
        p.write_text("[1,2,3]", encoding="utf-8")
        with pytest.raises(ValueError, match="top-level"):
            _load_part_spec(str(p))

    def test_invalid_schema_raises(self, tmp_path: Path) -> None:
        p = _write_part_spec(tmp_path / "bad_schema.json", {"name": "x"})
        with pytest.raises(ValueError, match="validation failed"):
            _load_part_spec(str(p))


# ---- _build_part_spec (mocked) --------------------------------------------


class TestBuildPartSpec:
    def test_ok_writes_save_as(self, tmp_path: Path) -> None:
        save_to = str(tmp_path / "built.SLDPRT")
        fake_result = MagicMock()
        fake_result.ok = True
        fake_result.error = None
        fake_result.save_as_verified = True
        fake_result.features_built = ["SK_Box", "EX_Box"]

        with patch(
            "ai_sw_bridge.spec.builder.build",
            return_value=fake_result,
        ) as mock_build:
            def _side_effect(spec, save_as=None, save_format="current", **kwargs):
                Path(save_as).write_text("fake")
                return fake_result

            mock_build.side_effect = _side_effect
            out = _build_part_spec(_minimal_part_spec(), save_to)

        assert out["ok"] is True
        assert out["save_as"] == save_to
        assert out["features_built"] == ["SK_Box", "EX_Box"]

    def test_build_failure_reports_error(self, tmp_path: Path) -> None:
        save_to = str(tmp_path / "failed.SLDPRT")
        fake_result = MagicMock()
        fake_result.ok = False
        fake_result.error = "feature X raised"
        fake_result.save_as_verified = None
        fake_result.features_built = []

        with patch(
            "ai_sw_bridge.spec.builder.build",
            return_value=fake_result,
        ):
            out = _build_part_spec(_minimal_part_spec(), save_to)

        assert out["ok"] is False
        assert "feature X raised" in out["error"]

    def test_build_ok_but_file_missing_fails(self, tmp_path: Path) -> None:
        save_to = str(tmp_path / "ghost.SLDPRT")
        fake_result = MagicMock()
        fake_result.ok = True
        fake_result.error = None
        fake_result.save_as_verified = None
        fake_result.features_built = []
        # Note: we do NOT materialize the file.

        with patch(
            "ai_sw_bridge.spec.builder.build",
            return_value=fake_result,
        ):
            out = _build_part_spec(_minimal_part_spec(), save_to)

        assert out["ok"] is False
        assert "not on disk" in out["error"]


# ---- dry_run: validates part_spec, does NOT build -------------------------


class TestDryRunPartSpec:
    def test_validates_part_spec_file(self, tmp_path: Path) -> None:
        spec_path = _write_part_spec(tmp_path / "lid.json")
        base_path = tmp_path / "base.sldprt"
        base_path.write_text("fake")

        asm_spec = {
            "kind": "assembly",
            "name": "a",
            "components": [
                {"id": "base", "part": str(base_path)},
                {"id": "lid", "part_spec": str(spec_path)},
            ],
            "mates": [
                {
                    "type": "coincident",
                    "alignment": "aligned",
                    "a": {"component": "base", "face_ref": {"normal": [0, 0, 1]}},
                    "b": {"component": "lid", "face_ref": {"normal": [0, 0, -1]}},
                },
            ],
        }

        # Patch _build_part_spec to assert it is NEVER called.
        with patch(
            "ai_sw_bridge.assembly.lifecycle._build_part_spec",
            side_effect=AssertionError("dry_run must not build"),
        ):
            result = dry_run_assembly(asm_spec)

        assert result["ok"] is True
        assert result["part_spec_validated"] == {"lid": str(spec_path)}
        assert result["sources"]["lid"] == "part_spec"
        assert result["sources"]["base"] == "part"

    def test_missing_part_spec_file_fails(self, tmp_path: Path) -> None:
        base_path = tmp_path / "base.sldprt"
        base_path.write_text("fake")
        asm_spec = {
            "kind": "assembly",
            "name": "a",
            "components": [
                {"id": "base", "part": str(base_path)},
                {
                    "id": "lid",
                    "part_spec": str(tmp_path / "missing.json"),
                },
            ],
        }
        result = dry_run_assembly(asm_spec)
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_invalid_part_spec_fails(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"name": "x"}), encoding="utf-8")
        base_path = tmp_path / "base.sldprt"
        base_path.write_text("fake")
        asm_spec = {
            "kind": "assembly",
            "name": "a",
            "components": [
                {"id": "base", "part": str(base_path)},
                {"id": "lid", "part_spec": str(bad)},
            ],
        }
        result = dry_run_assembly(asm_spec)
        assert result["ok"] is False
        assert "validation failed" in result["error"]

    def test_override_part_paths_wins(self, tmp_path: Path) -> None:
        spec_path = _write_part_spec(tmp_path / "lid.json")
        built_path = tmp_path / "pre_built.sldprt"
        built_path.write_text("fake")

        asm_spec = {
            "kind": "assembly",
            "name": "a",
            "components": [
                {"id": "base", "part": str(built_path)},
                {"id": "lid", "part_spec": str(spec_path)},
            ],
        }
        result = dry_run_assembly(
            asm_spec,
            part_paths={"lid": str(built_path)},
        )
        assert result["ok"] is True
        # The override resolves via part_paths; no part_spec validation ran.
        assert result["sources"]["lid"] == "part_paths"
        assert result["resolved_parts"]["lid"] == str(built_path)


# ---- commit: builds part_spec when no override -----------------------------


class TestCommitPartSpec:
    def test_builds_and_places(self, tmp_path: Path) -> None:
        spec_path = _write_part_spec(tmp_path / "lid.json")
        base_path = tmp_path / "base.sldprt"
        base_path.write_text("fake")

        asm_spec = {
            "kind": "assembly",
            "name": "a",
            "components": [
                {"id": "base", "part": str(base_path)},
                {"id": "lid", "part_spec": str(spec_path)},
            ],
            "mates": [],
        }

        save_to = tmp_path / "built_lid.SLDPRT"

        def fake_build(part_spec_data, save_as):
            # Materialize the "built" file.
            Path(save_as).write_text("fake")
            return {
                "ok": True,
                "save_as": save_as,
                "save_as_verified": True,
                "features_built": ["SK_Box", "EX_Box"],
                "build_ok": True,
            }

        placed = {"base": MagicMock(), "lid": MagicMock()}
        fake_sw = MagicMock()
        fake_asm_doc = MagicMock()
        fake_sw.NewDocument.return_value = fake_asm_doc
        fake_asm_doc.SaveAs3.return_value = None

        with patch(
            "ai_sw_bridge.assembly.lifecycle._find_assembly_template",
            return_value="fake.ASMDOT",
        ), patch(
            "ai_sw_bridge.assembly.lifecycle.place_components",
            return_value=(placed, None),
        ), patch(
            "ai_sw_bridge.assembly.lifecycle._build_part_spec",
            side_effect=fake_build,
        ) as mock_build, patch(
            "ai_sw_bridge.assembly.lifecycle._temp_part_path",
            return_value=str(save_to),
        ), patch(
            "ai_sw_bridge.com.sw_type_info.wrapper_module",
            return_value=MagicMock(),
        ), patch(
            "ai_sw_bridge.com.earlybind.typed",
            side_effect=lambda obj, iface, module=None: MagicMock(),
        ):
            result = commit_assembly(
                fake_sw, asm_spec, str(tmp_path / "out.sldasm"),
            )

        assert result["ok"] is True
        assert mock_build.call_count == 1
        # The built spec path is what we fed in via the temp_path patch.
        assert "lid" in result["built_part_specs"]
        assert result["built_part_specs"]["lid"]["spec_path"] == str(spec_path)
        assert result["sources"]["lid"] == "part_spec"
        assert result["sources"]["base"] == "part"

    def test_override_skips_build(self, tmp_path: Path) -> None:
        spec_path = _write_part_spec(tmp_path / "lid.json")
        base_path = tmp_path / "base.sldprt"
        base_path.write_text("fake")
        built_path = tmp_path / "pre_built.sldprt"
        built_path.write_text("fake")

        asm_spec = {
            "kind": "assembly",
            "name": "a",
            "components": [
                {"id": "base", "part": str(base_path)},
                {"id": "lid", "part_spec": str(spec_path)},
            ],
            "mates": [],
        }

        placed = {"base": MagicMock(), "lid": MagicMock()}
        fake_sw = MagicMock()
        fake_asm_doc = MagicMock()
        fake_sw.NewDocument.return_value = fake_asm_doc

        with patch(
            "ai_sw_bridge.assembly.lifecycle._find_assembly_template",
            return_value="fake.ASMDOT",
        ), patch(
            "ai_sw_bridge.assembly.lifecycle.place_components",
            return_value=(placed, None),
        ), patch(
            "ai_sw_bridge.assembly.lifecycle._build_part_spec",
            side_effect=AssertionError("override must skip build"),
        ), patch(
            "ai_sw_bridge.com.sw_type_info.wrapper_module",
            return_value=MagicMock(),
        ), patch(
            "ai_sw_bridge.com.earlybind.typed",
            side_effect=lambda obj, iface, module=None: MagicMock(),
        ):
            result = commit_assembly(
                fake_sw,
                asm_spec,
                str(tmp_path / "out.sldasm"),
                part_paths={"lid": str(built_path)},
            )

        assert result["ok"] is True
        assert result["built_part_specs"] == {}
        assert result["sources"]["lid"] == "part_paths"

    def test_build_failure_propagates(self, tmp_path: Path) -> None:
        spec_path = _write_part_spec(tmp_path / "lid.json")
        base_path = tmp_path / "base.sldprt"
        base_path.write_text("fake")

        asm_spec = {
            "kind": "assembly",
            "name": "a",
            "components": [
                {"id": "base", "part": str(base_path)},
                {"id": "lid", "part_spec": str(spec_path)},
            ],
        }

        def fake_build(part_spec_data, save_as):
            return {"ok": False, "error": "build raised"}

        fake_sw = MagicMock()

        with patch(
            "ai_sw_bridge.assembly.lifecycle._build_part_spec",
            side_effect=fake_build,
        ):
            result = commit_assembly(
                fake_sw, asm_spec, str(tmp_path / "out.sldasm"),
            )

        assert result["ok"] is False
        assert "build failed" in result["error"]
