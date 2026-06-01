"""Gold-standard PAE for dome (InsertDome via _create_dome handler)."""
import os, sys, json, time, tempfile, traceback
import pythoncom
import win32com.client
WT = os.path.join("C:" + os.sep, "D", "WorkSpace", "[Local]_Station", "01_Heavy_Assets", "aisw-W6")
sys.path.insert(0, os.path.join(WT, "src"))
RESULTS_DIR = os.path.join(WT, "spikes", "v0_16", "_results")
# PART_TEMPLATE resolved at runtime via sw.GetUserPreferenceStringValue(8)

from ai_sw_bridge.mutate import _create_dome
from ai_sw_bridge.com.sw_type_info import wrapper_module

def _get_sw():
    pythoncom.CoInitialize()
    return win32com.client.GetActiveObject("SldWorks.Application")

def _title(doc):
    t = doc.GetTitle
    return t() if callable(t) else t

def _feature_count(doc):
    try:
        fm = doc.FeatureManager
        feats = fm.GetFeatures(True)
        return len(feats) if feats else 0
    except Exception:
        return 0

def _build_box(sw, path):
    """50x50x50mm blind extrusion from Front Plane."""
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None: raise RuntimeError("NewDocument None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(True, False, False, 0, 0, 0.05, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0, False)
    doc.ClearSelection2(True)
    doc.SaveAs3(path, 0, 2)
    try: sw.CloseDoc(_title(doc))
    except Exception: pass

def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    part_path = os.path.join(tempfile.gettempdir(), "dome_pae_%d.SLDPRT" % int(time.time()))
    print("[pae] creating box -> %s" % part_path)
    sw = _get_sw()
    # Build box directly (no save/reopen - fingerprint matching works on fresh docs)
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        print("[pae] FAIL: NewDocument None")
        return 1
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.025, -0.025, 0, 0.025, 0.025, 0)
    doc.InsertSketch2(False)
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    fm = doc.FeatureManager
    fm.FeatureExtrusion3(True, False, False, 0, 0, 0.05, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0, False)
    doc.ClearSelection2(True)
    doc.ForceRebuild3(False)
    print("[pae] box built directly: %s" % _title(doc))

    # face_ref for the top face of a 50x50x50 blind extrusion from Front Plane:
    # Top face is at z=0.05, normal pointing +Z
    face_ref = {
        "normal": [0.0, 0.0, 1.0],
        "centroid": [0.0, 0.0, 0.05],
        "area_mm2": 2500.0,
        "role_hint": "top_face"
    }
    feature = {"type": "dome", "distance_mm": 10.0}
    target = {"face_ref": face_ref}

    n_before = _feature_count(doc)
    print("[pae] features before: %d" % n_before)
    print("[pae] calling _create_dome...")
    result = {}
    try:
        ok, err = _create_dome(doc, feature, target)
        result["ok"] = ok
        result["error"] = err
    except Exception:
        result["ok"] = False
        result["error"] = traceback.format_exc()

    n_after = _feature_count(doc)
    result["feature_count_before"] = n_before
    result["feature_count_after"] = n_after
    result["delta"] = n_after - n_before
    print("[pae] ok=%s error=%s" % (result.get("ok"), result.get("error")))
    print("[pae] features after: %d (delta=%d)" % (n_after, n_after - n_before))

    # Verify Dome feature exists
    if result["delta"] > 0:
        try:
            from ai_sw_bridge.com.earlybind import typed
            from ai_sw_bridge.com.sw_type_info import wrapper_module
            mod = wrapper_module()
            fm = doc.FeatureManager
            feats = fm.GetFeatures(True)
            for f in (feats or []):
                try:
                    ifeat = typed(f, "IFeature", module=mod)
                    name = ifeat.Name
                    typ = ifeat.GetTypeName2()
                    if "Dome" in name or "Dome" in typ:
                        result["feature_name"] = name
                        result["feature_type"] = typ
                        print("[pae] found: %s (%s)" % (name, typ))
                        break
                except Exception:
                    pass
        except Exception as e:
            result["verify_error"] = str(e)[:200]

    out_path = os.path.join(RESULTS_DIR, "dome_pae_run.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print("[pae] results -> %s" % out_path)
    try: sw.CloseDoc(_title(doc))
    except Exception: pass
    pythoncom.CoUninitialize()
    return 0 if result.get("ok") and result.get("delta", 0) > 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())

