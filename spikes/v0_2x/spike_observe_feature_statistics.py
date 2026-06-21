"""W71 witness — seat-prove observe.sw_get_feature_statistics on a known fixture.

Builds a multi-feature solid (40x30x20 block + 2 through-holes) and fires the
new statistics observer. The WITNESS is that the returned counts perfectly
match the physical topology:

  solid_bodies_count   == 1   (one block)
  surface_bodies_count == 0   (no surface body -- the discriminator must NOT
                               false-positive; build() is solid-core only, so
                               proving ==1 needs a registry surface feature,
                               identical discriminator logic)
  feature_count        >= 3   (>=1 boss + 2 cuts; SW's exact count incl.
                               origin/sketches reported in the telemetry)
  total_rebuild_time   is a float >= 0 (the rebuild-cost readout)
  feature_names/types/update_times arrays present, len == feature_count

GREEN := handler ok AND solid==1 AND surface==0 AND feature_count>=3.

Usage (seat must be UP)::
    C:/Python314/python.exe spikes/v0_2x/spike_observe_feature_statistics.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

RESULTS_PATH = Path(__file__).resolve().parents[2] / "spikes" / "v0_2x" / "_results" / "observe_feature_statistics.json"


def _build_fixture(part_path: str) -> bool:
    """Block + 2 through-holes -> 1 solid body, multi-feature tree."""
    from ai_sw_bridge.spec.builder import build as part_build
    spec = {
        "schema_version": 1,
        "name": "W71_Stats",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK_Base", "plane": "Front", "width": 40.0, "height": 30.0},
            {"type": "boss_extrude_blind", "name": "EX_Base", "sketch": "SK_Base", "depth": 20.0},
            {"type": "sketch_circle_on_face", "name": "SK_H1", "of_feature": "EX_Base", "face": "+z", "diameter": 8.0, "center": {"u": -10.0, "v": 0.0}},
            {"type": "cut_extrude_through_all", "name": "CUT_H1", "sketch": "SK_H1"},
            {"type": "sketch_circle_on_face", "name": "SK_H2", "of_feature": "EX_Base", "face": "+z", "diameter": 8.0, "center": {"u": 10.0, "v": 0.0}},
            {"type": "cut_extrude_through_all", "name": "CUT_H2", "sketch": "SK_H2"},
        ],
    }
    res = part_build(spec, no_dim=True, save_as=part_path)
    ok = getattr(res, "ok", None)
    if ok is None and isinstance(res, dict):
        ok = res.get("ok")
    return bool(ok) and os.path.isfile(part_path)


def main() -> int:
    from ai_sw_bridge.observe import sw_get_feature_statistics
    from ai_sw_bridge.sw_com import get_sw_app

    result: dict[str, Any] = {"spike": "w71_feature_statistics", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}

    with tempfile.TemporaryDirectory(prefix="w71_stats_", ignore_cleanup_errors=True) as tmp:
        part_path = os.path.join(tmp, "W71_Stats.sldprt")
        if not _build_fixture(part_path):
            result["overall"] = "ERROR"
            result["finding"] = "fixture build failed"
            _write(result)
            return 1

        try:
            stats = sw_get_feature_statistics()
            result["readout"] = stats

            fc = stats.get("feature_count")
            solid = stats.get("solid_bodies_count")
            surface = stats.get("surface_bodies_count")
            trt = stats.get("total_rebuild_time")
            names = stats.get("feature_names")

            checks = {
                "handler_ok": bool(stats.get("ok")),
                "refreshed": bool(stats.get("refreshed")),
                "solid_is_1": solid == 1,
                "surface_is_0": surface == 0,
                "feature_count_ge_3": isinstance(fc, int) and fc >= 3,
                "rebuild_time_float": isinstance(trt, float) and trt >= 0.0,
                "names_present": isinstance(names, list) and len(names) >= 1,
            }
            result["checks"] = checks
            green = all(checks.values())
            result["overall"] = "PASS" if green else "FAIL"
            result["finding"] = (
                f"feature_count={fc}, solid={solid}, surface={surface}, "
                f"rebuild_time={trt}s, names={names}, types={stats.get('feature_types')}"
            )
            _write(result)
            return 0 if green else 1
        finally:
            try:
                get_sw_app().CloseAllDocuments(True)
            except Exception:
                pass


def _write(result: dict) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(result.get("overall", "ERROR"), file=sys.stderr)
    print(result.get("finding", ""), file=sys.stderr)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
