"""
Spike K - reproduce and characterize the "cut on face containing pre-existing
through-hole" failure mode, then test workarounds.

Setup:
  1. Build 50x50x5mm box on Front Plane
  2. Cut a 12mm-dia through-hole at center (mimics MMP coupler hole)
  3. Try cuts that need to coexist with that hole

Attempts:
  A. Sketch on the +z face, draw a 20mm-dia concentric circle, cut blind 1mm.
     (the MMP failure mode)
  B. Same as A but sketch on Front Plane (the underlying plane), then cut
     blind 1mm starting at z=4mm (StartOffset = 0.004m, FlipStartOffset=False).
     The cut should remove material from z=4mm to z=5mm.
  C. Sketch on the +z face but with the circle off-center so its interior
     overlaps material.

Preconditions: blank Part open.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402
from ai_sw_bridge.sw_types import (  # noqa: E402
    SW_END_COND_BLIND,
    SW_END_COND_THROUGH_ALL,
    SW_START_SKETCH_PLANE,
    SW_START_OFFSET,
)


def _build_box_with_hole(doc):
    """50x50x5mm box on Front + Ø12mm through-hole at center."""
    # 1. Rect sketch
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("Front Plane")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.025, -0.025, 0.0, 0.025, 0.025, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Box"

    # 2. Box extrude
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box", "SKETCH", 0.0, 0.0, 0.0)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        0.005,
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
    if feat is None:
        raise RuntimeError("box extrude None")
    feat.Name = "Box"

    # 3. Coupler hole sketch on -z face (which is Front Plane at z=0)
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.0, 0.0, 0.0):
        raise RuntimeError("-z face")
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.006, 0.0, 0.0)  # Ø12mm
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Hole"

    # 4. Cut through all
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Hole", "SKETCH", 0.0, 0.0, 0.0)
    cut_args = (
        True,
        False,
        False,
        SW_END_COND_THROUGH_ALL,
        0,
        0.0,
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
        False,
        True,
        True,
        True,
        True,
        False,
        SW_START_SKETCH_PLANE,
        0.0,
        False,
        False,
    )
    feat = fm.FeatureCut4(*cut_args)
    if feat is None:
        raise RuntimeError("through-hole cut None")
    feat.Name = "Cut_Hole"


def _attempt_A_face_concentric(doc):
    """Sketch on +z face, Ø20mm concentric, cut blind 1mm. Expected: fail."""
    # Use offset face selection (15mm offset)
    doc.ClearSelection2(True)
    sel_ok = doc.SelectByID("", "FACE", 0.015, 0.0, 0.005)
    if not sel_ok:
        return {"attempt": "A", "step": "face_select", "ok": False}
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.010, 0.0, 0.0)  # Ø20mm at origin
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_A_FaceConcentric"

    doc.ClearSelection2(True)
    doc.SelectByID("SK_A_FaceConcentric", "SKETCH", 0.0, 0.0, 0.0)
    fm = doc.FeatureManager
    cut_args = (
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        0.001,
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
        False,
        True,
        True,
        True,
        True,
        False,
        SW_START_SKETCH_PLANE,
        0.0,
        False,
        False,
    )
    feat = fm.FeatureCut4(*cut_args)
    return {"attempt": "A_face_concentric", "cut_ok": feat is not None}


def _attempt_B_plane_with_start_offset(doc):
    """Sketch on Front Plane, Ø20mm concentric, cut blind 1mm starting at z=4mm.

    The cut direction is normal to Front Plane (+Z). With StartOffset = 4mm,
    the cut starts at z=4mm and goes 1mm forward to z=5mm.
    """
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"attempt": "B", "step": "plane_select", "ok": False}
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.010, 0.0, 0.0)  # Ø20mm
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_B_PlaneOffset"

    doc.ClearSelection2(True)
    doc.SelectByID("SK_B_PlaneOffset", "SKETCH", 0.0, 0.0, 0.0)
    fm = doc.FeatureManager
    # T0 = SW_START_OFFSET (3), StartOffset = 0.004m, FlipStartOffset=False
    cut_args = (
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        0.001,
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
        False,
        True,
        True,
        True,
        True,
        False,
        SW_START_OFFSET,
        0.004,
        False,
        False,
    )
    feat = fm.FeatureCut4(*cut_args)
    return {
        "attempt": "B_plane_with_StartOffset",
        "cut_ok": feat is not None,
        "args": "T0=swStartOffset(3), StartOffset=4mm",
    }


def _attempt_C_face_off_center(doc):
    """Sketch on +z face, Ø8mm circle off-center at (12, 0). Tests whether
    a face-based sketch works when the circle is entirely on material."""
    doc.ClearSelection2(True)
    sel_ok = doc.SelectByID("", "FACE", 0.015, 0.0, 0.005)
    if not sel_ok:
        return {"attempt": "C", "step": "face_select", "ok": False}
    sm = doc.SketchManager
    sm.InsertSketch(True)
    # Center at (12mm, 0); the circle is at radius 4mm so it spans (8, 16)
    # mm in x -- well outside the 6mm-radius hole.
    sm.CreateCircle(0.012, 0.0, 0.0, 0.012 + 0.004, 0.0, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_C_FaceOffCenter"

    doc.ClearSelection2(True)
    doc.SelectByID("SK_C_FaceOffCenter", "SKETCH", 0.0, 0.0, 0.0)
    fm = doc.FeatureManager
    cut_args = (
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        0.001,
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
        False,
        True,
        True,
        True,
        True,
        False,
        SW_START_SKETCH_PLANE,
        0.0,
        False,
        False,
    )
    feat = fm.FeatureCut4(*cut_args)
    return {"attempt": "C_face_off_center", "cut_ok": feat is not None}


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"ok": False, "error": "no doc"}))
        return 1
    if doc.GetFeatureCount > 17:
        print(json.dumps({"ok": False, "error": f"not blank ({doc.GetFeatureCount})"}))
        return 1

    try:
        _build_box_with_hole(doc)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"setup: {e!r}"}))
        return 1

    results = []
    for attempt_fn in (
        _attempt_A_face_concentric,
        _attempt_B_plane_with_start_offset,
        _attempt_C_face_off_center,
    ):
        try:
            r = attempt_fn(doc)
            results.append(r)
        except Exception as e:
            results.append({"attempt": attempt_fn.__name__, "error": repr(e)})

    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
