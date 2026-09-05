from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(spec: dict, tmp_path: Path, *extra: str):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec))
    env = {"PYTHONPATH": str(ROOT / "src")}
    import os

    env = {**os.environ, **env}
    r = subprocess.run(
        [sys.executable, "-m", "ai_sw_bridge.cli.build", str(p), "--lint", *extra],
        capture_output=True,
        text=True,
        env=env,
    )
    return r.returncode, json.loads(r.stdout)


_CLEAN = {
    "schema_version": 1,
    "name": "Clean",
    "features": [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK",
            "plane": "Front",
            "width": 40,
            "height": 30,
        },
        {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10},
    ],
}


def test_clean_spec_exits_zero_with_info_echoes(tmp_path):
    rc, payload = _run(_CLEAN, tmp_path)
    assert rc == 0
    assert payload["ok"] is True
    assert any(f["severity"] == "info" for f in payload["findings"])


def test_empty_air_cut_exits_six(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"] += [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SKA",
            "plane": "Front",
            "width": 5,
            "height": 5,
            "center": {"x": 100, "y": 100},
        },
        {"type": "cut_extrude_blind", "name": "CUTA", "sketch": "SKA", "depth": 5},
    ]
    rc, payload = _run(spec, tmp_path)
    assert rc == 6
    assert payload["ok"] is False
    assert any(
        f["severity"] == "error" and "CUTA" in f["message"] for f in payload["findings"]
    )


def test_warning_only_spec_exits_zero(tmp_path):
    # A WARNING (here an off-face simple_hole) must NOT gate the exit code --
    # only ERROR severity does (the gate special-cases == "error"). Covers the
    # WARNING-only exit-0 path (Task 4); INFO-only is covered above.
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"].append(
        {
            "type": "simple_hole",
            "name": "H_off",
            "of_feature": "EX",
            "face": "+z",
            "center": {"u": 50, "v": 0},  # material X in [-20, 20] -> off-face
            "diameter": 5,
            "depth": 8,
        }
    )
    rc, payload = _run(spec, tmp_path)
    assert rc == 0
    assert payload["ok"] is True
    assert any(f["severity"] == "warning" for f in payload["findings"])
    assert not any(f["severity"] == "error" for f in payload["findings"])


def test_no_preflight_suppresses_geometry_findings(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"] += [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SKA",
            "plane": "Front",
            "width": 5,
            "height": 5,
            "center": {"x": 100, "y": 100},
        },
        {"type": "cut_extrude_blind", "name": "CUTA", "sketch": "SKA", "depth": 5},
    ]
    rc, payload = _run(spec, tmp_path, "--no-preflight")
    assert rc == 0  # empty-air ERROR suppressed


def test_lint_payload_carries_a_coverage_summary(tmp_path):
    rc, payload = _run(_CLEAN, tmp_path)
    assert rc == 0
    assert payload["coverage"] == {
        "total": 1,
        "modeled": 1,
        "skipped": 0,
        "skipped_types": [],
        "complete": True,
    }


def test_lint_payload_coverage_names_unmodeled_types(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"].append(
        {
            "type": "linear_pattern",
            "name": "PAT",
            "seed": "EX",
            "count": 3,
            "direction": {"x": 10.0, "y": 0.0, "z": 0.0},
            "spacing": 5.0,
        }
    )
    rc, payload = _run(spec, tmp_path)
    assert rc == 0  # coverage gaps are not errors without --strict
    assert payload["coverage"]["complete"] is False
    assert payload["coverage"]["skipped_types"] == ["linear_pattern"]


def test_no_preflight_reports_zero_coverage_rather_than_claiming_completeness(
    tmp_path,
):
    rc, payload = _run(_CLEAN, tmp_path, "--no-preflight")
    assert rc == 0
    assert payload["coverage"]["complete"] is False
    assert payload["coverage"]["modeled"] == 0


def test_strict_exits_eight_on_incomplete_coverage(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"].append(
        {
            "type": "linear_pattern",
            "name": "PAT",
            "seed": "EX",
            "count": 3,
            "direction": {"x": 10.0, "y": 0.0, "z": 0.0},
            "spacing": 5.0,
        }
    )
    rc, payload = _run(spec, tmp_path, "--strict")
    assert rc == 8
    assert payload["coverage"]["complete"] is False
    # ok tracks ERROR findings, not coverage -- an incomplete spec is not invalid
    assert payload["ok"] is True


def test_strict_exits_zero_when_coverage_is_complete(tmp_path):
    rc, payload = _run(_CLEAN, tmp_path, "--strict")
    assert rc == 0
    assert payload["coverage"]["complete"] is True


def test_strict_does_not_mask_a_geometric_error(tmp_path):
    # An empty-air cut is exit 6; --strict must not downgrade it to 8.
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"] += [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SKA",
            "plane": "Front",
            "width": 4,
            "height": 4,
            "center": {"x": 500.0, "y": 500.0},
        },
        {"type": "cut_extrude_blind", "name": "CUTA", "sketch": "SKA", "depth": 5},
        {
            "type": "linear_pattern",
            "name": "PAT",
            "seed": "EX",
            "count": 3,
            "direction": {"x": 10.0, "y": 0.0, "z": 0.0},
            "spacing": 5.0,
        },
    ]
    rc, _ = _run(spec, tmp_path, "--strict")
    assert rc == 6


def test_default_run_is_unaffected_by_the_new_flag(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"].append(
        {
            "type": "linear_pattern",
            "name": "PAT",
            "seed": "EX",
            "count": 3,
            "direction": {"x": 10.0, "y": 0.0, "z": 0.0},
            "spacing": 5.0,
        }
    )
    rc, _ = _run(spec, tmp_path)
    assert rc == 0
