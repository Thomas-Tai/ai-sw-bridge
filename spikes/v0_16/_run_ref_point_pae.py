"""Gold-standard PAE for F0 ref_point (face-centroid variant)."""

import os, sys, json, time, tempfile, traceback
import pythoncom
import win32com.client

WT = os.path.join(
    "C:" + os.sep, "D", "WorkSpace", "[Local]_Station", "01_Heavy_Assets", "aisw-W5.3"
)
sys.path.insert(0, os.path.join(WT, "src"))
RESULTS_DIR = os.path.join(WT, "spikes", "v0_16", "_results")
PART_TEMPLATE = os.path.join(
    "C:" + os.sep,
    "ProgramData",
    "SOLIDWORKS",
    "SOLIDWORKS 2024",
    "templates",
    "Part.prtdot",
)

from ai_sw_bridge.mutate import _create_ref_point
from ai_sw_bridge.com.sw_type_info import wrapper_module


def _get_sw():
    pythoncom.CoInitialize()
    return win32com.client.GetActiveObject("SldWorks.Application")


def _title(doc):
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box(sw, path):
    doc = sw.NewDocument(PART_TEMPLATE, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.02, -0.02, 0, 0.02, 0.02, 0)
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
        0.02,
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
    doc.SaveAs3(path, 0, 2)
    sw.CloseDoc(_title(doc))


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    part_path = os.path.join(
        tempfile.gettempdir(), "ref_point_pae_%d.SLDPRT" % int(time.time())
    )
    print("[pae] creating box -> %s" % part_path)
    sw = _get_sw()
    _build_box(sw, part_path)
    print("[pae] box created, re-opening...")
    ret = sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    doc = ret[0] if isinstance(ret, tuple) else ret
    if doc is None:
        print("[pae] FAIL: OpenDoc6 None")
        return 1
    mod = wrapper_module()
    face_ref = {
        "normal": [0.0, 0.0, 1.0],
        "centroid": [0.0, 0.0, 0.02],
        "area_mm2": 1600.0,
        "role_hint": "top_face",
    }
    feature = {"type": "ref_point"}
    target = {"face_ref": face_ref}
    print("[pae] calling _create_ref_point...")
    result = {}
    try:
        ok, err = _create_ref_point(doc, feature, target)
        result["ok"] = ok
        result["error"] = err
    except Exception:
        result["ok"] = False
        result["error"] = traceback.format_exc()
    if result["ok"]:
        feat = doc.FirstFeature()
        while feat is not None:
            fname = getattr(feat, "Name", None)
            if "Point" in str(fname):
                result["feature_name"] = fname
                try:
                    result["feature_type"] = feat.GetTypeName2()
                except:
                    pass
                break
            try:
                feat = feat.GetNextFeature()
            except:
                feat = None
    print("[pae] ok=%s error=%s" % (result.get("ok"), result.get("error")))
    print("[pae] feature=%s" % result.get("feature_name", "N/A"))
    out_path = os.path.join(RESULTS_DIR, "ref_point_pae_run.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print("[pae] results -> %s" % out_path)
    sw.CloseDoc(_title(doc))
    pythoncom.CoUninitialize()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
