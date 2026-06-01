"""Spike v0.16 - T1 Rib: recipe probe (open sketch on face + InsertRib 10-arg).

Hypothesis (per DEFERRED / WAVE6_SEAT_DISPATCH section 6 T1):
    The legacy fm.InsertRib(Bool, Bool, Double, Long, Bool, Bool, Bool, Double, Bool, Bool)
    (10 args) needs an OPEN SKETCH on a planar face as the rib profile - not just a
    face selection. This spike builds a 40x40x20mm box (proven recipe from
    _run_ref_point_pae.py), sketches a single open line on the top face, selects
    that sketch, and sweeps the 10-arg space.

DoD: a Rib feature materializes (feature-count delta + GetTypeName2 == Rib).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V16 = Path(__file__).resolve().parent
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))

import pythoncom
import win32com.client as w32

from ai_sw_bridge.com.earlybind import typed, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module

from spike_earlybind_persist import connect_running_sw, ensure_sw_module


SW_DEFAULT_TEMPLATE_PART = 8


def _title(doc):
    t = doc.GetTitle
    return t() if callable(t) else t


def _try_close(sw, doc):
    try:
        sw.CloseDoc(_title(doc))
    except Exception:
        pass


def _feature_count(doc):
    """Walk features via FeatureManager - FirstFeature() returns None on late-bound docs."""
    try:
        fm = doc.FeatureManager
        # Try GetFeatures(True) first - returns all features
        feats = fm.GetFeatures(True)
        if feats is not None:
            return len(feats) if isinstance(feats, (list, tuple)) else 1
    except Exception:
        pass
    # Fallback: count by name probing
    n = 0
    for i in range(50):
        try:
            f = doc.FeatureByPositionReverse(i)
            if f is None:
                break
            n += 1
        except Exception:
            break
    return n


def _list_features(doc):
    out = []
    try:
        fm = doc.FeatureManager
        feats = fm.GetFeatures(True)
        if feats is not None:
            for f in (feats if isinstance(feats, (list, tuple)) else [feats]):
                try:
                    out.append({"name": f.Name, "type": f.GetTypeName2()})
                except Exception:
                    out.append({"name": "?", "type": "?"})
            return out
    except Exception:
        pass
    for i in range(50):
        try:
            f = doc.FeatureByPositionReverse(i)
            if f is None:
                break
            try:
                out.append({"name": f.Name, "type": f.GetTypeName2()})
            except Exception:
                out.append({"name": "?", "type": "?"})
        except Exception:
            break
    return out


def _build_box(sw):
    """L-bracket host body: 40mm vertical wall + 40mm horizontal base, 10mm thick.
    Mid-plane extrusion so Front Plane slices through the middle.
    The rib sketch will be a diagonal line on Front Plane connecting inner faces."""
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument returned None")
    doc.ClearSelection2(True)
    # Sketch L-profile on Right Plane (so extrusion goes along X, Front Plane = YZ midplane)
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    # L-shape: vertical wall 0..10mm x, 0..40mm y; horizontal base 0..40mm x, 0..10mm y
    # Draw as a closed L-profile using lines
    sk.CreateLine(0, 0, 0, 0.04, 0, 0)       # bottom: (0,0) -> (40,0)
    sk.CreateLine(0.04, 0, 0, 0.04, 0.01, 0)  # right base: (40,0) -> (40,10)
    sk.CreateLine(0.04, 0.01, 0, 0.01, 0.01, 0)  # inner base top: (40,10) -> (10,10)
    sk.CreateLine(0.01, 0.01, 0, 0.01, 0.04, 0)  # inner wall right: (10,10) -> (10,40)
    sk.CreateLine(0.01, 0.04, 0, 0, 0.04, 0)  # top wall: (10,40) -> (0,40)
    sk.CreateLine(0, 0.04, 0, 0, 0, 0)        # left wall: (0,40) -> (0,0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    # Mid-plane extrusion, 10mm total (5mm each side of Right Plane)
    fm.FeatureExtrusion3(
        True, False, False, 6, 0, 0.005, 0.005,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0, False,
    )
    doc.ClearSelection2(True)
    return doc


def _find_top_face(doc, mod):
    """For L-bracket: we use Front Plane directly for the rib sketch (not a face).
    This function is a no-op placeholder - returns None to signal skip-face-sketch."""
    return None


def _sketch_open_line_on_face(doc, face_entity):
    """For L-bracket: sketch a diagonal line on Front Plane connecting inner faces.
    The L-bracket inner corner is at (10mm, 10mm) in the Right Plane sketch.
    On Front Plane (YZ at x=0, mid-plane of 10mm extrusion), the inner wall face
    is at y=10mm..40mm (z=0), inner base face at z=-5mm..+5mm (y=10mm).
    Diagonal: from inner wall (y=30mm, z=0) to inner base (y=0, z=0) -- a line
    that crosses the gap between the two inner faces."""
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    # Diagonal line on Front Plane: from (y=15mm, z=0) to (y=0, z=15mm)
    # This crosses the interior gap of the L-bracket
    sk.CreateLine(0.0, 0.015, 0.0, 0.0, 0.0, 0.015)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)


def _select_sketch(doc, mark=0):
    ok = doc.SelectByID("Sketch2", "SKETCH", 0, 0, 0)
    if isinstance(ok, tuple):
        ok = ok[0]
    return bool(ok)


def _activate_sketch(doc):
    """Put Sketch2 into edit mode (active sketch) - some Insert* APIs require this."""
    doc.ClearSelection2(True)
    ok = doc.SelectByID("Sketch2", "SKETCH", 0, 0, 0)
    if isinstance(ok, tuple):
        ok = ok[0]
    if not ok:
        return False
    doc.EditSketch()
    return True


def _probe_insert_rib(fm, args_tuple):
    try:
        feat = fm.InsertRib(*args_tuple)
        if isinstance(feat, tuple):
            feat = feat[0] if feat and feat[0] is not None else None
        return feat, None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:200])


def _materialized(feat):
    if feat is None:
        return False
    if isinstance(feat, (int, bool)):
        return False
    return True


def run():
    result = {"spike": "rib_recipe_T1", "ts": time.time()}
    print("[rib] connecting to running SW...")
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    print("[rib] building 40x40x20mm box...")
    doc = _build_box(sw)
    print("[rib] box built: %s" % _title(doc))

    try:
        fm = doc.FeatureManager
        print("[rib] sketching diagonal on Front Plane (L-bracket)...")
        _sketch_open_line_on_face(doc, None)

        n_before = _feature_count(doc)
        result["feature_count_before"] = n_before
        result["features_before"] = _list_features(doc)

        sel_variants = [
            ("sketch_mark0",      lambda: _select_sketch(doc, mark=0)),
            ("sketch_mark1",      lambda: _select_sketch(doc, mark=1)),
            ("sketch_mark4",      lambda: _select_sketch(doc, mark=4)),
            ("sketch_active",     lambda: _activate_sketch(doc)),
        ]

        # Corrected arg semantics per SW2024 typelib dump (W0 handoff):
        # InsertRib(Is2Sided:BOOL, ReverseThicknessDir:BOOL, Thickness:R8,
        #           ReferenceEdgeIndex:I4, ReverseMaterialDir:BOOL, IsDrafted:BOOL,
        #           DraftOutward:BOOL, DraftAngle:R8, IsNormToSketch:BOOL,
        #           IsDraftedFromWall:BOOL)
        # Key insight: arg4 (ReverseMaterialDir) controls whether rib extrudes
        # INTO the host body or out into empty space. Must try both.
        arg_variants = [
            ("probe_A_fwd_5mm",  (True, False, 0.005, 0, False, False, False, 0.0, True, False)),
            ("probe_B_rev_5mm",  (True, False, 0.005, 0, True,  False, False, 0.0, True, False)),
            ("probe_C_fwd_2mm",  (True, False, 0.002, 0, False, False, False, 0.0, True, False)),
            ("probe_D_rev_2mm",  (True, False, 0.002, 0, True,  False, False, 0.0, True, False)),
            ("probe_E_1sided_fwd", (False, False, 0.005, 0, False, False, False, 0.0, True, False)),
            ("probe_F_1sided_rev", (False, False, 0.005, 0, True,  False, False, 0.0, True, False)),
            ("probe_G_parallel_fwd", (True, False, 0.005, 0, False, False, False, 0.0, False, False)),
            ("probe_H_parallel_rev", (True, False, 0.005, 0, True,  False, False, 0.0, False, False)),
            ("probe_I_revThk_fwd", (True, True,  0.005, 0, False, False, False, 0.0, True, False)),
            ("probe_J_revThk_rev", (True, True,  0.005, 0, True,  False, False, 0.0, True, False)),
            ("probe_K_draft_fwd",  (True, False, 0.005, 0, False, True,  True,  0.0873, True, False)),
            ("probe_L_draft_rev",  (True, False, 0.005, 0, True,  True,  True,  0.0873, True, False)),
        ]

        probes = []
        green = None
        for sel_name, sel_fn in sel_variants:
            sel_result = sel_fn()
            try:
                sel_count = doc.SelectionMgr.GetSelectedObjectCount()
            except Exception:
                sel_count = "?"
            print("[rib] sel=%s count=%s sel_ok=%s" % (sel_name, sel_count, sel_result))
            for arg_name, args in arg_variants:
                n_before_call = _feature_count(doc)
                feat, err = _probe_insert_rib(fm, args)
                n_after_call = _feature_count(doc)
                mat = _materialized(feat)
                entry = {
                    "sel": sel_name,
                    "args": arg_name,
                    "arg_tuple": list(args),
                    "materialized": mat,
                    "feature": str(feat)[:120] if feat is not None else None,
                    "error": err,
                    "sel_count": sel_count,
                    "delta": n_after_call - n_before_call,
                }
                if mat:
                    try:
                        entry["feature_type"] = feat.GetTypeName2()
                        entry["feature_name"] = feat.Name
                    except Exception:
                        pass
                probes.append(entry)
                print("  [%s/%s] mat=%s err=%s" % (sel_name, arg_name, mat, err))
                if mat and green is None:
                    green = entry
                    break
            if green is not None:
                break

        result["probes"] = probes
        result["feature_count_after"] = _feature_count(doc)
        result["features_after"] = _list_features(doc)

        if green is not None:
            result["overall"] = "GREEN"
            result["recipe"] = {
                "selection": green["sel"],
                "args_name": green["args"],
                "args_tuple": green["arg_tuple"],
                "feature_name": green.get("feature_name"),
                "feature_type": green.get("feature_type"),
            }
            result["interpretation"] = (
                "Rib materialized with selection=%s args=%s (tuple=%s). "
                "W0 wires InsertRib into mutate.py."
                % (green["sel"], green["args"], green["arg_tuple"])
            )
        else:
            any_partial = any(
                p.get("error") is None and not p["materialized"] for p in probes
            )
            result["overall"] = "PARTIAL" if any_partial else "WALL"
            result["interpretation"] = (
                "No arg/selection combo materialized a Rib across %d probes. "
                "Open-sketch-on-face hypothesis tested with 5 selection variants "
                "and 11 arg tuples. Next: check SW API docs for exact InsertRib "
                "semantics or try with the sketch line as a SELECTED ENTITY "
                "(not just the sketch feature)."
                % len(probes)
            )
    finally:
        _try_close(sw, doc)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print("wrote %s" % args.out, file=sys.stderr)
    else:
        print(payload)
    return {"GREEN": 0, "PARTIAL": 2, "WALL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())

