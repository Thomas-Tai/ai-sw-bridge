"""Spike v0.16 - T3 Wrap: recipe probe (sketch-on-face + InsertWrapFeature2 5-arg).

Hypothesis: InsertWrapFeature2 needs a CLOSED sketch on the target face
(the wrap source) plus the face selected. Args: (wrapType, thickness,
reverse, draftAngle, draftType). wrapType: 0=emboss, 1=deboss, 2=scribe.
Materialization via len(GetFeatures(True)) delta.
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
        feats = doc.FeatureManager.GetFeatures(True)
        return len(feats) if feats else 0
    except Exception:
        return 0


def _list_features(doc):
    out = []
    mod = wrapper_module()
    try:
        feats = doc.FeatureManager.GetFeatures(True)
        if feats:
            for f in feats:
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    out.append({"name": ifeat.Name, "type": ifeat.GetTypeName2()})
                except Exception:
                    out.append({"name": "?", "type": "?"})
    except Exception:
        pass
    return out


def _build_box(sw):
    """50x50x50mm blind extrusion from Front Plane."""
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
        0,
        0,
        0.05,
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
        0,
        False,
    )
    doc.ClearSelection2(True)
    return doc


def _sketch_closed_on_face(doc, face_entity, mod):
    """Enter sketch on the given face and draw a small closed rectangle."""
    doc.ClearSelection2(True)
    try:
        ient = typed(face_entity, "IEntity", module=mod)
        ok = ient.Select2(False, 0)
    except Exception:
        ok = face_entity.Select2(False, 0)
    if not ok:
        raise RuntimeError("face Select2 returned False")
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    # Small closed rectangle centered on face, 10x10mm
    sk.CreateCornerRectangle(-0.005, -0.005, 0, 0.005, 0.005, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)


def _get_first_face(doc, mod):
    """Get the first body face via persist round-trip."""
    bodies = doc.GetBodies2(0, True)
    if not bodies:
        raise RuntimeError("no bodies")
    body = bodies[0] if isinstance(bodies, (list, tuple)) else bodies
    faces = body.GetFaces()
    if not faces:
        raise RuntimeError("no faces")
    ext = typed_extension(doc, module=mod)
    f = faces[0]
    pid = ext.GetPersistReference3(f)
    if pid is None:
        raise RuntimeError("no persist ref")
    obj = ext.GetObjectByPersistReference3(pid)
    return obj[0] if isinstance(obj, tuple) else obj


def run():
    result = {"spike": "wrap_recipe_T3", "ts": time.time()}
    print("[wrap] connecting...")
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    print("[wrap] building 50x50x50mm box...")
    doc = _build_box(sw)
    print("[wrap] box built: %s" % _title(doc))

    try:
        fm = doc.FeatureManager
        face = _get_first_face(doc, mod)
        print("[wrap] face acquired: %s" % type(face).__name__)

        print("[wrap] sketching closed rect on face...")
        _sketch_closed_on_face(doc, face, mod)

        n_before = _feature_count(doc)
        result["feature_count_before"] = n_before
        result["features_before"] = _list_features(doc)

        # Selection variants
        sel_variants = [
            ("sketch_only", lambda: doc.SelectByID("Sketch2", "SKETCH", 0, 0, 0)),
            (
                "sketch_then_face",
                lambda: (
                    doc.SelectByID("Sketch2", "SKETCH", 0, 0, 0)
                    and typed(face, "IEntity", module=mod).Select2(True, 0)
                ),
            ),
            (
                "face_then_sketch",
                lambda: (
                    typed(face, "IEntity", module=mod).Select2(False, 0)
                    and doc.SelectByID("Sketch2", "SKETCH", 0, 0, 0)
                ),
            ),
        ]

        # InsertWrapFeature2(wrapType, thickness, reverse, draftAngle, draftType)
        # wrapType: 0=emboss, 1=deboss, 2=scribe
        arg_variants = [
            ("emboss_1mm", (0, 0.001, False, 0.0, 0)),
            ("deboss_1mm", (1, 0.001, False, 0.0, 0)),
            ("scribe_1mm", (2, 0.001, False, 0.0, 0)),
            ("emboss_2mm", (0, 0.002, False, 0.0, 0)),
            ("emboss_rev", (0, 0.001, True, 0.0, 0)),
            ("deboss_rev", (1, 0.001, True, 0.0, 0)),
        ]

        probes = []
        green = None
        for sel_name, sel_fn in sel_variants:
            doc.ClearSelection2(True)
            sel_ok = sel_fn()
            print("[wrap] sel=%s ok=%s" % (sel_name, sel_ok))
            for arg_name, args in arg_variants:
                n_before_call = _feature_count(doc)
                try:
                    feat = fm.InsertWrapFeature2(*args)
                    err = None
                except Exception as e:
                    feat = None
                    err = "%s: %s" % (type(e).__name__, str(e)[:200])
                n_after_call = _feature_count(doc)
                delta = n_after_call - n_before_call
                mat = delta > 0
                entry = {
                    "sel": sel_name,
                    "args": arg_name,
                    "arg_tuple": list(args),
                    "delta": delta,
                    "materialized": mat,
                    "return_value": str(feat)[:120] if feat else "None",
                    "error": err,
                }
                if mat:
                    for f in _list_features(doc):
                        if "Wrap" in f.get("type", "") or "Wrap" in f.get("name", ""):
                            entry["feature_name"] = f["name"]
                            entry["feature_type"] = f["type"]
                            break
                probes.append(entry)
                print(
                    "  [%s/%s] delta=%d mat=%s err=%s"
                    % (sel_name, arg_name, delta, mat, err)
                )
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
                "Wrap materialized with sel=%s args=%s (tuple=%s). "
                "W0 wires InsertWrapFeature2 into mutate.py."
                % (green["sel"], green["args"], green["arg_tuple"])
            )
        else:
            result["overall"] = "WALL"
            result["interpretation"] = (
                "No sel/arg combo materialized a Wrap across %d probes. "
                "Closed sketch on face + InsertWrapFeature2 tested." % len(probes)
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
