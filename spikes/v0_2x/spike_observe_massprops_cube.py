"""W71 witness — prove the EXISTING mass-properties observer on an exact cube.

Reflect-first found that the "Mass Properties observational handler" is ALREADY
shipped as ``observe.sw_get_volume`` (CLI ``observe volume``): it reads Volume,
SurfaceArea, Mass, Density, CenterOfMass off IMassProperty2 and returns a
structured dict. Rather than duplicate it (a W64-class anti-pattern), this spike
fires the witness gate against the SHIPPED handler:

  Build a 10 x 10 x 10 mm cube -> call sw_get_volume() ->
  WITNESS: volume_mm3 == 1000.0 and surface_area_mm2 == 600.0 (exact, no COM
  precision loss), center_of_mass at the cube centroid.

GREEN := |volume_mm3 - 1000| < 1e-6 AND |surface_area_mm2 - 600| < 1e-6.

Usage (seat must be UP)::
    C:/Python314/python.exe spikes/v0_2x/spike_observe_massprops_cube.py
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

RESULTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "spikes"
    / "v0_2x"
    / "_results"
    / "observe_massprops_cube.json"
)

_EXPECT_VOL_MM3 = 1000.0  # 10^3
_EXPECT_AREA_MM2 = 600.0  # 6 faces * 10^2
_TOL = 1e-6


def _build_cube(part_path: str) -> bool:
    """Build a 10 x 10 x 10 mm cube and leave it as the active doc."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W71_Cube",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10.0},
        ],
    }
    res = part_build(spec, no_dim=True, save_as=part_path)
    ok = getattr(res, "ok", None)
    if ok is None and isinstance(res, dict):
        ok = res.get("ok")
    return bool(ok) and os.path.isfile(part_path)


def main() -> int:
    from ai_sw_bridge.observe import sw_get_volume
    from ai_sw_bridge.sw_com import get_sw_app

    result: dict[str, Any] = {
        "spike": "w71_observe_massprops_cube",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # ignore_cleanup_errors: the cube .SLDPRT is held open by SW until we close
    # it; close docs in finally first, but tolerate the OS-level unlink race.
    with tempfile.TemporaryDirectory(
        prefix="w71_cube_", ignore_cleanup_errors=True
    ) as tmp:
        part_path = os.path.join(tmp, "W71_Cube.sldprt")
        if not _build_cube(part_path):
            result["overall"] = "ERROR"
            result["finding"] = "cube build failed"
            _write(result)
            return 1

        try:
            # The shipped handler reads the ACTIVE doc (the cube we just built).
            readout = sw_get_volume()
            result["readout"] = readout

            vol = readout.get("volume_mm3")
            area = readout.get("surface_area_mm2")
            com = readout.get("center_of_mass_mm")

            checks = {
                "handler_ok": bool(readout.get("ok")),
                "volume_exact": vol is not None and abs(vol - _EXPECT_VOL_MM3) < _TOL,
                "area_exact": area is not None and abs(area - _EXPECT_AREA_MM2) < _TOL,
            }
            result["checks"] = checks
            result["deltas"] = {
                "volume_mm3": vol,
                "volume_delta": (vol - _EXPECT_VOL_MM3) if vol is not None else None,
                "surface_area_mm2": area,
                "area_delta": (area - _EXPECT_AREA_MM2) if area is not None else None,
                "center_of_mass_mm": com,
            }
            green = all(checks.values())
            result["overall"] = "PASS" if green else "FAIL"
            result["finding"] = (
                f"vol={vol} mm3 (exp 1000), area={area} mm2 (exp 600), "
                f"mass={readout.get('mass_kg')} kg, density={readout.get('density_kg_m3')}, "
                f"com={com}"
            )
            _write(result)
            return 0 if green else 1
        finally:
            # Release the cube doc so the temp .SLDPRT can be deleted and the
            # seat stays clean (CloseAllDocuments(True), never Close() mid-session).
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
