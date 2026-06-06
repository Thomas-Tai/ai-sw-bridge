"""Diagnostic: test all component-selection methods on a fresh assembly."""
from __future__ import annotations

import glob
import sys
import tempfile
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom
from spike_earlybind_persist import connect_running_sw

from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module


def main() -> int:
    pythoncom.CoInitialize()
    try:
        sw = connect_running_sw()
    except Exception as e:
        print(f"Could not connect to SW: {e}")
        return 2

    mod = wrapper_module()

    # Build a simple box part
    from ai_sw_bridge.spec.builder import build as part_build
    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    part_path = str(_tmp / f"diag_box_{_ts}.SLDPRT")

    spec = {
        "schema_version": 1,
        "name": "DiagBox",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK",
             "plane": "Front", "width": 20.0, "height": 10.0},
            {"type": "boss_extrude_blind", "name": "EX",
             "sketch": "SK", "depth": 10.0},
        ],
    }
    r = part_build(spec, save_as=part_path, save_format="current", no_dim=True)
    if not r.ok:
        print(f"Part build failed: {r}")
        return 1
    print(f"Part: {part_path}")

    # Create assembly
    templates = glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.ASMDOT")
    asm_doc = sw.NewDocument(templates[0], 0, 0.1, 0.1)
    if asm_doc is None:
        print("Assembly creation failed")
        return 1

    # Pre-open + place
    typed_sw = typed(sw, "ISldWorks", module=mod)
    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    open_ret = typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
    if isinstance(open_ret, tuple):
        open_ret = open_ret[0]

    comp = typed_asm.AddComponent4(part_path, "", 0.0, 0.0, 0.0)
    if comp is None:
        print("AddComponent4 returned None")
        return 1

    cn = comp.Name
    if callable(cn):
        cn = cn()
    print(f"Component name: {cn!r}")
    print(f"Component type: {type(comp).__name__}")

    # Get feature tree type
    fm = asm_doc.FeatureManager
    feats = fm.GetFeatures(True)
    if feats:
        for f in feats:
            fn = f.Name
            if callable(fn):
                fn = fn()
            if fn == cn:
                ft = f.GetTypeName2
                if callable(ft):
                    ft = ft()
                print(f"Feature tree type: {ft!r}")
                break

    ext = typed(asm_doc.Extension, "IModelDocExtension", module=mod)
    sel_mgr = asm_doc.SelectionManager

    # Test all selection methods
    tests = [
        ("SelectByID2 COMPONENT", lambda: ext.SelectByID2(cn, "COMPONENT", 0, 0, 0, False, 0, None, 0)),
        ("SelectByID2 no-type", lambda: ext.SelectByID2(cn, "", 0, 0, 0, False, 0, None, 0)),
        ("SelectByID2 REFERENCE", lambda: ext.SelectByID2(cn, "REFERENCE", 0, 0, 0, False, 0, None, 0)),
        ("SelectByID COMPONENT", lambda: asm_doc.SelectByID(cn, "COMPONENT", 0, 0, 0)),
        ("SelectByID no-type", lambda: asm_doc.SelectByID(cn, "", 0, 0, 0)),
        ("IComponent2.Select4(False,0)", lambda: comp.Select4(False, 0)),
        ("IComponent2.Select4(False,4)", lambda: comp.Select4(False, 4)),
        ("IComponent2.Select2(False,0)", lambda: comp.Select2(False, 0)),
        ("IComponent2.Select2(False,4)", lambda: comp.Select2(False, 4)),
    ]

    for label, fn in tests:
        asm_doc.ClearSelection2(True)
        try:
            ok = fn()
            sc = sel_mgr.GetSelectedObjectCount2(-1)
            sel_type = ""
            if sc and sc > 0:
                obj = sel_mgr.GetSelectedObject6(1, -1)
                sel_type = f" sel_type={type(obj).__name__}"
            print(f"  {label}: ok={ok}{sel_type} sel_count={sc}")
        except Exception as e:
            print(f"  {label}: EXC {type(e).__name__}: {e}")

    # Test IFeature.Select2 on the feature tree entry
    asm_doc.ClearSelection2(True)
    if feats:
        for f in feats:
            fn2 = f.Name
            if callable(fn2):
                fn2 = fn2()
            if fn2 == cn:
                try:
                    ok = f.Select2(False, 4)
                    sc = sel_mgr.GetSelectedObjectCount2(-1)
                    sel_type = ""
                    if sc and sc > 0:
                        obj = sel_mgr.GetSelectedObject6(1, -1)
                        sel_type = f" sel_type={type(obj).__name__}"
                    print(f"  IFeature.Select2(False,4): ok={ok}{sel_type} sel_count={sc}")
                except Exception as e:
                    print(f"  IFeature.Select2(False,4): EXC {type(e).__name__}: {e}")
                break

    # Try a short name (without timestamp)
    short_name = "DiagBox-1"
    asm_doc.ClearSelection2(True)
    try:
        ok = ext.SelectByID2(short_name, "COMPONENT", 0, 0, 0, False, 0, None, 0)
        sc = sel_mgr.GetSelectedObjectCount2(-1)
        print(f"  SelectByID2 '{short_name}' COMPONENT: ok={ok} sel_count={sc}")
    except Exception as e:
        print(f"  SelectByID2 '{short_name}' COMPONENT: EXC {e}")

    # Also try component Name property directly
    try:
        comp2_name = comp.Name
        if callable(comp2_name):
            comp2_name = comp2_name()
        print(f"\nIComponent2.Name = {comp2_name!r}")
        # Try Name2 or GetName
        for attr in ("Name2", "GetName", "GetPathName"):
            try:
                val = getattr(comp, attr, None)
                if val is not None:
                    val = val() if callable(val) else val
                    print(f"  {attr} = {val!r}")
            except Exception:
                pass
    except Exception:
        pass

    # Cleanup
    try:
        t = asm_doc.GetTitle
        if isinstance(t, tuple):
            t = t[0]
        sw.CloseDoc(t() if callable(t) else t)
    except Exception:
        pass
    try:
        sw.CloseDoc(Path(part_path).name)
    except Exception:
        pass

    pythoncom.CoUninitialize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
