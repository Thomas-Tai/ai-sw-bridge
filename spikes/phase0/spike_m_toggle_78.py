"""
Spike M - Probe swSketchEnableOnScreenNumericInput (toggle ID 78).

User suggestion (2026-05-17): Spike I tested toggle ID 8
(swInputDimValOnCreate) and it had no effect on the Modify Dimension popup.
Toggle 78 is a different preference -- specifically the "on-screen numeric
input" that IS the popup. It was never tried.

This spike:
1. Reads the current value of toggle 78
2. Sets it to False
3. Reads it back to confirm
4. Creates a sketch + circle + AddDimension2 and measures elapsed time
   - If the toggle works, AddDimension2 returns in well under 1 second
     (no user interaction needed). Prior measurement: 12+ seconds blocking.
5. Restores the original toggle value

PASS: AddDimension2 returns in < 2.0 seconds AND dim exists.
FAIL: still blocks > 5 seconds (toggle had no effect) OR dim creation broken.

Run from a SOLIDWORKS session with NO active doc (we'll open a fresh part).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402


SW_SKETCH_ENABLE_ON_SCREEN_NUMERIC_INPUT = 78  # the candidate toggle
SW_INPUT_DIM_VAL_ON_CREATE = 8                  # previously-tried toggle (Spike I)


def run_com() -> dict:
    sw = get_sw_app()

    # Read both toggles before any change
    val78_before = sw.GetUserPreferenceToggle(SW_SKETCH_ENABLE_ON_SCREEN_NUMERIC_INPUT)
    val8_before = sw.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE)

    # Set toggle 78 to False (suppress the on-screen numeric input popup)
    sw.SetUserPreferenceToggle(SW_SKETCH_ENABLE_ON_SCREEN_NUMERIC_INPUT, False)
    val78_after_set = sw.GetUserPreferenceToggle(SW_SKETCH_ENABLE_ON_SCREEN_NUMERIC_INPUT)

    # Also set toggle 8 to False (belt + suspenders -- we don't know which one matters)
    sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, False)

    # Open a fresh part
    template = sw.GetUserPreferenceStringValue(8)
    if not template:
        return {"status": "FAIL", "error": "no default Part template"}
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"status": "FAIL", "error": "NewDocument returned None"}

    # Create one sketch, one circle, one dim. Measure the AddDimension2
    # elapsed time -- the only thing we care about here.
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"status": "FAIL", "error": "could not select Front Plane"}
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)  # 10mm diameter placeholder

    doc.ClearSelection2(True)
    if not doc.SelectByID("", "SKETCHSEGMENT", 0.005, 0.0, 0.0):
        return {"status": "FAIL", "error": "could not select circle for dim"}

    t_dim_start = time.perf_counter()
    dim = doc.AddDimension2(0.010, 0.005, 0.0)
    t_dim_end = time.perf_counter()
    elapsed_dim_s = round(t_dim_end - t_dim_start, 3)

    sm.InsertSketch(True)  # close

    # Restore original toggle values
    sw.SetUserPreferenceToggle(SW_SKETCH_ENABLE_ON_SCREEN_NUMERIC_INPUT, val78_before)
    sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, val8_before)

    # PASS criterion: dim returned non-None AND elapsed < 2.0s (no user tick needed)
    # Previously recorded baseline: ~12s blocking on manual tick.
    status = "PASS" if (dim is not None and elapsed_dim_s < 2.0) else "FAIL"

    return {
        "status": status,
        "toggle_78_before": val78_before,
        "toggle_78_after_set_false": val78_after_set,
        "toggle_8_before": val8_before,
        "add_dim2_elapsed_s": elapsed_dim_s,
        "add_dim2_returned_none": dim is None,
        "interpretation": (
            "Toggle 78 SUPPRESSED the popup -- ship it" if status == "PASS"
            else "Toggle 78 did NOT suppress the popup OR dim creation broke"
        ),
        "baseline_blocking_time_s_per_dim": "~12s (Spike I)",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com"], default="com")
    args = parser.parse_args()
    result = run_com()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
