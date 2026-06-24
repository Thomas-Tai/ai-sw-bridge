"""Spike v0.16 - Epic C: E4 interference detection (Assembly).
Probes assembly doc acquisition + IInterferenceDetectionManager.
Usage: python spikes/v0_16/spike_interference.py --out spikes/v0_16/_results/interference.json
"""

from __future__ import annotations
import argparse, json, os, sys, tempfile, time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
_V16 = Path(__file__).resolve().parent
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))
sys.path.insert(0, str(_V16))
import pythoncom
import win32com.client as w32
from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module
from spike_earlybind_persist import connect_running_sw, ensure_sw_module


def _title(doc):
    t = doc.GetTitle
    return t() if callable(t) else t


def _try_close(sw, doc):
    try:
        sw.CloseDoc(_title(doc))
    except:
        pass


def _capture(fn):
    try:
        return {"status": "OK"}, fn()
    except Exception as exc:
        return {
            "status": "ERR",
            "type": type(exc).__name__,
            "message": str(exc)[:200],
        }, None


def _build_box(sw, path):
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-0.01, -0.01, 0, 0.01, 0.01, 0)
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
        0.01,
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


def run():
    result = {"spike": "interference_epic_C"}
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))
    sw = connect_running_sw()
    # Phase 1: assembly template
    print("[spike] checking assembly template...")
    try:
        asm_template = sw.GetUserPreferenceStringValue(9)
        result["assembly_template"] = asm_template
        has_template = bool(asm_template) and os.path.exists(asm_template)
        result["template_exists"] = has_template
    except Exception as e:
        result["assembly_template_error"] = str(e)[:200]
        has_template = False
    if not has_template:
        result["overall"] = "WALL"
        result["interpretation"] = "No assembly template. Assembly blocked."
        return result
    # Phase 2: build box parts
    print("[spike] building box parts...")
    tmpdir = tempfile.gettempdir()
    box1 = os.path.join(tmpdir, "epic_c_box1_%d.SLDPRT" % int(time.time()))
    box2 = os.path.join(tmpdir, "epic_c_box2_%d.SLDPRT" % int(time.time()))
    try:
        _build_box(sw, box1)
        _build_box(sw, box2)
        result["parts"] = [box1, box2]
    except Exception as e:
        result["overall"] = "FAIL"
        result["reason"] = "box parts failed: %s" % str(e)[:200]
        return result
    # Phase 3: create assembly + add components
    print("[spike] creating assembly...")
    asm_doc = sw.NewDocument(asm_template, 0, 0.0, 0.0)
    if asm_doc is None:
        result["overall"] = "WALL"
        result["interpretation"] = (
            "NewDocument(assembly) None. Assembly creation blocked."
        )
        return result
    result["assembly_created"] = True
    result["assembly_title"] = _title(asm_doc)
    try:
        result["doc_type"] = asm_doc.GetType()
    except:
        pass
    # Add components
    print("[spike] adding components...")
    comps = []
    for label, p in [("box1", box1), ("box2", box2)]:
        rec, comp = _capture(
            lambda pp=p: asm_doc.AddComponent5(pp, 0, "", False, "", 0, 0, 0)
        )
        entry = {"label": label, **rec}
        if comp is not None:
            entry["has_component"] = True
        comps.append(entry)
    result["add_components_v5"] = comps
    comps_ok = all(c.get("has_component") for c in comps)
    if not comps_ok:
        comps2 = []
        for label, p in [("box1", box1), ("box2", box2)]:
            rec, comp = _capture(lambda pp=p: asm_doc.AddComponent4(pp, "", 0, 0, 0))
            entry = {"label": label, **rec}
            if comp is not None:
                entry["has_component"] = True
            comps2.append(entry)
        result["add_components_v4"] = comps2
        comps_ok = any(c.get("has_component") for c in comps2)
    # Phase 4: interference detection manager
    print("[spike] probing interference detection...")
    idm_result = {}
    rec, idm = _capture(lambda: asm_doc.GetInterferenceDetectionManager())
    idm_result["acquire"] = rec
    if idm is not None:
        idm_result["type"] = type(idm).__name__
        idm_result["has_mgr"] = True
        try:
            idm_t = typed(idm, "IInterferenceDetectionManager", module=mod)
            idm_result["typed"] = True
            for mn in (
                "GetInterferenceCount",
                "GetInterferences",
                "SetOptions",
                "RunInterferenceDetection",
            ):
                try:
                    attr = getattr(idm_t, mn)
                    idm_result[mn] = (
                        "callable" if callable(attr) else type(attr).__name__
                    )
                except Exception as e:
                    idm_result[mn] = "ERR: %s" % str(e)[:100]
        except Exception as e:
            idm_result["typed_error"] = str(e)[:200]
    result["interference_mgr"] = idm_result
    # Verdict
    if idm_result.get("has_mgr"):
        result["overall"] = "GREEN"
        result["interpretation"] = "Assembly + interference mgr available."
    elif comps_ok:
        result["overall"] = "PARTIAL"
        result["interpretation"] = "Assembly works but interference mgr unavailable."
    else:
        result["overall"] = "WALL"
        result["interpretation"] = "Assembly doc acquisition blocked."
    _try_close(sw, asm_doc)
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

    def _safe(o):
        if hasattr(o, "_oleobj_"):
            return "<COM>"
        return str(o)

    payload = json.dumps(result, indent=2, default=_safe)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print("wrote %s" % args.out, file=sys.stderr)
    else:
        print(payload)
    rc = {"GREEN": 0, "PARTIAL": 2, "WALL": 2, "FAIL": 1}.get(result.get("overall"), 1)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
