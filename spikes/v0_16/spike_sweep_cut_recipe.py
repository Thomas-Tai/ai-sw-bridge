"""Spike v0.16 - T4 Sweep-Cut: recipe probe with delta detection.

swFmSweepCut=18, CreateDefinition(18) -> typed_qi(ISweepFeatureData) -> CreateFeature.
Key geometry: profile circle on a plane that intersects the solid block,
path line on a different plane that pierces through the solid.
Materialization via feature-count delta (never trust return value).
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

from ai_sw_bridge.com.earlybind import typed, typed_qi
from ai_sw_bridge.com.sw_type_info import wrapper_module

from spike_earlybind_persist import connect_running_sw, ensure_sw_module

SW_DEFAULT_TEMPLATE_PART = 8
_SW_FM_SWEEP_CUT = 18


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


def _build_harness(sw):
    """Solid block + profile circle + path line that pierces the block.

    Block: 50x50x50mm blind extrusion from Front Plane (+Y direction in SW).
    Profile: small circle (r=3mm) on Right Plane at the block center.
    Path: line on Top Plane from outside the block through the center to the other side.
    """
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument returned None")

    # 1. Solid block: 50x50mm square on Front Plane, extruded 50mm blind
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

    # 2. Profile: small circle on Right Plane at origin
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCircle(0, 0, 0, 0.003, 0, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)

    # 3. Path: line on Top Plane that pierces through the block
    doc.SelectByID("Top Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateLine(-0.04, 0, 0, 0.04, 0, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)

    doc.ForceRebuild3(False)
    return doc


def run():
    result = {"spike": "sweep_cut_recipe_T4", "ts": time.time()}
    print("[swcut] connecting...")
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))

    sw = connect_running_sw()
    print("[swcut] building harness (block + profile + path)...")
    doc = _build_harness(sw)
    print("[swcut] harness built: %s" % _title(doc))

    try:
        fm = doc.FeatureManager
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)

        n_before = _feature_count(doc)
        result["feature_count_before"] = n_before
        result["features_before"] = _list_features(doc)

        # Verify CreateDefinition(18) returns non-null
        try:
            data = fm.CreateDefinition(_SW_FM_SWEEP_CUT)
            result["create_def"] = (
                "non-null" if data and not isinstance(data, (int, bool)) else "null/int"
            )
            print("[swcut] CreateDefinition(18): %s" % result["create_def"])
        except Exception as e:
            result["create_def"] = "error: %s" % str(e)[:100]
            print("[swcut] CreateDefinition(18) error: %s" % e)

        # Geometry variants: different profile/path combinations
        geo_variants = [
            ("profile2_path3", "Sketch2", "Sketch3"),
            ("profile3_path2", "Sketch3", "Sketch2"),
        ]

        probes = []
        green = None
        for geo_name, profile, path in geo_variants:
            doc.ClearSelection2(True)
            # Select profile (mark=1) then path (mark=4, append)
            sel_p = ext.SelectByID2(profile, "SKETCH", 0, 0, 0, False, 1, None, 0)
            sel_path = ext.SelectByID2(path, "SKETCH", 0, 0, 0, True, 4, None, 0)
            print(
                "[swcut] %s: profile_sel=%s path_sel=%s" % (geo_name, sel_p, sel_path)
            )

            n_before_call = _feature_count(doc)
            try:
                data = fm.CreateDefinition(_SW_FM_SWEEP_CUT)
                fd = typed_qi(data, "ISweepFeatureData", module=mod)
                feat = fm.CreateFeature(fd)
                err = None
            except Exception as e:
                feat = None
                err = "%s: %s" % (type(e).__name__, str(e)[:200])
            n_after_call = _feature_count(doc)
            delta = n_after_call - n_before_call
            mat = delta > 0
            entry = {
                "geo": geo_name,
                "profile": profile,
                "path": path,
                "delta": delta,
                "materialized": mat,
                "return_value": str(feat)[:120] if feat else "None",
                "error": err,
            }
            if mat:
                # Find the new feature
                for f in _list_features(doc):
                    if "Sweep" in f.get("type", "") or "Sweep" in f.get("name", ""):
                        entry["feature_name"] = f["name"]
                        entry["feature_type"] = f["type"]
                        break
            probes.append(entry)
            print("  [%s] delta=%d mat=%s err=%s" % (geo_name, delta, mat, err))
            if mat and green is None:
                green = entry

        result["probes"] = probes
        result["feature_count_after"] = _feature_count(doc)
        result["features_after"] = _list_features(doc)

        if green is not None:
            result["overall"] = "GREEN"
            result["recipe"] = {
                "profile": green["profile"],
                "path": green["path"],
                "feature_name": green.get("feature_name"),
                "feature_type": green.get("feature_type"),
            }
            result["interpretation"] = (
                "Sweep-cut materialized with profile=%s path=%s. "
                "W0 wires _create_sweep_cut with delta detection."
                % (green["profile"], green["path"])
            )
        else:
            result["overall"] = "WALL"
            result["interpretation"] = (
                "No geometry variant materialized a sweep-cut. "
                "Delta=0 on all probes. Geometry constraint persists."
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
