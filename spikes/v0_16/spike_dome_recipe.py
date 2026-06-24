"""Spike v0.16 - T2 Dome: recipe probe (face select + InsertDome 3-arg).

InsertDome(Height:R8, ReverseDir:BOOL, DoEllipticSurface:BOOL) on IModelDoc2.
Builds 50x50x50mm box, selects top face via persist round-trip, probes 4 arg combos.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parent
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
    try:
        fm = doc.FeatureManager
        feats = fm.GetFeatures(True)
        if feats is not None:
            return len(feats) if isinstance(feats, (list, tuple)) else 1
    except Exception:
        pass
    return 0


def _list_features(doc):
    out = []
    try:
        fm = doc.FeatureManager
        feats = fm.GetFeatures(True)
        if feats:
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=wrapper_module())
                    out.append({"name": ifeat.Name, "type": ifeat.GetTypeName2()})
                except Exception:
                    out.append({"name": "?", "type": "?"})
    except Exception:
        pass
    return out


def _build_box(sw):
    """50x50x50 mm box on Front Plane."""
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument returned None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(
        True,
        False,
        False,
        6,
        0,
        0.025,
        0.025,
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
        0,
        False,
    )
    doc.ClearSelection2(True)
    return doc


def _find_top_face(doc, mod):
    """Pick the top planar face (z-max) of the box via persist round-trip."""
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        raise RuntimeError("no bodies")
    body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    faces = body.GetFaces()
    if not faces:
        raise RuntimeError("no faces")
    ext = typed_extension(doc, module=mod)
    best = None
    best_z = -1e30
    for f in faces:
        try:
            pid = ext.GetPersistReference3(f)
            if pid is None:
                continue
            obj = ext.GetObjectByPersistReference3(pid)
            live = obj[0] if isinstance(obj, tuple) else obj
            iface = typed(live, "IFace2", module=mod)
            try:
                uv = iface.GetFaceUVBounds()
                mid_u = (uv[0] + uv[2]) / 2.0
                mid_v = (uv[1] + uv[3]) / 2.0
            except Exception:
                mid_u, mid_v = 0.0, 0.0
            try:
                eval_out = iface.Evaluate(mid_u, mid_v)
                if eval_out is not None and len(eval_out) >= 3:
                    z = eval_out[2]
                    if z > best_z:
                        best_z = z
                        best = live
            except Exception:
                if best is None:
                    best = live
        except Exception:
            continue
    if best is None:
        raise RuntimeError("no usable face")
    return best


def run():
    result = {"spike": "dome_recipe_T2", "ts": time.time()}
    print("[dome] connecting...")
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    print("[dome] building 50x50x50mm box...")
    doc = _build_box(sw)
    print("[dome] box built: %s" % _title(doc))

    try:
        print("[dome] locating top face...")
        face = _find_top_face(doc, mod)
        print("[dome] face acquired: %s" % type(face).__name__)

        n_before = _feature_count(doc)
        result["feature_count_before"] = n_before
        result["features_before"] = _list_features(doc)

        # Select face with mark=1 (InsertDome requires mark=1 per seat probe)
        ient = typed(face, "IEntity", module=mod)
        sel_ok = ient.Select2(False, 1)
        result["face_select2"] = sel_ok
        print("[dome] face Select2: %s" % sel_ok)

        # InsertDome(Height, ReverseDir, DoEllipticSurface) on IModelDoc2
        arg_variants = [
            ("v1_fwd_round", (0.01, False, False)),
            ("v2_rev_round", (0.01, True, False)),
            ("v3_fwd_ellip", (0.01, False, True)),
            ("v4_rev_ellip", (0.01, True, True)),
            ("v5_tall_fwd", (0.02, False, False)),
            ("v6_short_fwd", (0.005, False, False)),
        ]

        probes = []
        green = None
        for arg_name, args in arg_variants:
            # Re-select face with mark=1 before each attempt
            doc.ClearSelection2(True)
            ient.Select2(False, 1)
            n_before_call = _feature_count(doc)
            try:
                feat = doc.InsertDome(*args)
                if isinstance(feat, tuple):
                    feat = feat[0] if feat and feat[0] is not None else None
                err = None
            except Exception as e:
                feat = None
                err = "%s: %s" % (type(e).__name__, str(e)[:200])
            n_after_call = _feature_count(doc)
            mat = (n_after_call - n_before_call) > 0
            entry = {
                "args": arg_name,
                "arg_tuple": list(args),
                "materialized": mat,
                "feature": str(feat)[:120] if feat else None,
                "error": err,
                "delta": n_after_call - n_before_call,
            }
            if mat:
                try:
                    ifeat = typed(feat, "IFeature", module=mod)
                    entry["feature_type"] = ifeat.GetTypeName2()
                    entry["feature_name"] = ifeat.Name
                except Exception:
                    pass
            probes.append(entry)
            print(
                "  [%s] mat=%s delta=%d err=%s" % (arg_name, mat, entry["delta"], err)
            )
            if mat and green is None:
                green = entry
                break

        result["probes"] = probes
        result["feature_count_after"] = _feature_count(doc)
        result["features_after"] = _list_features(doc)

        if green is not None:
            result["overall"] = "GREEN"
            result["recipe"] = {
                "args_name": green["args"],
                "args_tuple": green["arg_tuple"],
                "feature_name": green.get("feature_name"),
                "feature_type": green.get("feature_type"),
            }
            result["interpretation"] = (
                "Dome materialized with args=%s (tuple=%s). "
                "W0 wires InsertDome into mutate.py."
                % (green["args"], green["arg_tuple"])
            )
        else:
            any_no_err = any(p.get("error") is None for p in probes)
            result["overall"] = "PARTIAL" if any_no_err else "WALL"
            result["interpretation"] = (
                "No arg combo materialized a Dome across %d probes. "
                "Face selection achieved. InsertDome returns None silently."
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
    return {"GREEN": 0, "PARTIAL": 2, "WALL": 2, "FAIL": 1}.get(
        result.get("overall"), 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
