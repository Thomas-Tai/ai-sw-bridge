"""
Spike E2 - Spike E ruled out arg-count (all of 23,24,25,26 hit
PARAMNOTOPTIONAL). The issue is in arg *values* or *types*, not count.

This spike fixes the arg count at 24 (the documented form) and varies:
  - End condition: BLIND vs THROUGH_ALL vs THROUGH_NEXT
  - Depth: 0.001 vs 0.0 vs 0.010
  - Sd (single direction): True vs False

It also tries FeatureManager.FeatureCut (no 4 suffix) and FeatureCut3 in
case SW 2024 SP1 prefers the older signature.

Preconditions: blank Part open. Spike auto-builds the box + creates one
hole sketch per attempt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


SW_END_COND_BLIND = 0
SW_END_COND_THROUGH = 1        # alternative name for THROUGH_NEXT
SW_END_COND_THROUGH_NEXT = 2
SW_END_COND_THROUGH_ALL = 4    # documented value


def _build_box(doc):
    doc.ClearSelection2(True)
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("select Front Plane")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(-0.010, -0.010, 0.0, 0.010, 0.010, 0.0)
    # Skip dims -- we just need a closed sketch for the box extrude
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Box"
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Box", "SKETCH", 0.0, 0.0, 0.0)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True, False, False,
        SW_END_COND_BLIND, 0,
        0.005, 0.0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False,
        True, True, True,
        0, 0.0, False,
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


def _try_cut(doc, fm, method_name: str, args: list, label: str) -> dict:
    """Call a cut method by name with given args. Returns result dict."""
    try:
        method = getattr(fm, method_name)
    except Exception as e:
        return {"label": label, "method": method_name, "args_n": len(args),
                "ok": False, "error": f"no method: {e!r}"}
    try:
        f = method(*args)
        ok = f is not None
        return {"label": label, "method": method_name, "args_n": len(args),
                "ok": ok, "returned_feature": ok}
    except Exception as e:
        return {"label": label, "method": method_name, "args_n": len(args),
                "ok": False, "error": repr(e)}


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"ok": False, "error": "no active doc"}))
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

    fm = doc.FeatureManager
    results = []

    # 24-arg template -- this is the documented SW 2024 signature
    def args24(end_cond, depth, sd):
        return [
            sd,             # 1  Sd
            False,          # 2  Flip
            False,          # 3  Dir
            end_cond,       # 4  T1
            0,              # 5  T2
            depth,          # 6  D1
            0.0,            # 7  D2
            False, False, False, False,   # 8-11 Dchk1/2 Ddir1/2
            0.0, 0.0,                     # 12-13 Dang1/2
            False, False, False, False,   # 14-17 OffsetReverse1/2, TranslateSurface1/2
            False,                        # 18 NormalCut
            True, True, True,             # 19-21 UseFeatScope, UseAutoSelect, AssemblyFeatureScope
            0, 0.0, False,                # 22-24 T0, StartOffset, FlipStartOffset
        ]

    # 23-arg template (FeatureCut3 style)
    def args23(end_cond, depth, sd):
        return [
            sd, False, False,
            end_cond, 0,
            depth, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0.0, False,
        ]

    # Each test: fresh sketch, select, try cut
    test_cases = [
        ("FeatureCut4_blind_5mm_Sd_True",   "FeatureCut4", args24(SW_END_COND_BLIND, 0.005, True)),
        ("FeatureCut4_blind_5mm_Sd_False",  "FeatureCut4", args24(SW_END_COND_BLIND, 0.005, False)),
        ("FeatureCut4_through_all_d0",      "FeatureCut4", args24(SW_END_COND_THROUGH_ALL, 0.0, True)),
        ("FeatureCut4_through_next_d0",     "FeatureCut4", args24(SW_END_COND_THROUGH_NEXT, 0.0, True)),
        ("FeatureCut3_23args_blind",        "FeatureCut3", args23(SW_END_COND_BLIND, 0.005, True)),
        ("FeatureCut_legacy_blind",         "FeatureCut",  args23(SW_END_COND_BLIND, 0.005, True)),
    ]

    for i, (label, method, args) in enumerate(test_cases):
        try:
            sk_name = _fresh_hole_sketch(doc, i)
        except Exception as e:
            results.append({"label": label, "ok": False,
                            "error": f"sketch setup: {e!r}"})
            continue
        doc.ClearSelection2(True)
        if not doc.SelectByID(sk_name, "SKETCH", 0.0, 0.0, 0.0):
            results.append({"label": label, "ok": False,
                            "error": f"select {sk_name} failed"})
            continue

        r = _try_cut(doc, fm, method, args, label)
        results.append(r)
        if r.get("ok") and r.get("returned_feature"):
            try:
                doc.EditUndo2(1)
            except Exception:
                pass

    succ = [r for r in results if r.get("ok")]
    print(json.dumps({
        "results": results,
        "succeeded": [r["label"] for r in succ],
    }, indent=2))
    return 0 if succ else 1


if __name__ == "__main__":
    sys.exit(main())
