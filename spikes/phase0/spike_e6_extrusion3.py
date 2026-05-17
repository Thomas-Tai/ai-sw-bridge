"""
Spike E6 - try FeatureExtrusion3 for cut operations.

Per SW API: FeatureExtrusion3 is the modern combined boss/cut method.
Operation type is controlled by parameters (Sd direction, Flip), not by
which method is called. If this exists on SW 2024 SP1 AND it accepts
pywin32 late-binding calls, we have a cuts path.

Test:
1. Build box.
2. Sketch circle on top face.
3. Call FeatureExtrusion3 with cut-intent params.
4. Verify result is a cut, not a boss.

The FeatureExtrusion3 signature (per SW 2024 docs):
  FeatureExtrusion3(
    Sd, Flip, Dir, T1, T2, D1, D2,
    Dchk1, Dchk2, Ddir1, Ddir2,
    Dang1, Dang2,
    OffsetReverse1, OffsetReverse2,
    TranslateSurface1, TranslateSurface2,
    Merge, UseFeatScope, UseAutoSelect, AssemblyFeatureScope,
    T0, StartOffset, FlipStartOffset, FlipSideToCut, BothDirectionsAsymmetric
  )
= 26 args. The new args (FlipSideToCut, BothDirectionsAsymmetric) at
the end may be what's needed for cut behavior.
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
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
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
    cx = -0.005 + (suffix * 0.002)
    sm.CreateCircle(cx, 0.0, 0.0, cx + 0.0015, 0.0, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    name = f"SK_H_{suffix}"
    sk.Name = name
    return name


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

    # 26-arg FeatureExtrusion3 with various cut-intent params
    # (label, Sd, Flip, T1, D1, Merge, FlipSideToCut)
    variants = [
        ("E3_blind_flip_True_FSC_True", True, True, 0, 0.005, True, True),
        ("E3_blind_flip_True_FSC_False", True, True, 0, 0.005, True, False),
        ("E3_blind_flip_False_FSC_True", True, False, 0, 0.005, True, True),
        ("E3_through_all_FSC_True", True, True, 4, 0.0, True, True),
    ]

    # Try multiple arg counts since 26 was wrong.
    # Build base 24-arg form (no FSC, no BothDirs) and add extras as needed.
    arg_counts_to_try = [24, 25, 26, 27, 28]

    for i, (label, sd, flip, t1, d1, merge, fsc) in enumerate(variants):
        try:
            sk = _hole_sketch(doc, i)
        except Exception as e:
            results.append({"label": label, "ok": False, "error": f"sketch: {e!r}"})
            continue
        doc.ClearSelection2(True)
        doc.SelectByID(sk, "SKETCH", 0.0, 0.0, 0.0)

        # Try just this variant's params at each arg count
        base_args = [
            sd,
            flip,
            False,
            t1,
            0,
            d1,
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
        ]
        # then merge + UseFeatScope + UseAutoSelect + AssemblyFeatureScope
        # + T0 + StartOffset + FlipStartOffset = 24 args total
        tail24 = [merge, True, True, True, 0, 0.0, False]
        tail25 = tail24 + [fsc]
        tail26 = tail24 + [fsc, False]
        tail27 = tail24 + [fsc, False, False]
        tail28 = tail24 + [fsc, False, False, False]

        tails = {24: tail24, 25: tail25, 26: tail26, 27: tail27, 28: tail28}

        result_for_label = None
        for arg_count in arg_counts_to_try:
            args = base_args + tails[arg_count]
            assert len(args) == arg_count
            try:
                f = fm.FeatureExtrusion3(*args)
                if f is None:
                    continue
                # got one
                try:
                    ftype = str(f.GetTypeName)
                except Exception:
                    ftype = "?"
                try:
                    fname = str(f.Name)
                except Exception:
                    fname = "?"
                result_for_label = {
                    "label": label,
                    "ok": True,
                    "args_n": arg_count,
                    "feature_type": ftype,
                    "feature_name": fname,
                    "looks_like_cut": "Cut" in ftype,
                }
                try:
                    doc.EditUndo2(1)
                except Exception:
                    pass
                break
            except Exception as e:
                # try next arg count
                continue

        if result_for_label is None:
            results.append(
                {"label": label, "ok": False, "error": "no arg count worked"}
            )
        else:
            results.append(result_for_label)

    cuts = [r for r in results if r.get("looks_like_cut")]
    bosses = [r for r in results if r.get("ok") and not r.get("looks_like_cut")]
    print(
        json.dumps(
            {
                "results": results,
                "cuts_count": len(cuts),
                "bosses_count": len(bosses),
                "winning_labels": [r["label"] for r in cuts],
            },
            indent=2,
        )
    )
    return 0 if cuts else 1


if __name__ == "__main__":
    sys.exit(main())
