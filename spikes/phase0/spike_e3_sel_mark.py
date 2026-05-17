"""
Spike E3 - try SelectByID2 with various Mark values before FeatureCut4.

Hypothesis: FeatureCut4 PARAMNOTOPTIONAL on this build may be because
the sketch needs to be selected with a specific selection Mark (not
the plain Mark=0 that plain SelectByID uses).

SelectByID2 signature:
  SelectByID2(name, type, x, y, z, Append, Mark, Callout, SelectOption)
  - Callout is the problematic interface arg
  - Try with Callout=None (Nothing in VBA). Late-binding may accept None
    even though arbitrary IDispatch args fail

Mark values worth trying for sketch selection -> cut:
  0  - default (no mark)
  1  - sketch contour
  4  - "primary" selection (some APIs)
  8  - "secondary" selection (often required for sweeps/lofts/cuts)

For each Mark value: build a fresh hole sketch, SelectByID2 with that
Mark, then try FeatureCut4 (24-arg, BLIND 5mm) and report.

Preconditions: blank Part with the box already built (or auto-build).
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
        0,
        0.0,
        False,
    )
    if feat is None:
        raise RuntimeError("FeatureExtrusion2 None")
    feat.Name = "Box"


def _fresh_hole_sketch(doc, suffix: int) -> str:
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


def _cut_args_blind_5mm():
    return [
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
        False,
        True,
        True,
        True,
        0,
        0.0,
        False,
    ]


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"ok": False, "error": "no active doc"}))
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
    ext = doc.Extension
    results = []

    marks = [0, 1, 2, 4, 8, 16, 32]
    for i, mark in enumerate(marks):
        try:
            sk_name = _fresh_hole_sketch(doc, i)
        except Exception as e:
            results.append(
                {"mark": mark, "step": "sketch", "ok": False, "error": repr(e)}
            )
            continue

        # Select via SelectByID2 with the test Mark, Callout=None
        doc.ClearSelection2(True)
        try:
            ok = ext.SelectByID2(sk_name, "SKETCH", 0.0, 0.0, 0.0, False, mark, None, 0)
        except Exception as e:
            results.append(
                {"mark": mark, "step": "select_by_id2", "ok": False, "error": repr(e)}
            )
            continue
        if not ok:
            results.append({"mark": mark, "step": "select_returned_False", "ok": False})
            continue

        try:
            f = fm.FeatureCut4(*_cut_args_blind_5mm())
            ok_cut = f is not None
            results.append(
                {"mark": mark, "step": "cut", "ok": ok_cut, "returned": ok_cut}
            )
            if ok_cut:
                try:
                    doc.EditUndo2(1)
                except Exception:
                    pass
        except Exception as e:
            results.append({"mark": mark, "step": "cut", "ok": False, "error": repr(e)})

    succ = [r for r in results if r.get("ok") and r.get("step") == "cut"]
    print(
        json.dumps(
            {
                "results": results,
                "winning_marks": [r["mark"] for r in succ],
            },
            indent=2,
        )
    )
    return 0 if succ else 1


if __name__ == "__main__":
    sys.exit(main())
