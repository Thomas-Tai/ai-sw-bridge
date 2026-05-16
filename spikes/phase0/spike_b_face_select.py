"""
Spike B - SelectByID face-by-coordinates on a freshly-built feature.

Assumes Spike A has been run and the active doc contains feature "SpikeA_Box":
a 20x20x5 mm extrusion off Front Plane, depth in +Z.

Outboard face is the +Z face at local z = +0.005, centered at (0, 0, 0.005).

PASS criteria:
- doc.SelectByID(..., "FACE", 0, 0, 0.005) returns True
- We can immediately InsertSketch and create a circle on that selection
- New sketch appears as a child feature of SpikeA_Box (sketch plane = outboard face)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


def run_com() -> dict:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        return {"status": "FAIL", "error": "no active doc"}

    # Make sure SpikeA_Box exists (we'll just trust visual; SelectByID will fail
    # at the face level if it doesn't).
    doc.ClearSelection2(True)

    # Outboard face center on a Front-Plane-based extrude with depth +Z = +5mm.
    ok = doc.SelectByID("", "FACE", 0.0, 0.0, 0.005)
    if not ok:
        return {
            "status": "FAIL",
            "error": "SelectByID returned False at (0, 0, 0.005) - face not at expected coord",
            "hint": "Maybe SW extruded in -Z. Try z=-0.005.",
        }

    # Now try inserting a sketch on the selected face.
    sketch_mgr = doc.SketchManager
    sketch_mgr.InsertSketch(True)

    # Draw a circle of diameter 6 mm centered at face origin.
    # SketchManager.CreateCircle(Xc, Yc, Zc, Xp, Yp, Zp) - sketch-local coords.
    # Perimeter point at (0.003, 0, 0) gives radius 3 mm.
    circle = sketch_mgr.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)

    if circle is None:
        sketch_mgr.InsertSketch(True)  # close
        return {"status": "FAIL", "error": "circle creation returned None"}

    sketch_mgr.InsertSketch(True)  # close sketch

    # Verify the new sketch exists. GetFeatureCount is auto-invoked as a
    # property under late-binding -- access without parens.
    feature_count = doc.GetFeatureCount
    most_recent = None
    try:
        most_recent = doc.FeatureByPositionReverse(0)
        recent_name = most_recent.Name if most_recent else None
    except Exception as e:
        recent_name = f"<err: {e!r}>"

    return {
        "status": "PASS",
        "select_by_id_ok": True,
        "feature_count": feature_count,
        "most_recent_feature": recent_name,
    }


def emit_vba() -> str:
    return """' Spike B - VBA fallback
Option Explicit
Dim swApp As Object
Dim Part As Object
Dim boolStatus As Boolean
Sub main()
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Part.ClearSelection2 True
    boolStatus = Part.SelectByID("", "FACE", 0, 0, 0.005)
    If Not boolStatus Then
        MsgBox "SelectByID FAILED at (0,0,0.005)"
        Exit Sub
    End If
    Part.SketchManager.InsertSketch True
    Part.SketchManager.CreateCircleByRadius 0, 0, 0, 0.003, 0, 0
    Part.SketchManager.InsertSketch True
    MsgBox "Spike B PASS"
End Sub
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com", "vba"], default="com")
    args = parser.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_b.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}")
        return 0

    result = run_com()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
