"""Spike v0.16 - T5: E4 interference full handler (component placement + enumeration).

Builds two overlapping box parts in an assembly via AddComponent5 + IMathTransform.
Then enumerates IInterference results: Volume, GetComponents, GetBodies.
Captures JSON shape for observe.py wiring.
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


def _build_box(sw, path, size=0.02):
    """Build a box part and save to path."""
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.1, 0.1)
    if doc is None:
        raise RuntimeError("NewDocument None")
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    doc.InsertSketch2(True)
    sk = doc.SketchManager
    sk.CreateCornerRectangle(-size / 2, -size / 2, 0, size / 2, size / 2, 0)
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
        size,
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
    result = {"spike": "interference_T5_full"}
    mod = wrapper_module()
    if mod is None:
        mod, info = ensure_sw_module()
        result["module_fallback"] = info
    result["module"] = getattr(mod, "__name__", str(mod))
    sw = connect_running_sw()

    # Build two box parts
    tmpdir = tempfile.gettempdir()
    ts = int(time.time())
    box1_path = os.path.join(tmpdir, "t5_box1_%d.SLDPRT" % ts)
    box2_path = os.path.join(tmpdir, "t5_box2_%d.SLDPRT" % ts)
    print("[t5] building box parts...")
    _build_box(sw, box1_path, size=0.02)
    _build_box(sw, box2_path, size=0.02)
    result["parts"] = [box1_path, box2_path]

    # Create assembly
    print("[t5] creating assembly...")
    asm_template = sw.GetUserPreferenceStringValue(9)
    asm_doc = sw.NewDocument(asm_template, 0, 0.0, 0.0)
    if asm_doc is None:
        result["overall"] = "WALL"
        result["interpretation"] = "Assembly creation blocked"
        return result
    result["assembly_title"] = _title(asm_doc)

    # Add components with placement
    print("[t5] adding components with transforms...")
    iasm = typed(asm_doc, "IAssemblyDoc", module=mod)

    # Place box1 at origin
    try:
        comp1 = iasm.AddComponent5(box1_path, 0, "", False, "", 0.0, 0.0, 0.0)
        result["comp1"] = str(comp1)[:120] if comp1 else "None"
        result["comp1_type"] = type(comp1).__name__ if comp1 else "None"
        print("  comp1: %s (%s)" % (result["comp1"], result["comp1_type"]))
    except Exception as e:
        result["comp1_error"] = str(e)[:200]
        print("  comp1 err: %s" % e)

    # Place box2 offset by 5mm in X (so they overlap by 15mm)
    try:
        comp2 = iasm.AddComponent5(box2_path, 0, "", False, "", 0.005, 0.0, 0.0)
        result["comp2"] = str(comp2)[:120] if comp2 else "None"
        result["comp2_type"] = type(comp2).__name__ if comp2 else "None"
        print("  comp2: %s (%s)" % (result["comp2"], result["comp2_type"]))
    except Exception as e:
        result["comp2_error"] = str(e)[:200]
        print("  comp2 err: %s" % e)

    # Get interference detection manager
    print("[t5] getting interference manager...")
    try:
        mgr = iasm.InterferenceDetectionManager
        result["mgr"] = str(mgr)[:120] if mgr else "None"
        result["mgr_type"] = type(mgr).__name__ if mgr else "None"
        print("  mgr: %s (%s)" % (result["mgr"], result["mgr_type"]))
    except Exception as e:
        result["mgr_error"] = str(e)[:200]
        print("  mgr err: %s" % e)
        mgr = None

    if mgr:
        print("[t5] checking interference count...")
        try:
            count = mgr.GetInterferenceCount()
            result["interference_count"] = count
            print("  count: %s" % count)
        except Exception as e:
            result["count_error"] = str(e)[:200]
            print("  count err: %s" % e)
            count = 0

        if count and count > 0:
            print("[t5] enumerating interferences...")
            try:
                interferences = mgr.GetInterferences()
                if interferences:
                    result["interferences"] = []
                    for i, interf in enumerate(interferences):
                        entry = {"index": i}
                        try:
                            i_interf = typed(interf, "IInterference", module=mod)
                            entry["volume"] = i_interf.Volume
                        except Exception as e:
                            entry["volume_error"] = str(e)[:100]
                        try:
                            comps = i_interf.GetComponents()
                            if comps:
                                entry["components"] = [str(c)[:80] for c in comps]
                        except Exception as e:
                            entry["components_error"] = str(e)[:100]
                        try:
                            bodies = i_interf.GetBodies()
                            if bodies:
                                entry["bodies"] = [str(b)[:80] for b in bodies]
                        except Exception as e:
                            entry["bodies_error"] = str(e)[:100]
                        result["interferences"].append(entry)
            except Exception as e:
                result["interferences_error"] = str(e)[:200]

    _try_close(sw, asm_doc)

    if result.get("interference_count", 0) > 0 and result.get("interferences"):
        result["overall"] = "GREEN"
        result["interpretation"] = (
            "Interference detected: count=%d. IInterference enumeration works. "
            "W0 wires into observe.py." % result["interference_count"]
        )
    elif result.get("interference_count", 0) > 0:
        result["overall"] = "PARTIAL"
        result["interpretation"] = "Count > 0 but enumeration failed."
    elif result.get("comp1") and result.get("comp2"):
        result["overall"] = "PARTIAL"
        result["interpretation"] = "Components placed but count=0."
    else:
        result["overall"] = "WALL"
        result["interpretation"] = "Component placement failed."
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
