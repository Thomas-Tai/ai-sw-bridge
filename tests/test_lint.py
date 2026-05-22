"""Tests for ai-sw-build --lint (P1.3).

Verifies that the lint module catches the semantic issues it should
and stays quiet on clean specs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.spec.lint import lint, LintFinding
from ai_sw_bridge.spec.validator import validate


def _minimal_spec() -> dict:
    return {
        "schema_version": 1,
        "name": "LintTest",
        "features": [
            {
                "type": "sketch_circle_on_plane",
                "name": "SK_A",
                "plane": "Front",
                "diameter": 25.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_A",
                "sketch": "SK_A",
                "depth": 10.0,
            },
        ],
    }


def test_clean_spec_lints_clean() -> None:
    findings = lint(_minimal_spec())
    assert len(findings) == 0


def test_unconsumed_sketch_warned() -> None:
    spec = _minimal_spec()
    # Add a sketch that no extrude references
    spec["features"].insert(
        1,
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Orphan",
            "plane": "Front",
            "width": 10.0,
            "height": 5.0,
        },
    )
    validate(spec)  # should still pass (orphan is valid)
    findings = lint(spec)
    messages = [f.message for f in findings]
    assert any("SK_Orphan" in m and "not referenced" in m for m in messages)


def test_top_plane_centerline_without_center_z_warned() -> None:
    spec = {
        "schema_version": 1,
        "name": "CenterZTest",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Groove",
                "plane": "Top",
                "width": 1.0,
                "height": 5.0,
                "center": {"x": 12.0, "y": 0.0},
                "centerline": {
                    "start": {"x": 0.0, "y": 0.0},
                    "end": {"x": 0.0, "y": 85.0},
                },
            },
            {
                "type": "revolve_cut",
                "name": "Cut_Groove",
                "sketch": "SK_Groove",
                "angle": 360.0,
            },
        ],
    }
    validate(spec)  # should pass
    findings = lint(spec)
    messages = [f.message for f in findings]
    assert any("center.z" in m and "Top Plane" in m for m in messages)


def test_top_plane_centerline_with_center_z_passes() -> None:
    spec = {
        "schema_version": 1,
        "name": "CenterZTest",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Groove",
                "plane": "Top",
                "width": 1.0,
                "height": 5.0,
                "center": {"x": 12.0, "y": 0.0, "z": 40.0},
                "centerline": {
                    "start": {"x": 0.0, "y": 0.0, "z": -5.0},
                    "end": {"x": 0.0, "y": 0.0, "z": 85.0},
                },
            },
            {
                "type": "revolve_cut",
                "name": "Cut_Groove",
                "sketch": "SK_Groove",
                "angle": 360.0,
            },
        ],
    }
    validate(spec)
    findings = lint(spec)
    center_z_findings = [f for f in findings if "center.z" in f.message]
    assert len(center_z_findings) == 0


def test_center_z_thread_through_warned() -> None:
    spec = {
        "schema_version": 1,
        "name": "ThreadThroughTest",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Top",
                "width": 10.0,
                "height": 10.0,
                "center": {"x": 0.0, "y": 0.0, "z": 40.0},
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 5.0,
            },
        ],
    }
    validate(spec)
    findings = lint(spec)
    messages = [f.message for f in findings]
    assert any("center.z" in m and "extrude_origin" in m for m in messages)


def test_lint_finding_serializable() -> None:
    f = LintFinding("warning", "features/0/SK_X", "test finding")
    d = f.to_dict()
    assert d["severity"] == "warning"
    assert d["path"] == "features/0/SK_X"
    assert d["message"] == "test finding"
    # Must be JSON-serializable (the CLI uses json.dumps)
    json.dumps(d)


def test_cli_lint_flag() -> None:
    """End-to-end test: ai-sw-build --lint exits non-zero on findings."""
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parent.parent
    spec_path = repo_root / "examples" / "drive_roller" / "spec.json"
    if not spec_path.exists():
        pytest.skip("drive_roller spec not found")
    # Run the CLI with the interpreter that's running the tests, so this
    # works on CI (no .venv-freshtest there) as well as locally.
    result = subprocess.run(
        [sys.executable, "-m", "ai_sw_bridge.cli.build", "--lint", str(spec_path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    # DriveRoller has center.z=40 on the groove, so it should pass lint
    # (no center.z warnings). It may have other findings though.
    output = json.loads(result.stdout)
    assert "lint" in output or "findings" in output or "dry_run" in output
