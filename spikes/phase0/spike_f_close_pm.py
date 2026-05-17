"""
Spike F - dismiss the Dimension PropertyManager pane after AddDimension2.

Context from MMP debug 2026-05-16: the small floating "Modify Dimension"
popup is suppressed via swInputDimValOnCreate=False, but a separate
left-side Dimension PropertyManager pane still opens after each
AddDimension2 and pauses the build until manually green-ticked.

This spike adds a single dim and tries several APIs to close the pane,
reporting which one works without re-enabling the popup or losing the
dim.

Preconditions: a fresh blank Part is open in SW (caller does File > New).

Strategies tried:
  S1: ClosePropertyManager()         -- the natural "press OK" API
  S2: CloseAndDestroyPropertyManagers
  S3: Extension.RunCommand(swCmd_PmOK, "") -- explicit PM-OK command
  S4: Just continue without dismissing (control)

Each strategy runs in an isolated trial: open new sketch -> add 1 dim ->
try to dismiss -> probe whether the next COM call (selecting a sketch
segment) succeeds without hanging.

Output: JSON {strategy: status} so we can pick the winner before
patching builder.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402

SW_INPUT_DIM_VAL_ON_CREATE = 8


def _open_sketch_and_add_dim(doc, sm, x_offset_m: float):
    """Create a 10mm circle on Front Plane and add a diameter dim.

    Returns the IDisplayDimension. Leaves the sketch OPEN so the caller
    can observe the PM pane state.
    """
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("could not select Front Plane")
    sm.InsertSketch(True)

    # 10mm dia circle centered at (x_offset, 0)
    r = 0.005
    sm.CreateCircle(x_offset_m, 0.0, 0.0, x_offset_m + r, 0.0, 0.0)

    doc.ClearSelection2(True)
    if not doc.SelectByID("", "SKETCHSEGMENT", x_offset_m + r, 0.0, 0.0):
        raise RuntimeError("could not select circle for dim")
    dim = doc.AddDimension2(x_offset_m + r + 0.005, 0.005, 0.0)
    return dim


def _close_sketch(sm):
    sm.InsertSketch(True)


def _try_strategy(doc, sm, strategy: str, x_offset_m: float) -> dict:
    """Run one strategy. Returns a result dict with status + diagnostics."""
    t0 = time.time()
    try:
        dim = _open_sketch_and_add_dim(doc, sm, x_offset_m)
        if dim is None:
            return {
                "strategy": strategy,
                "status": "FAIL",
                "error": "AddDimension2 returned None",
            }

        # Apply the strategy
        applied = False
        method_result = None
        try:
            if strategy == "S1_ClosePropertyManager":
                method_result = doc.ClosePropertyManager()
                applied = True
            elif strategy == "S2_CloseAndDestroyPMs":
                # This is on IModelDocExtension typically
                ext = doc.Extension
                method_result = ext.CloseAndDestroyPropertyManagers()
                applied = True
            elif strategy == "S3_RunCommand_PmOK":
                # swCommands_PmOK = constant (need to discover)
                # Try a few candidates: swCommands_Sketch_QuickSnaps_PmOK?
                # Most likely: -2 is "OK" in PM context, or specific named cmd
                ext = doc.Extension
                # Try the documented PM-OK command id. SW docs: "PmOK" command
                # in swUserPreferenceIntegerValue is not the right approach;
                # RunCommand takes a swCommands_e value. Common: 1 = OK button.
                method_result = ext.RunCommand(1, "")
                applied = True
            elif strategy == "S4_no_dismiss":
                applied = True  # control
        except Exception as e:
            return {
                "strategy": strategy,
                "status": "ERROR_IN_STRATEGY",
                "error": repr(e),
                "applied": applied,
            }

        # Probe: can we still do COM calls? Try ClearSelection2 + close sketch
        try:
            doc.ClearSelection2(True)
            _close_sketch(sm)
            elapsed = time.time() - t0
            return {
                "strategy": strategy,
                "status": "PASS",
                "method_result": str(method_result),
                "elapsed_s": round(elapsed, 3),
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

    # Suppress the Modify popup (we want to isolate the PM-pane question)
    prev = sw.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, False)

    results = []
    strategies = [
        "S1_ClosePropertyManager",
        "S2_CloseAndDestroyPMs",
        "S3_RunCommand_PmOK",
        "S4_no_dismiss",
    ]

    try:
        for i, s in enumerate(strategies):
            # Space each test 30mm apart so sketches don't overlap
            x_offset_m = i * 0.030
            r = _try_strategy(doc, sm, s, x_offset_m)
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
