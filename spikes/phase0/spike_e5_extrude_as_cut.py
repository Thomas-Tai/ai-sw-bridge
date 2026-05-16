"""
Spike E5 - test if FeatureExtrusion2 acts as a cut when the sketch
overlaps an existing solid.

Background: FeatureCut4 PARAMNOTOPTIONAL is a wall via pywin32 late-
binding (spikes E, E2, E3, E4 all confirm). If FeatureExtrusion2 can
auto-detect that a sketch on a face of an existing body should produce
a cut instead of a boss, we avoid FeatureCut4 entirely.

Test:
1. Build box (20x20x5mm).
2. Sketch a circle (Ø6mm) on the top face.
3. Call FeatureExtrusion2 with:
   - Same args as boss
   - But Merge=True and the sketch is on an existing face
   - SW *may* auto-detect overlap and cut. Or it may produce a boss.
4. Inspect the result. If a cut, FeatureExtrusion2 returns a feature
   whose type ends in "...Cut" instead of "...Boss". If a boss, we
   know cuts aren't auto-detected on this build.

Preconditions: blank Part open.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


def _build_box(doc):
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("select Front Plane")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0.0, 0.010, 0.010, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Box"
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box", "SKETCH", 0.0, 0.0, 0.0)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True, False, False, 0, 0,
        0.005, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True, 0, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("box FeatureExtrusion2 None")
    feat.Name = "Box"


def _hole_sketch_on_top(doc) -> str:
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.0, 0.0, 0.005):
        raise RuntimeError("select top face")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)  # Ø6mm
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_HoleSketch"
    return "SK_HoleSketch"


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"ok": False, "error": "no doc"}))
        return 1
    if doc.GetFeatureCount > 17:
        print(json.dumps({"ok": False,
                          "error": f"not blank ({doc.GetFeatureCount})"}))
        return 1

    try:
        _build_box(doc)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"box: {e!r}"}))
        return 1

    sk_name = _hole_sketch_on_top(doc)
    doc.ClearSelection2(True)
    doc.SelectByID(sk_name, "SKETCH", 0.0, 0.0, 0.0)

    fm = doc.FeatureManager

    # Try FeatureExtrusion2 with Flip=True (extruding INTO the box).
    # If SW auto-detects this should cut, we get a cut. Else, a boss
    # protruding into / under the box.
    results = []

    test_variants = [
        ("blind_flip_True_d5_merge", True,  True,  0, 0.005, True),
        ("blind_flip_False_d5_merge", True, False, 0, 0.005, True),
        ("through_all_flip_True", True, True, 4, 0.0, True),
        ("blind_flip_True_d5_no_merge", True, True, 0, 0.005, False),
    ]
    # args: (label, Sd, Flip, T1, D1, Merge)

    for label, sd, flip, t1, d1, merge in test_variants:
        # Each variant needs a fresh sketch because the previous call
        # consumed it.
        try:
            sk = _hole_sketch_on_top(doc)
        except Exception as e:
            results.append({"label": label, "ok": False,
                            "error": f"sketch: {e!r}"})
            continue
        doc.ClearSelection2(True)
        doc.SelectByID(sk, "SKETCH", 0.0, 0.0, 0.0)

        try:
            f = fm.FeatureExtrusion2(
                sd, flip, False, t1, 0,
                d1, 0.0,
                False, False, False, False, 0.0, 0.0,
                False, False, False, False,
                merge,
                True, True, 0, 0.0, False,
            )
            if f is None:
                results.append({"label": label, "ok": False,
                                "error": "FeatureExtrusion2 returned None"})
                continue
            # Inspect feature type
            ftype = "UNKNOWN"
            fname = "UNKNOWN"
            try:
                ftype = str(f.GetTypeName)
            except Exception:
                pass
            try:
                fname = str(f.Name)
            except Exception:
                pass
            is_cut = "Cut" in ftype or "cut" in ftype.lower()
            results.append({"label": label, "ok": True,
                            "feature_type": ftype, "feature_name": fname,
                            "looks_like_cut": is_cut})
            # Undo to clean slate
            try:
                doc.EditUndo2(1)
            except Exception:
                pass
        except Exception as e:
            results.append({"label": label, "ok": False, "error": repr(e)})

    print(json.dumps({"results": results}, indent=2))
    cuts = [r for r in results if r.get("looks_like_cut")]
    return 0 if cuts else 1


if __name__ == "__main__":
    sys.exit(main())
