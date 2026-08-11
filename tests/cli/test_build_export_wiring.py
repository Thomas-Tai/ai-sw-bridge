"""Unit tests for ai-sw-build's schema-v2 `export:` block wiring.

The low-level builder builds features only; ``main()`` is responsible for
running the ``export:`` block against the just-built part and folding the
per-format results into the JSON envelope. These tests pin that wiring WITHOUT
a live seat: the builder, seat gate, active-doc readers, and ``export_all`` are
all patched, so no SOLIDWORKS is attached or launched.

Crux: a spec with an ``export:`` block gets an ``export_results`` array and an
overall ok/exit that reflects export success; a spec WITHOUT one is completely
unaffected (no ``export_results`` key, no active-doc read).
"""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

from ai_sw_bridge.cli.build import main
from ai_sw_bridge.export.dispatch import ExportResult

_EXPORT_SPEC = {
    "schema_version": 2,
    "name": "DemoExportBlock",
    "features": [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK",
            "plane": "Front",
            "width": 30.0,
            "height": 20.0,
            "center": {"x": 0.0, "y": 0.0},
        },
        {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 8.0},
    ],
    "export": [
        {"format": "step214", "output_dir": "demo_out"},
        {"format": "stl", "output_dir": "demo_out", "binary": True},
        {"format": "3mf", "output_dir": "demo_out"},
    ],
}

_V1_SPEC = {
    "schema_version": 1,
    "name": "PlainPart",
    "features": [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK",
            "plane": "Front",
            "width": 30.0,
            "height": 20.0,
            "center": {"x": 0.0, "y": 0.0},
        },
        {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 8.0},
    ],
}


class _FakeBuildResult:
    """Stand-in for BuildResult: a successful, unsaved build."""

    def __init__(self, ok: bool = True, save_as: str | None = None) -> None:
        self.ok = ok
        self.save_as = save_as

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "features_built": ["SK", "EX"], "save_as": self.save_as}


class _MockDoc:
    def GetType(self) -> int:  # Part
        return 1


def _write_spec(tmp_path, spec) -> str:
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return str(p)


def test_export_block_runs_and_folds_results(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AI_SW_BRIDGE_FLAG_SCHEMA_V2", "1")
    spec_path = _write_spec(tmp_path, _EXPORT_SPEC)

    def fake_export_all(doc, requests, part_name):
        assert part_name == "DemoExportBlock"
        return [
            ExportResult(format=r.format, path=f"/out/{part_name}", ok=True)
            for r in requests
        ]

    monkeypatch.setattr(sys, "argv", ["ai-sw-build", spec_path, "--no-dim", "--yes"])
    with (
        patch("ai_sw_bridge.cli.build.build", return_value=_FakeBuildResult()),
        patch("ai_sw_bridge.cli.build._seat_gate", return_value=None),
        patch("ai_sw_bridge.sw_com.get_sw_app", return_value=object()),
        patch("ai_sw_bridge.sw_com.get_active_doc", return_value=_MockDoc()),
        patch("ai_sw_bridge.export.export_all", side_effect=fake_export_all),
    ):
        rc = main()

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ok"] is True
    assert "export_results" in out
    assert [r["format"] for r in out["export_results"]] == ["step214", "stl", "3mf"]
    assert all(r["ok"] for r in out["export_results"])


def test_export_failure_sets_ok_false_and_exit_4(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AI_SW_BRIDGE_FLAG_SCHEMA_V2", "1")
    spec_path = _write_spec(tmp_path, _EXPORT_SPEC)

    def fake_export_all(doc, requests, part_name):
        # First format fails, the rest succeed.
        return [
            ExportResult(
                format=r.format,
                path=f"/out/{part_name}",
                ok=(i != 0),
                error=None if i != 0 else "SaveAs3 returned swFileSaveError=1",
            )
            for i, r in enumerate(requests)
        ]

    monkeypatch.setattr(sys, "argv", ["ai-sw-build", spec_path, "--no-dim", "--yes"])
    with (
        patch("ai_sw_bridge.cli.build.build", return_value=_FakeBuildResult()),
        patch("ai_sw_bridge.cli.build._seat_gate", return_value=None),
        patch("ai_sw_bridge.sw_com.get_sw_app", return_value=object()),
        patch("ai_sw_bridge.sw_com.get_active_doc", return_value=_MockDoc()),
        patch("ai_sw_bridge.export.export_all", side_effect=fake_export_all),
    ):
        rc = main()

    out = json.loads(capsys.readouterr().out)
    assert rc == 4
    assert out["ok"] is False
    assert out["error"] == "export_failed"
    assert out["export_results"][0]["ok"] is False


def test_no_active_doc_after_build_is_export_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AI_SW_BRIDGE_FLAG_SCHEMA_V2", "1")
    spec_path = _write_spec(tmp_path, _EXPORT_SPEC)

    monkeypatch.setattr(sys, "argv", ["ai-sw-build", spec_path, "--no-dim", "--yes"])
    with (
        patch("ai_sw_bridge.cli.build.build", return_value=_FakeBuildResult()),
        patch("ai_sw_bridge.cli.build._seat_gate", return_value=None),
        patch("ai_sw_bridge.sw_com.get_sw_app", return_value=object()),
        patch("ai_sw_bridge.sw_com.get_active_doc", return_value=None),
    ):
        rc = main()

    out = json.loads(capsys.readouterr().out)
    assert rc == 4
    assert out["ok"] is False
    assert "no active document" in out["export_results"][0]["error"]


def test_spec_without_export_block_is_unaffected(tmp_path, monkeypatch, capsys):
    # A v1 spec (no export:) must not grow an export_results key and must never
    # touch the active doc. get_active_doc is intentionally NOT patched — if the
    # wiring wrongly ran, it would try to attach to SW and the test would error.
    spec_path = _write_spec(tmp_path, _V1_SPEC)

    monkeypatch.setattr(sys, "argv", ["ai-sw-build", spec_path, "--no-dim", "--yes"])
    with (
        patch("ai_sw_bridge.cli.build.build", return_value=_FakeBuildResult()),
        patch("ai_sw_bridge.cli.build._seat_gate", return_value=None),
    ):
        rc = main()

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ok"] is True
    assert "export_results" not in out
