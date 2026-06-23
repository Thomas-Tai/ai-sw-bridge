"""Tests for assembly lifecycle (Wave-9 Slice 6).

End-to-end tests for dry_run_assembly + commit_assembly + the propose→
dry_run→commit pipeline in mutate.py. Uses fakes — no SOLIDWORKS required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_sw_bridge.assembly.lifecycle import dry_run_assembly


def _assembly_spec() -> dict:
    return {
        "kind": "assembly",
        "name": "test_assy",
        "components": [
            {"id": "a", "part": "a.sldprt", "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": "b.sldprt", "transform": {"xyz_mm": [100, 0, 0]}},
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


# ---- dry_run_assembly ------------------------------------------------------


class TestDryRunAssembly:
    def test_accepts_valid_spec(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part"] = str(tmp_path / "a.sldprt")
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "a.sldprt").write_text("fake")
        (tmp_path / "b.sldprt").write_text("fake")

        result = dry_run_assembly(spec)
        assert result["ok"] is True
        assert len(result["resolved_parts"]) == 2
        assert len(result["face_checks"]) == 2

    def test_fails_missing_part_file(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part"] = str(tmp_path / "nonexistent.sldprt")
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "b.sldprt").write_text("fake")

        result = dry_run_assembly(spec)
        assert result["ok"] is False
        assert "file not found" in result["error"]

    def test_fails_no_part_path(self) -> None:
        spec = _assembly_spec()
        del spec["components"][0]["part"]

        result = dry_run_assembly(spec)
        assert result["ok"] is False
        assert "no part path" in result["error"]

    def test_fails_mate_unknown_component(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part"] = str(tmp_path / "a.sldprt")
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "a.sldprt").write_text("fake")
        (tmp_path / "b.sldprt").write_text("fake")
        spec["mates"][0]["a"]["component"] = "ghost"

        result = dry_run_assembly(spec)
        assert result["ok"] is False
        assert "ghost" in result["error"]

    def test_fails_empty_face_ref(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part"] = str(tmp_path / "a.sldprt")
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "a.sldprt").write_text("fake")
        (tmp_path / "b.sldprt").write_text("fake")
        spec["mates"][0]["a"]["face_ref"] = {}

        result = dry_run_assembly(spec)
        assert result["ok"] is False
        assert "empty face_ref" in result["error"]

    def test_resolves_from_part_paths_arg(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part_spec"] = "a.aisw.json"
        del spec["components"][0]["part"]
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "a.sldprt").write_text("fake")
        (tmp_path / "b.sldprt").write_text("fake")

        result = dry_run_assembly(
            spec,
            part_paths={"a": str(tmp_path / "a.sldprt")},
        )
        assert result["ok"] is True

    def test_no_mates_passes(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part"] = str(tmp_path / "a.sldprt")
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "a.sldprt").write_text("fake")
        (tmp_path / "b.sldprt").write_text("fake")
        del spec["mates"]

        result = dry_run_assembly(spec)
        assert result["ok"] is True
        assert result["face_checks"] == []


# ---- mutate.py pipeline (propose → dry_run → commit) -----------------------


class TestAssemblyPipeline:
    def test_propose_then_dry_run(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path / "proposals"))

        part_dir = tmp_path / "parts"
        part_dir.mkdir()
        (part_dir / "a.sldprt").write_text("fake")
        (part_dir / "b.sldprt").write_text("fake")

        spec = _assembly_spec()
        spec["components"][0]["part"] = str(part_dir / "a.sldprt")
        spec["components"][1]["part"] = str(part_dir / "b.sldprt")

        from ai_sw_bridge.mutate import _sw_propose_assembly_impl, _sw_dry_run_assembly_impl

        propose = _sw_propose_assembly_impl(spec)
        assert propose["ok"] is True
        pid = propose["proposal_id"]

        dry = _sw_dry_run_assembly_impl(pid)
        assert dry["ok"] is True
        assert dry["state"] == "dry_run_ok"
        assert len(dry["resolved_parts"]) == 2

    def test_dry_run_rejects_non_assembly(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path / "proposals"))

        from ai_sw_bridge.mutate import _sw_propose_feature_add_impl, _sw_dry_run_assembly_impl

        doc_path = str(tmp_path / "dummy.sldprt")
        Path(doc_path).write_text("fake")
        propose = _sw_propose_feature_add_impl(
            doc_path,
            {"type": "ref_plane", "distance_mm": 10},
            {"plane": "Front Plane"},
        )
        assert propose["ok"] is True

        dry = _sw_dry_run_assembly_impl(propose["proposal_id"])
        assert dry["ok"] is False
        assert "not an assembly" in dry["error"]

    def test_commit_rejects_without_dry_run(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AI_SW_BRIDGE_PROPOSALS", str(tmp_path / "proposals"))

        spec = _assembly_spec()
        from ai_sw_bridge.mutate import _sw_propose_assembly_impl, _sw_commit_assembly_impl

        propose = _sw_propose_assembly_impl(spec)
        assert propose["ok"] is True

        commit = _sw_commit_assembly_impl(
            propose["proposal_id"],
            str(tmp_path / "out.sldasm"),
        )
        assert commit["ok"] is False
        assert "dry_run_ok" in commit["error"]


# ---- Exploded views in dry_run -------------------------------------------


class TestDryRunExplodedViews:
    """Dry-run validation for exploded_views (W32v)."""

    def test_accepts_valid_exploded_view(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part"] = str(tmp_path / "a.sldprt")
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "a.sldprt").write_text("fake")
        (tmp_path / "b.sldprt").write_text("fake")
        spec["exploded_views"] = [
            {
                "name": "Default",
                "steps": [
                    {"components": ["b"], "distance_mm": 50.0, "direction": "front"},
                ],
            }
        ]

        result = dry_run_assembly(spec)
        assert result["ok"] is True
        assert "exploded_checks" in result
        assert len(result["exploded_checks"]) == 1

    def test_fails_unknown_component(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part"] = str(tmp_path / "a.sldprt")
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "a.sldprt").write_text("fake")
        (tmp_path / "b.sldprt").write_text("fake")
        spec["exploded_views"] = [
            {
                "name": "Default",
                "steps": [
                    {"components": ["nonexistent"], "distance_mm": 50.0,
                     "direction": "front"},
                ],
            }
        ]

        result = dry_run_assembly(spec)
        assert result["ok"] is False
        assert "nonexistent" in result["error"]

    def test_accepts_no_exploded_views(self, tmp_path: Path) -> None:
        spec = _assembly_spec()
        spec["components"][0]["part"] = str(tmp_path / "a.sldprt")
        spec["components"][1]["part"] = str(tmp_path / "b.sldprt")
        (tmp_path / "a.sldprt").write_text("fake")
        (tmp_path / "b.sldprt").write_text("fake")

        result = dry_run_assembly(spec)
        assert result["ok"] is True
        assert "exploded_checks" not in result
