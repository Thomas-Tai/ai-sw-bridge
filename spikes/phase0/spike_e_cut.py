"""
Spike E - find a working FeatureCut signature on this SW 2024 build via late-binding.

Auto-builds the prerequisite shape (20x20x5mm box + circle sketch on top face),
then tries multiple FeatureCut4 arg-count variants and reports which succeed.

Why each is tried: the SW API docs list 24-arg form, but PARAMNOTOPTIONAL on
25-arg attempts during MMP build (2026-05-16) suggested the actual signature
may differ on SW 2024 SP1. Test 23, 24, 25 systematically.

Workflow per variant:
  1. Open/reuse a sketch with a circle on the top face of the box
  2. Exit sketch (so it's the "active sketch" for FeatureCut4)
  3. Select the sketch by name
  4. Call FeatureCut4 with the variant's arg list
  5. If success: roll back via EditUndo2 to clean state for next variant
  6. Record result

Preconditions: SW is running with a blank Part already open.

Note: dimensions are added but builder reuses AddDimension2 -- user must
manually tick the Modify popup + PM pane (~6 ticks for setup). This is
the accepted limitation documented in MMP_DEBUG_SESSION.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


SW_END_COND_BLIND = 0
SW_END_COND_THROUGH_ALL = 4


def _build_box(doc):
    """20x20x5mm box on Front Plane. Returns the boss-extrude feature."""
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("could not select Front Plane")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    # 20x20 mm corner rectangle centered at origin (so the box occupies
    # x,y in [-0.010, +0.010], z in [0, depth])
    sm.CreateCornerRectangle(-0.010, -0.010, 0.0, 0.010, 0.010, 0.0)
    # Two dims so the rect is fully defined. (Manual ticks: 2x2 = 4)
    doc.ClearSelection2(True)
    doc.SelectByID("", "SKETCHSEGMENT", 0.0, 0.010, 0.0)
    doc.AddDimension2(0.0, 0.015, 0.0)
    doc.ClearSelection2(True)
    doc.SelectByID("", "SKETCHSEGMENT", -0.010, 0.0, 0.0)
    doc.AddDimension2(-0.015, 0.0, 0.0)
    sm.InsertSketch(True)  # close sketch

    # Rename the sketch
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Box"

    # Extrude 5mm
    doc.ClearSelection2(True)
    if not doc.SelectByID("SK_Box", "SKETCH", 0.0, 0.0, 0.0):
        raise RuntimeError("could not select SK_Box")
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,           # Sd
        False,          # Flip
        False,          # Dir
        SW_END_COND_BLIND, 0,
        0.005, 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False,
        True, True, True,
        0, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("FeatureExtrusion2 returned None")
    feat.Name = "Box"
    return feat


def _build_circle_sketch_on_top(doc):
    """Sketch a Ø6mm circle centered on the top face (+z) of the box.

    Top face center for our 20x20x5mm box on Front Plane is (0, 0, 0.005).
    Returns the sketch feature (already closed).
    """
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.0, 0.0, 0.005):
        raise RuntimeError("could not select top face at (0,0,0.005)")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    # Ø6mm centered at face origin (0, 0)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)
    # One dim. (Manual ticks: 1x2 = 2)
    doc.ClearSelection2(True)
    doc.SelectByID("", "SKETCHSEGMENT", 0.003, 0.0, 0.0)
    doc.AddDimension2(0.005, 0.005, 0.0)
    sm.InsertSketch(True)  # close

    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Hole"
    return sk


def _build_circle_sketch_fresh(doc, name_suffix: int):
    """Build a NEW circle sketch on the top face for the next cut attempt.

    Each cut variant test needs a fresh sketch because the previous one
    was consumed (or its cut got undone).
    """
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.0, 0.0, 0.005):
        raise RuntimeError("could not select top face for hole sketch")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    # Place the circle at a different x for each attempt so they don't overlap
    # if a previous undo didn't fully clean up
    cx = -0.005 + (name_suffix * 0.003)
    sm.CreateCircle(cx, 0.0, 0.0, cx + 0.0015, 0.0, 0.0)  # Ø3mm
    # No dim here -- the cut just needs the geometry; skip dim ticks
    sm.InsertSketch(True)

    sk = doc.FeatureByPositionReverse(0)
    name = f"SK_Hole_{name_suffix}"
    sk.Name = name
    return name


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"ok": False, "error": "no active doc"}))
        return 1

    if doc.GetFeatureCount > 17:
        print(json.dumps({"ok": False,
                          "error": f"doc not blank ({doc.GetFeatureCount} features); "
                          "File>New>Part first"}))
        return 1

    # 1. Build box
    try:
        _build_box(doc)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"box build failed: {e!r}"}))
        return 1

    # Reference SW API arg order for FeatureCut4 (SW 2024):
    #   Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2,
    #   Dang1, Dang2, OffsetReverse1, OffsetReverse2,
    #   TranslateSurface1, TranslateSurface2, NormalCut,
    #   UseFeatScope, UseAutoSelect, AssemblyFeatureScope,
    #   T0, StartOffset, FlipStartOffset
    # = 24 args.
    variants = {
        "23_args_through_all": [
            True, False, False,
            SW_END_COND_THROUGH_ALL, 0,
            0.001, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0.0, False,
        ],
        "24_args_through_all": [
            True, False, False,
            SW_END_COND_THROUGH_ALL, 0,
            0.001, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            False,
            True, True, True,
            0, 0.0, False,
        ],
        "25_args_through_all": [
            True, False, False,
            SW_END_COND_THROUGH_ALL, 0,
            0.001, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            False, False,
            True, True, True,
            0, 0.0, False,
        ],
        "26_args_through_all": [
            True, False, False,
            SW_END_COND_THROUGH_ALL, 0,
            0.001, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            False, False, False,
            True, True, True,
            0, 0.0, False,
        ],
    }

    fm = doc.FeatureManager
    results = []

    for i, (name, args) in enumerate(variants.items()):
        # Build a fresh sketch for this attempt
        try:
            sk_name = _build_circle_sketch_fresh(doc, i)
        except Exception as e:
            results.append({"variant": name, "arg_count": len(args), "ok": False,
                            "error": f"sketch setup: {e!r}"})
            continue

        # Select the sketch and try the cut
        doc.ClearSelection2(True)
        if not doc.SelectByID(sk_name, "SKETCH", 0.0, 0.0, 0.0):
            results.append({"variant": name, "arg_count": len(args), "ok": False,
                            "error": f"select sketch {sk_name} failed"})
            continue

        try:
            f = fm.FeatureCut4(*args)
            results.append({"variant": name, "arg_count": len(args), "ok": True,
                            "feature_returned": f is not None})
            if f is not None:
                # Roll back so the next variant has a clean slate.
                try:
                    doc.EditUndo2(1)
                except Exception:
                    pass
        except Exception as e:
            results.append({"variant": name, "arg_count": len(args), "ok": False,
                            "error": repr(e)})

    succeeded = [r for r in results if r.get("ok")]
    print(json.dumps({
        "results": results,
        "succeeded_count": len(succeeded),
        "winning_arg_counts": [r["arg_count"] for r in succeeded],
    }, indent=2))
    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
