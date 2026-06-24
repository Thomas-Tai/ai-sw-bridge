"""Tests for assembly edit operations (Wave-15).

Covers apply_edit_op per op, input immutability, fail-closed cases,
manifest→edit→validate round-trip, and the CLI edit subcommand.
"""

from __future__ import annotations

import copy
import json

import pytest

from ai_sw_bridge.assembly.edit import (
    AssemblyEditError,
    apply_edit_op,
)
from ai_sw_bridge.assembly.validator import validate_assembly


def _base_spec() -> dict:
    return {
        "kind": "assembly",
        "name": "test_assy",
        "components": [
            {"id": "a", "part": "a.sldprt", "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": "b.sldprt", "transform": {"xyz_mm": [10, 0, 0]}},
        ],
        "mates": [
            {
                "type": "coincident",
                "alignment": "aligned",
                "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
                "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
            },
        ],
    }


# ---- add_component ----


class TestAddComponent:
    def test_adds_component(self) -> None:
        spec = _base_spec()
        op = {
            "op": "add_component",
            "component": {
                "id": "c",
                "part": "c.sldprt",
                "transform": {"xyz_mm": [20, 0, 0]},
            },
        }
        result = apply_edit_op(spec, op)
        assert len(result["components"]) == 3
        assert result["components"][2]["id"] == "c"

    def test_input_not_mutated(self) -> None:
        spec = _base_spec()
        original = copy.deepcopy(spec)
        apply_edit_op(
            spec,
            {
                "op": "add_component",
                "component": {"id": "c", "part": "c.sldprt"},
            },
        )
        assert spec == original

    def test_rejects_duplicate_id(self) -> None:
        spec = _base_spec()
        with pytest.raises(AssemblyEditError, match="already exists"):
            apply_edit_op(
                spec,
                {
                    "op": "add_component",
                    "component": {"id": "a", "part": "a2.sldprt"},
                },
            )

    def test_rejects_missing_component(self) -> None:
        with pytest.raises(AssemblyEditError, match="component"):
            apply_edit_op(_base_spec(), {"op": "add_component"})

    def test_rejects_empty_id(self) -> None:
        with pytest.raises(AssemblyEditError, match="id"):
            apply_edit_op(
                _base_spec(),
                {
                    "op": "add_component",
                    "component": {"id": "", "part": "x.sldprt"},
                },
            )


# ---- remove_component ----


class TestRemoveComponent:
    def test_removes_unreferenced_component(self) -> None:
        spec = _base_spec()
        spec["components"].append(
            {"id": "c", "part": "c.sldprt", "transform": {"xyz_mm": [20, 0, 0]}}
        )
        result = apply_edit_op(spec, {"op": "remove_component", "id": "c"})
        assert len(result["components"]) == 2
        assert all(c["id"] != "c" for c in result["components"])

    def test_fail_closed_when_mate_references(self) -> None:
        spec = _base_spec()
        with pytest.raises(AssemblyEditError, match="still referenced"):
            apply_edit_op(spec, {"op": "remove_component", "id": "a"})

    def test_error_lists_blocking_mates(self) -> None:
        spec = _base_spec()
        with pytest.raises(AssemblyEditError, match=r"mate\[0\]"):
            apply_edit_op(spec, {"op": "remove_component", "id": "a"})

    def test_fail_closed_width_mate_references(self) -> None:
        spec = _base_spec()
        spec["mates"].append(
            {
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
        )
        with pytest.raises(AssemblyEditError, match="width_faces"):
            apply_edit_op(spec, {"op": "remove_component", "id": "a"})

    def test_rejects_nonexistent_id(self) -> None:
        with pytest.raises(AssemblyEditError, match="not found"):
            apply_edit_op(
                _base_spec(),
                {
                    "op": "remove_component",
                    "id": "ghost",
                },
            )

    def test_rejects_missing_id(self) -> None:
        with pytest.raises(AssemblyEditError, match="id"):
            apply_edit_op(_base_spec(), {"op": "remove_component"})


# ---- add_mate ----


class TestAddMate:
    def test_adds_mate(self) -> None:
        spec = _base_spec()
        mate = {
            "type": "parallel",
            "a": {"component": "a", "face_ref": {"normal": [0, 1, 0]}},
            "b": {"component": "b", "face_ref": {"normal": [0, 1, 0]}},
        }
        result = apply_edit_op(spec, {"op": "add_mate", "mate": mate})
        assert len(result["mates"]) == 2

    def test_adds_to_empty_mates(self) -> None:
        spec = _base_spec()
        del spec["mates"]
        mate = {
            "type": "coincident",
            "alignment": "aligned",
            "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
            "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
        }
        result = apply_edit_op(spec, {"op": "add_mate", "mate": mate})
        assert len(result["mates"]) == 1

    def test_input_not_mutated(self) -> None:
        spec = _base_spec()
        original = copy.deepcopy(spec)
        apply_edit_op(
            spec,
            {
                "op": "add_mate",
                "mate": {
                    "type": "parallel",
                    "a": {"component": "a", "face_ref": {"normal": [0, 1, 0]}},
                    "b": {"component": "b", "face_ref": {"normal": [0, 1, 0]}},
                },
            },
        )
        assert spec == original

    def test_rejects_missing_mate(self) -> None:
        with pytest.raises(AssemblyEditError, match="mate"):
            apply_edit_op(_base_spec(), {"op": "add_mate"})

    def test_rejects_mate_without_type(self) -> None:
        with pytest.raises(AssemblyEditError, match="type"):
            apply_edit_op(
                _base_spec(),
                {
                    "op": "add_mate",
                    "mate": {"a": {}, "b": {}},
                },
            )


# ---- remove_mate ----


class TestRemoveMate:
    def test_removes_mate(self) -> None:
        spec = _base_spec()
        result = apply_edit_op(spec, {"op": "remove_mate", "index": 0})
        assert len(result["mates"]) == 0

    def test_input_not_mutated(self) -> None:
        spec = _base_spec()
        original = copy.deepcopy(spec)
        apply_edit_op(spec, {"op": "remove_mate", "index": 0})
        assert spec == original

    def test_rejects_out_of_range(self) -> None:
        with pytest.raises(AssemblyEditError, match="out of range"):
            apply_edit_op(_base_spec(), {"op": "remove_mate", "index": 5})

    def test_rejects_negative_index(self) -> None:
        with pytest.raises(AssemblyEditError, match="out of range"):
            apply_edit_op(_base_spec(), {"op": "remove_mate", "index": -1})

    def test_rejects_non_integer_index(self) -> None:
        with pytest.raises(AssemblyEditError, match="integer"):
            apply_edit_op(_base_spec(), {"op": "remove_mate", "index": "0"})


# ---- Fail-closed ----


class TestFailClosed:
    def test_unknown_op(self) -> None:
        with pytest.raises(AssemblyEditError, match="unknown op"):
            apply_edit_op(_base_spec(), {"op": "rename_component"})

    def test_missing_op(self) -> None:
        with pytest.raises(AssemblyEditError, match="unknown op"):
            apply_edit_op(_base_spec(), {})

    def test_non_dict_op(self) -> None:
        with pytest.raises(AssemblyEditError, match="must be a dict"):
            apply_edit_op(_base_spec(), "add_mate")  # type: ignore[arg-type]


# ---- Manifest → edit → validate round-trip ----


class TestManifestEditValidate:
    """Prove that an edited spec still passes validate_assembly."""

    def test_remove_mate_then_remove_component(self) -> None:
        spec = _base_spec()
        # Step 1: remove the mate referencing 'b'
        edited = apply_edit_op(spec, {"op": "remove_mate", "index": 0})
        assert len(edited["mates"]) == 0
        # Step 2: now remove 'b' (no blocking mates)
        edited = apply_edit_op(
            edited,
            {
                "op": "remove_component",
                "id": "b",
            },
        )
        assert len(edited["components"]) == 1
        # Edited spec validates
        validate_assembly(edited)

    def test_add_component_then_add_mate(self) -> None:
        spec = _base_spec()
        # Add component c
        edited = apply_edit_op(
            spec,
            {
                "op": "add_component",
                "component": {
                    "id": "c",
                    "part": "c.sldprt",
                    "transform": {"xyz_mm": [20, 0, 0]},
                },
            },
        )
        # Add a mate between a and c
        edited = apply_edit_op(
            edited,
            {
                "op": "add_mate",
                "mate": {
                    "type": "parallel",
                    "a": {"component": "a", "face_ref": {"normal": [0, 1, 0]}},
                    "b": {"component": "c", "face_ref": {"normal": [0, 1, 0]}},
                },
            },
        )
        assert len(edited["components"]) == 3
        assert len(edited["mates"]) == 2
        validate_assembly(edited)


# ---- sw_edit_assembly pipeline ----


class TestSwEditAssembly:
    def test_edit_round_trip(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.assembly.storage import AssemblyManifest
        from ai_sw_bridge.mutate import _sw_edit_assembly_impl

        spec = _base_spec()
        manifest = AssemblyManifest(spec=spec, assembly_path="test.sldasm")
        manifest.components = []  # runtime overlay (empty for offline test)
        mpath = tmp_path / "test.SLDASM.manifest.json"
        manifest.save(mpath)

        result = _sw_edit_assembly_impl(
            str(mpath),
            {
                "op": "add_mate",
                "mate": {
                    "type": "parallel",
                    "a": {"component": "a", "face_ref": {"normal": [0, 1, 0]}},
                    "b": {"component": "b", "face_ref": {"normal": [0, 1, 0]}},
                },
            },
        )
        assert result["ok"] is True
        assert result["proposal_id"] is not None
        assert result["edit_applied"] is True

    def test_edit_rejects_bad_op(self, tmp_path) -> None:
        from ai_sw_bridge.assembly.storage import AssemblyManifest
        from ai_sw_bridge.mutate import _sw_edit_assembly_impl

        spec = _base_spec()
        manifest = AssemblyManifest(spec=spec, assembly_path="test.sldasm")
        manifest.components = []
        mpath = tmp_path / "test.SLDASM.manifest.json"
        manifest.save(mpath)

        result = _sw_edit_assembly_impl(str(mpath), {"op": "bogus"})
        assert result["ok"] is False
        assert "edit op rejected" in result["error"]

    def test_edit_missing_manifest(self, tmp_path) -> None:
        from ai_sw_bridge.mutate import _sw_edit_assembly_impl

        result = _sw_edit_assembly_impl(
            str(tmp_path / "nonexistent.manifest.json"),
            {"op": "add_mate", "mate": {"type": "parallel"}},
        )
        assert result["ok"] is False
        assert "manifest load failed" in result["error"]


# ---- CLI edit subcommand ----


class TestCliEdit:
    def test_cli_smoke(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.assembly.storage import AssemblyManifest

        spec = _base_spec()
        manifest = AssemblyManifest(spec=spec, assembly_path="test.sldasm")
        manifest.components = []
        mpath = tmp_path / "test.SLDASM.manifest.json"
        manifest.save(mpath)

        op_json = json.dumps(
            {
                "op": "add_mate",
                "mate": {
                    "type": "parallel",
                    "a": {"component": "a", "face_ref": {"normal": [0, 1, 0]}},
                    "b": {"component": "b", "face_ref": {"normal": [0, 1, 0]}},
                },
            }
        )

        from ai_sw_bridge.cli.assembly import _load_op, _run_edit
        import argparse

        op = _load_op(op_json)
        assert op is not None

        args = argparse.Namespace(manifest=str(mpath), op=op_json)
        result = _run_edit(args)
        assert result["ok"] is True

    def test_cli_at_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path))
        from ai_sw_bridge.assembly.storage import AssemblyManifest
        from ai_sw_bridge.cli.assembly import _run_edit
        import argparse

        spec = _base_spec()
        manifest = AssemblyManifest(spec=spec, assembly_path="test.sldasm")
        manifest.components = []
        mpath = tmp_path / "test.SLDASM.manifest.json"
        manifest.save(mpath)

        op_file = tmp_path / "op.json"
        op_file.write_text(
            json.dumps(
                {
                    "op": "remove_mate",
                    "index": 0,
                }
            )
        )

        args = argparse.Namespace(manifest=str(mpath), op=f"@{op_file}")
        result = _run_edit(args)
        assert result["ok"] is True
