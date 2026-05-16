"""
Spike J - try AddSpecificDimension instead of AddDimension2 to bypass the
Modify popup blocker.

Reddit thread (2022) reports that swInputDimValOnCreate=False does
suppress the popup for AddSpecificDimension. Our Spike I proved the
toggle DOESN'T work for AddDimension2 on this SW 2024 SP1 build. So
this spike tests whether AddSpecificDimension behaves better.

Test cases:
  - Linear horizontal dim on a single line (rect edge)
  - Diameter dim on a circle
  - Linear vertical dim

Each: with toggle 8 = False (we'll set it just in case), measure
elapsed time. If <2s -> popup suppressed -> we use this API.

AddSpecificDimension signature (IModelDocExtension):
  AddSpecificDimension(X, Y, Z, DimType, Error) -> IDisplayDimension

swDimensionType_e (best guess from API docs):
  1 = swLinearDimension
  2 = swAngularDimension
  3 = swDiameterDimension (?)
  4 = swRadialDimension (?)

We try multiple values to discover the right enum on this build.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402

SW_INPUT_DIM_VAL_ON_CREATE = 8


def _try_dim(doc, ext, sel_coord, leader, dim_type: int, label: str) -> dict:
    """Try AddSpecificDimension at sel_coord with the given DimType. Return
    timing + result."""
    sm = doc.SketchManager
    # Each call assumes a fresh circle on Front Plane (centered at origin,
    # 10mm dia). Create + select inline.
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"label": label, "status": "FAIL", "error": "select Front Plane"}
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)

    doc.ClearSelection2(True)
    if not doc.SelectByID("", "SKETCHSEGMENT", sel_coord[0], sel_coord[1], sel_coord[2]):
        sm.InsertSketch(True)
        return {"label": label, "status": "FAIL", "error": "select circle"}

    err = 0  # OUT param; pywin32 late-binding may not return it correctly
    t0 = time.time()
    try:
        dim = ext.AddSpecificDimension(leader[0], leader[1], leader[2], dim_type, err)
    except Exception as e:
        sm.InsertSketch(True)
        return {"label": label, "status": "ERROR", "error": repr(e),
                "elapsed_s": round(time.time() - t0, 3)}
    elapsed = time.time() - t0

    sm.InsertSketch(True)  # close the sketch

    return {
        "label": label,
        "status": "PASS" if dim is not None else "FAIL_NONE",
        "elapsed_s": round(elapsed, 3),
        "dim_type_tried": dim_type,
        "blocked": elapsed > 3.0,
    }


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"status": "FAIL", "error": "no active doc"}))
        return 1
    if doc.GetFeatureCount > 17:
        print(json.dumps({"status": "FAIL",
                          "error": "doc not blank; File>New>Part first"}))
        return 1

    # Suppress popup (per Reddit, should work for AddSpecificDimension)
    prev = sw.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, False)

    ext = doc.Extension
    results = []
    try:
        # Try a few DimType values. Circle diameter is the simplest case.
        # Leader at (5+5, 5+5, 0) mm puts it outside the circle.
        sel = (0.005, 0.0, 0.0)         # point on perimeter
        leader = (0.010, 0.005, 0.0)
        for dt in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            r = _try_dim(doc, ext, sel, leader, dt, f"DimType_{dt}")
            results.append(r)
    finally:
        sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, prev)

    # Find any that succeeded fast
    fast = [r for r in results if r["status"] == "PASS" and not r.get("blocked")]
    slow = [r for r in results if r["status"] == "PASS" and r.get("blocked")]

    print(json.dumps({
        "status": "DONE",
        "results": results,
        "fast_PASS_count": len(fast),
        "fast_dim_types": [r["dim_type_tried"] for r in fast],
        "slow_PASS_count": len(slow),
        "verdict": (
            "AddSpecificDimension respects toggle 8 -> use it!"
            if fast else
            "AddSpecificDimension also blocks; toggle 8 still ineffective"
        ),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
