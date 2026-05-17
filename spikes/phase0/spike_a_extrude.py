"""
Spike A — FeatureManager.FeatureExtrusion2 via pywin32 late-binding.

Builds a 20x20x5 mm box on the Front plane of the currently active blank part.

Usage:
    python spike_a_extrude.py --mode=com    # direct COM
    python spike_a_extrude.py --mode=vba    # emit .bas you paste into VBE+F5

PASS criteria:
- Returns a non-None Feature object
- Feature.Name reads as a string (we then rename it to "SpikeA_Box")
- Manual visual check: 20x20x5 box centered at origin on Front plane

Notes on the call:
- SOLIDWORKS API: IFeatureManager::FeatureExtrusion2 (22 args)
  see https://help.solidworks.com/2024/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeatureManager~FeatureExtrusion2.html
- SI units throughout (meters for length)
- swEndCondBlind = 0, swEndCondMidPlane = 5; we use Blind in one direction
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reach the package's sw_com helper without forcing install side-effects.
_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


# SW enum values used in this spike
SW_SELECTYPE_SKETCH = "SKETCH"
SW_END_COND_BLIND = 0


BOX_W = 0.020  # 20 mm
BOX_H = 0.020  # 20 mm
BOX_T = 0.005  # 5 mm


def run_com() -> dict:
    """Build the box by directly calling FeatureExtrusion2 via late-binding.

    Returns a dict {status, feature_name, error}.
    """
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        return {"status": "FAIL", "error": "no active doc; open a blank part first"}

    # Select Front plane to sketch on.
    # NOTE: SelectByID2's Callout arg can't be marshalled via late-binding
    # (see docs/known_gotchas.md). Use legacy 5-arg SelectByID on IModelDoc2.
    # SelectByID signature: (Name, Type, X, Y, Z) -> Boolean
    ok = doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    if not ok:
        return {"status": "FAIL", "error": "could not select Front Plane"}

    sketch_mgr = doc.SketchManager
    sketch_mgr.InsertSketch(True)

    # Centered rectangle: SketchManager.CreateCornerRectangle(x1,y1,z1,x2,y2,z2)
    # In the active sketch's coordinate system (sketch X/Y, Z=0 in plane).
    half_w = BOX_W / 2.0
    half_h = BOX_H / 2.0
    sketch_mgr.CreateCornerRectangle(-half_w, -half_h, 0.0, half_w, half_h, 0.0)

    # Exit (close) sketch by toggling InsertSketch again
    sketch_mgr.InsertSketch(True)

    # Re-select the sketch we just created (it auto-named, e.g. "Sketch1").
    # The trick: SelectByID2 with "" name + "SKETCH" type does not work; we
    # need the actual feature name. SW just-closed-sketch is selectable via
    # ClearSelection2 + SelectByID2 with name.
    # However, immediately after InsertSketch, the sketch is implicitly
    # selected. We can skip the re-select and call FeatureExtrusion2.
    # If that fails, we'll fall through and select Sketch1 explicitly.

    fm = doc.FeatureManager

    # FeatureExtrusion2 (22 args):
    #   Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2,
    #   Dang1, Dang2, OffsetReverse1, OffsetReverse2, TranslateSurface1, TranslateSurface2,
    #   Merge, UseFeatScope, UseAutoSelect, T0, StartOffset
    #
    # Sd = single-direction (True), Flip = False, Dir = False (use sketch normal),
    # T1 = swEndCondBlind, T2 = blind (unused for single-dir),
    # D1 = depth m, D2 = 0,
    # Draft check / dir / angle all 0 / False
    # Merge = True, UseFeatScope = True, UseAutoSelect = True
    # T0 = swStartSketchPlane = 0, StartOffset = 0.0
    try:
        feature = fm.FeatureExtrusion2(
            True,  # Sd (single direction)
            False,  # Flip
            False,  # Dir (use sketch normal)
            SW_END_COND_BLIND,  # T1
            0,  # T2
            BOX_T,  # D1 (5 mm)
            0.0,  # D2
            False,  # Dchk1
            False,  # Dchk2
            False,  # Ddir1
            False,  # Ddir2
            0.0,  # Dang1
            0.0,  # Dang2
            False,  # OffsetReverse1
            False,  # OffsetReverse2
            False,  # TranslateSurface1
            False,  # TranslateSurface2
            True,  # Merge
            True,  # UseFeatScope
            True,  # UseAutoSelect
            0,  # T0 (swStartSketchPlane)
            0.0,  # StartOffset
            False,  # FlipStartOffset (some docs show 22 args, some 23)
        )
    except Exception as e:
        # try the 22-arg form if 23-arg failed
        try:
            feature = fm.FeatureExtrusion2(
                True,
                False,
                False,
                SW_END_COND_BLIND,
                0,
                BOX_T,
                0.0,
                False,
                False,
                False,
                False,
                0.0,
                0.0,
                False,
                False,
                False,
                False,
                True,
                True,
                True,
                0,
                0.0,
            )
        except Exception as e2:
            return {
                "status": "FAIL",
                "error": f"FeatureExtrusion2 raised: 23-arg={e!r}; 22-arg={e2!r}",
            }

    if feature is None:
        return {"status": "FAIL", "error": "FeatureExtrusion2 returned None"}

    try:
        original_name = feature.Name
    except Exception as e:
        return {
            "status": "PARTIAL",
            "feature_name": "?",
            "error": f"got feature but Name failed: {e!r}",
        }

    # Try to rename it
    try:
        feature.Name = "SpikeA_Box"
        renamed = True
    except Exception:
        renamed = False

    return {
        "status": "PASS",
        "original_name": original_name,
        "renamed_to": "SpikeA_Box" if renamed else original_name,
        "feature_obj_callable": True,
    }


def emit_vba() -> str:
    """Emit a .bas file with the same construction as run_com()."""
    return f"""' Spike A - VBA fallback
' Builds a {int(BOX_W*1000)}x{int(BOX_H*1000)}x{int(BOX_T*1000)} mm box on Front Plane
' Paste into the active blank part's VBE and press F5
Option Explicit
Dim swApp As Object
Dim Part As Object
Dim feature As Object
Dim boolStatus As Boolean
Sub main()
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    If Part Is Nothing Then
        MsgBox "No active doc"
        Exit Sub
    End If

    boolStatus = Part.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0)
    Part.SketchManager.InsertSketch True
    Part.SketchManager.CreateCornerRectangle {-BOX_W/2}, {-BOX_H/2}, 0, {BOX_W/2}, {BOX_H/2}, 0
    Part.SketchManager.InsertSketch True

    Set feature = Part.FeatureManager.FeatureExtrusion2( _
        True, False, False, _
        0, 0, _
        {BOX_T}, 0, _
        False, False, False, False, _
        0, 0, _
        False, False, False, False, _
        True, True, True, _
        0, 0, False)

    If feature Is Nothing Then
        MsgBox "FeatureExtrusion2 returned Nothing"
        Exit Sub
    End If
    feature.Name = "SpikeA_Box"
    MsgBox "Spike A PASS: " & feature.Name
End Sub
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com", "vba"], default="com")
    args = parser.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_a.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}")
        print("Paste into VBE, press F5, with the blank part as active doc.")
        return 0

    import json

    result = run_com()
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
