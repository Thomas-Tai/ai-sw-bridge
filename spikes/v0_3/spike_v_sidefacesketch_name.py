"""
Spike V: does setting IFeature.Name on a sketch created on a side face
actually persist so SelectByID("name", "SKETCH", 0,0,0) finds it?

Side_face_bosses example fails at the second boss_extrude_blind because
_select_sketch (which uses SelectByID) cannot find a sketch named
"SK_BossPlusX" that was created on the +x face. Patterned_disc works
fine for the +z-face equivalent.

Hypothesis: the sketch is being created, named, AND found by
FeatureByPositionReverse(0), but the .Name property isn't persisted to
SW's name database, OR something about the side-face context puts the
sketch into a sub-feature-tree position not visible to SelectByID.

This spike: build a 30x30x20 box, sketch a circle on +x face, NAME the
sketch, close the sketch, THEN immediately try SelectByID with the name.
Report whether the name persisted.

Usage:
    python spikes/v0_3/spike_v_sidefacesketch_name.py
"""

from __future__ import annotations

import sys
import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0


def _create_box(doc, side_mm: float, depth_mm: float) -> None:
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    half = side_mm / 2 / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, half, half, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        depth_mm / 1000,
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
        SW_START_SKETCH_PLANE,
        0.0,
        False,
    )


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2

    print("== Spike V: side-face sketch name persistence ==")
    _create_box(doc, side_mm=30.0, depth_mm=20.0)

    # Sketch on +x face (face plane x=15mm, mid-height z=10mm)
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.015, 0.0, 0.010):
        print("! could not select +x face")
        return 3
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)  # 3mm radius at sketch (0,0)
    sm.InsertSketch(True)

    sketch_feat = doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        print("! no sketch produced via FeatureByPositionReverse")
        return 4
    print(
        f"  sketch obtained via FBPR(0): name='{sketch_feat.Name}', "
        f"type='{sketch_feat.GetTypeName2}'"
    )

    sketch_feat.Name = "SK_TestPlusX"
    print(f"  after Name='SK_TestPlusX' set, sketch_feat.Name='{sketch_feat.Name}'")

    # Try SelectByID with name
    doc.ClearSelection2(True)
    ok = doc.SelectByID("SK_TestPlusX", "SKETCH", 0.0, 0.0, 0.0)
    print(f"  SelectByID('SK_TestPlusX', 'SKETCH', 0,0,0) -> {ok}")

    # Try with the FeatureByPositionReverse approach
    doc.ClearSelection2(True)
    fbpr = doc.FeatureByPositionReverse(0)
    if fbpr is None:
        print(f"  FeatureByPositionReverse(0) after sketch close -> None")
    else:
        print(f"  FBPR(0) name='{fbpr.Name}', type='{fbpr.GetTypeName2()}'")

    # Print top-N features for context
    print("  ---- top features (FBPR order) ----")
    for i in range(8):
        try:
            f = doc.FeatureByPositionReverse(i)
            if f is None:
                break
            print(f"    [{i}] name='{f.Name}', type='{f.GetTypeName2}'")
        except Exception:
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
