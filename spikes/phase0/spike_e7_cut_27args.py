"""
Spike E7 - the correct FeatureCut4 signature is 27 args (not 24).

Per the SOLIDWORKS API help file (sldworksapi.chm, decompiled
2026-05-17), IFeatureManager::FeatureCut4 takes 27 parameters:

  1.  Sd                       (bool)
  2.  Flip                     (bool)
  3.  Dir                      (bool)
  4.  T1                       (int)   swEndConditions_e
  5.  T2                       (int)
  6.  D1                       (double) meters
  7.  D2                       (double) meters
  8.  Dchk1                    (bool)
  9.  Dchk2                    (bool)
  10. Ddir1                    (bool)
  11. Ddir2                    (bool)
  12. Dang1                    (double)
  13. Dang2                    (double)
  14. OffsetReverse1           (bool)
  15. OffsetReverse2           (bool)
  16. TranslateSurface1        (bool)
  17. TranslateSurface2        (bool)
  18. NormalCut                (bool)  -- sheet metal only
  19. UseFeatScope             (bool)
  20. UseAutoSelect            (bool)
  21. AssemblyFeatureScope     (bool)
  22. AutoSelectComponents     (bool)  -- MISSING in our earlier spikes
  23. PropagateFeatureToParts  (bool)  -- MISSING in our earlier spikes
  24. T0                       (int)   swStartConditions_e
  25. StartOffset              (double)
  26. FlipStartOffset          (bool)
  27. OptimizeGeometry         (bool)  -- MISSING in our earlier spikes (sheet metal only)

Earlier Spikes E, E2 used 24-arg form (missing args 22, 23, 27) which
explains the PARAMNOTOPTIONAL error -- pywin32 saw 3 required args with
nothing supplied.

Test: build box + circle sketch on top, call FeatureCut4 with 27 args,
BLIND end condition, 5mm depth. Verify a cut was produced.

Preconditions: blank Part open.
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
SW_START_SKETCH_PLANE = 0


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
        True,
        False,
        False,
        0,
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
        0,
        0.0,
        False,
    )
    if feat is None:
        raise RuntimeError("box None")
    feat.Name = "Box"


def _hole_sketch(doc, suffix: int) -> str:
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.0, 0.0, 0.005):
        raise RuntimeError("select top face")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    cx = -0.005 + (suffix * 0.003)
    sm.CreateCircle(cx, 0.0, 0.0, cx + 0.0015, 0.0, 0.0)  # Ø3mm
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    name = f"SK_H_{suffix}"
    sk.Name = name
    return name


def _cut27(end_cond, depth):
    """27-arg FeatureCut4. depth meaningful only for BLIND."""
    return [
        True,  # 1  Sd (single-ended)
        False,  # 2  Flip
        False,  # 3  Dir
        end_cond,  # 4  T1
        0,  # 5  T2
        depth,  # 6  D1
        0.0,  # 7  D2
        False,
        False,  # 8-9   Dchk1, Dchk2
        False,
        False,  # 10-11 Ddir1, Ddir2
        0.0,
        0.0,  # 12-13 Dang1, Dang2
        False,
        False,  # 14-15 OffsetReverse1/2
        False,
        False,  # 16-17 TranslateSurface1/2
        False,  # 18 NormalCut (sheet metal only)
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
        True,  # 21 AssemblyFeatureScope
        True,  # 22 AutoSelectComponents (NEW)
        False,  # 23 PropagateFeatureToParts (NEW)
        SW_START_SKETCH_PLANE,  # 24 T0
        0.0,  # 25 StartOffset
        False,  # 26 FlipStartOffset
        False,  # 27 OptimizeGeometry (NEW; sheet metal only)
    ]


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
        _build_box(doc)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"box: {e!r}"}))
        return 1

    fm = doc.FeatureManager
    results = []

    test_cases = [
        ("blind_5mm", SW_END_COND_BLIND, 0.005),
        ("through_all_d0", SW_END_COND_THROUGH_ALL, 0.0),
    ]

    for i, (label, end_cond, depth) in enumerate(test_cases):
        try:
            sk_name = _hole_sketch(doc, i)
        except Exception as e:
            results.append({"label": label, "ok": False, "error": f"sketch: {e!r}"})
            continue
        doc.ClearSelection2(True)
        if not doc.SelectByID(sk_name, "SKETCH", 0.0, 0.0, 0.0):
            results.append(
                {"label": label, "ok": False, "error": "select sketch failed"}
            )
            continue

        args = _cut27(end_cond, depth)
        assert len(args) == 27, f"expected 27 args, got {len(args)}"

        try:
            f = fm.FeatureCut4(*args)
            if f is None:
                results.append(
                    {
                        "label": label,
                        "ok": False,
                        "error": "FeatureCut4 returned None",
                        "args_n": 27,
                    }
                )
                continue
            try:
                ftype = str(f.GetTypeName)
            except Exception:
                ftype = "?"
            try:
                fname = str(f.Name)
            except Exception:
                fname = "?"
            results.append(
                {
                    "label": label,
                    "ok": True,
                    "feature_type": ftype,
                    "feature_name": fname,
                    "looks_like_cut": "Cut" in ftype,
                    "args_n": 27,
                }
            )
        except Exception as e:
            results.append(
                {"label": label, "ok": False, "error": repr(e), "args_n": 27}
            )

    cuts = [r for r in results if r.get("looks_like_cut")]
    print(
        json.dumps(
            {"results": results, "winning": [r["label"] for r in cuts]}, indent=2
        )
    )
    return 0 if cuts else 1


if __name__ == "__main__":
    sys.exit(main())
