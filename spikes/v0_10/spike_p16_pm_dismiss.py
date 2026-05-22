"""
Spike P1.6 - PM-pane dismiss after AddDimension2 (time-boxed 1 day).

Context: After AddDimension2, SW opens a Dimension PropertyManager pane
on the left side. The floating Modify popup is suppressed via
swInputDimValOnCreate=False, but the side pane is NOT. Previous
investigation (Spike F, 2026-05-16) tried:

  S1: doc.ClosePropertyManager()                -- did not close pane
  S2: doc.Extension.CloseAndDestroyPropertyManagers() -- did not close pane
  S3: doc.Extension.RunCommand(1, "")           -- regressed cylinder
  S4: no dismiss (control)                      -- pane stays open

This spike tries UNTESTED approaches from the enhancement plan:

  T1: doc.Extension.RunCommand(2421, "")        -- 2421 = swCommands_PmOK
                                                   per forum posts
  T2: doc.ClosePropertyManager() AFTER ForceRebuild3  -- timing variant:
                                                   close PM after rebuild
  T3: sw.SetUserPreferenceToggle(78, False)      -- swSketchEnableOnScreenNumericInput
                                                   applied at APP level
                                                   before ANY sketch opens
  T4: IModelDoc2::SetAddDimension2Return(0)      -- undocumented; may not exist
  T5: doc.Extension.RunCommand(2421, "") + sleep(0.5)  -- with settle time

Preconditions: a fresh blank Part is open in SW (caller does File > New).

Usage:
    python spikes/v0_10/spike_p16_pm_dismiss.py

Output: JSON {strategy: {status, method_result, elapsed_s, geometry_ok}}.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc

SW_INPUT_DIM_VAL_ON_CREATE = 8
SW_SKETCH_ENABLE_ON_SCREEN_NUMERIC_INPUT = 78


def _open_sketch_and_add_dim(doc, sm, x_offset_m: float):
    """Create a 10mm circle on Front Plane and add a diameter dim.

    Returns the IDisplayDimension. Leaves the sketch OPEN.
    """
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("could not select Front Plane")
    sm.InsertSketch(True)

    r = 0.005
    sm.CreateCircle(x_offset_m, 0.0, 0.0, x_offset_m + r, 0.0, 0.0)

    doc.ClearSelection2(True)
    if not doc.SelectByID("", "SKETCHSEGMENT", x_offset_m + r, 0.0, 0.0):
        raise RuntimeError("could not select circle for dim")
    dim = doc.AddDimension2(x_offset_m + r + 0.005, 0.005, 0.0)
    return dim


def _close_sketch(sm):
    sm.InsertSketch(True)


def _geometry_ok(doc) -> bool:
    """Quick check: does the part have a non-zero volume?"""
    try:
        mp = doc.Extension.CreateMassProperty
        vol = mp.Mass
        return vol is not None and vol > 0
    except Exception:
        return False


def _try_strategy(doc, sm, sw, strategy: str, x_offset_m: float) -> dict:
    """Run one strategy. Returns a result dict."""
    t0 = time.time()
    try:
        dim = _open_sketch_and_add_dim(doc, sm, x_offset_m)
        if dim is None:
            return {
                "strategy": strategy,
                "status": "FAIL",
                "error": "AddDimension2 returned None",
            }

        applied = False
        method_result = None
        try:
            if strategy == "T1_RunCommand_2421":
                method_result = doc.Extension.RunCommand(2421, "")
                applied = True
            elif strategy == "T2_ClosePM_after_rebuild":
                doc.ForceRebuild3(False)
                time.sleep(0.1)
                method_result = doc.ClosePropertyManager()
                applied = True
            elif strategy == "T3_toggle78_before_sketch":
                # This one needs to be tested differently: set toggle
                # BEFORE opening any sketch
                sw.SetUserPreferenceToggle(
                    SW_SKETCH_ENABLE_ON_SCREEN_NUMERIC_INPUT, False
                )
                method_result = "toggle78_set"
                applied = True
            elif strategy == "T4_SetAddDimReturn":
                try:
                    method_result = doc.SetAddDimension2Return(0)
                    applied = True
                except AttributeError:
                    return {
                        "strategy": strategy,
                        "status": "NO_SUCH_API",
                        "error": "SetAddDimension2Return not found on doc",
                    }
            elif strategy == "T5_RunCommand_2421_with_sleep":
                method_result = doc.Extension.RunCommand(2421, "")
                time.sleep(0.5)
                applied = True
            elif strategy == "T6_control_no_dismiss":
                applied = True  # control
        except Exception as e:
            return {
                "strategy": strategy,
                "status": "ERROR_IN_STRATEGY",
                "error": repr(e),
                "applied": applied,
            }

        # Probe: can we still do COM calls?
        try:
            doc.ClearSelection2(True)
            _close_sketch(sm)
            elapsed = time.time() - t0
            geo = _geometry_ok(doc)
            return {
                "strategy": strategy,
                "status": "PASS",
                "method_result": str(method_result),
                "elapsed_s": round(elapsed, 3),
                "geometry_ok": geo,
            }
        except Exception as e:
            return {
                "strategy": strategy,
                "status": "FAIL_AFTER_STRATEGY",
                "error": repr(e),
                "method_result": str(method_result),
            }

    except Exception as e:
        return {"strategy": strategy, "status": "FAIL_SETUP", "error": repr(e)}


def run() -> dict:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        return {"status": "FAIL", "error": "no active doc; open blank part first"}

    fc = doc.GetFeatureCount
    if fc > 17:
        return {
            "status": "FAIL",
            "error": f"doc not blank: {fc} features. File > New > Part first.",
        }

    sm = doc.SketchManager

    # Suppress the Modify popup to isolate the PM-pane question
    prev = sw.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, False)

    results = []
    strategies = [
        "T1_RunCommand_2421",
        "T2_ClosePM_after_rebuild",
        "T3_toggle78_before_sketch",
        "T4_SetAddDimReturn",
        "T5_RunCommand_2421_with_sleep",
        "T6_control_no_dismiss",
    ]

    try:
        for i, s in enumerate(strategies):
            x_offset_m = i * 0.030
            r = _try_strategy(doc, sm, sw, s, x_offset_m)
            results.append(r)
    finally:
        sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, prev)

    return {"status": "DONE", "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com"], default="com")
    parser.parse_args()

    out = run()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
