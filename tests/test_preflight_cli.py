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
