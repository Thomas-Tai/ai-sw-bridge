"""
Investigate AddExplodeStep requirements - why does it return None?
Uses proven part_builder.
"""

import pythoncom
from win32com.client import dynamic, gencache, VARIANT
import winreg
import os
import sys
import tempfile
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

SW_LIBID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"


def _sw_tlb_path():
    try:
        libk = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"TypeLib")
        libk = winreg.OpenKey(libk, SW_LIBID)
    except:
        return None
    vers, i = [], 0
    while True:
        try:
            vers.append(winreg.EnumKey(libk, i))
            i += 1
        except:
            break
    for ver in reversed(vers):
        for arch in ("win64", "win32"):
            try:
                kk = winreg.OpenKey(libk, f"{ver}\\0\\{arch}")
                path, _ = winreg.QueryValueEx(kk, "")
                return path
            except:
                continue
    return None


def investigate():
    pythoncom.CoInitialize()
    try:
        from spike_earlybind_persist import connect_running_sw, ensure_sw_module
        from ai_sw_bridge.com.earlybind import typed
        from ai_sw_bridge.com.sw_type_info import wrapper_module
        from ai_sw_bridge.spec.builder import build as part_build

        path = _sw_tlb_path()
        tlb = pythoncom.LoadTypeLib(path)
        iid, lcid, _, major, minor = tlb.GetLibAttr()[:5]
        mod = gencache.EnsureModule(str(iid), lcid, major, minor)
        early_mod, _ = ensure_sw_module()

        sw = connect_running_sw()
        sw_mod = wrapper_module()

        # Build part using proven builder
        _tmp = Path(tempfile.gettempdir())
        _ts = int(time.time())
        part_path = str(_tmp / f"probe_part_{_ts}.SLDPRT")

        box_spec = {
            "schema_version": 1,
            "name": "ProbeBox",
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK",
                    "plane": "Front",
                    "width": 10.0,
                    "height": 10.0,
                },
                {
                    "type": "boss_extrude_blind",
                    "name": "EX",
                    "sketch": "SK",
                    "depth": 5.0,
                },
            ],
        }
        br = part_build(box_spec, save_as=part_path, save_format="current", no_dim=True)
        if not br.ok:
            print(f"Part build failed: {br.error}")
            return
        print(f"Part: {part_path}")

        # Create assembly
        asm_template = (
            r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"
        )
        asm = sw.NewDocument(asm_template, 0, 0, 0)

        if asm:
            asm_typed = typed(asm, "IAssemblyDoc", module=sw_mod)
            model_typed = typed(asm, "IModelDoc2", module=sw_mod)

            typed_sw = typed(sw, "ISldWorks", module=sw_mod)
            typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)

            comp1 = asm_typed.AddComponent4(part_path, "", 0, 0, 0)
            comp2 = asm_typed.AddComponent4(part_path, "", 0.02, 0, 0)
            print(f"Components: comp1={comp1}, comp2={comp2}")

            # Create exploded view
            print("\n" + "=" * 80)
            print("Creating exploded view:")
            print("=" * 80)

            view_ok = asm_typed.CreateExplodedView()
            print(f"CreateExplodedView: {view_ok}")
            ev_count = asm_typed.GetExplodedViewCount()
            print(f"ExplodedViewCount: {ev_count}")

            # Get config
            config = model_typed.GetActiveConfiguration()
            config_typed = early_mod.IConfiguration(config._oleobj_)
            print(f"Config: {config_typed}")

            # Get components (tuple returned)
            comps = asm_typed.GetComponents(False)
            if isinstance(comps, tuple):
                comps = list(comps)
            print(f"Components list: {len(comps)} items")

            comp = comps[1]
            comp_name = comp.Name() if callable(comp.Name) else comp.Name
            print(f"Component[1]: {comp_name}")

            # Try different approaches for AddExplodeStep
            print("\n" + "=" * 80)
            print("AddExplodeStep attempts:")
            print("=" * 80)

            # Approach 1: Select then call with Python bools
            print("\n  Approach 1: Select + Python bools...")
            select_ok = comp.Select2(False, 1)
            print(f"    Select2(False, 1): {select_ok}")
            step1 = config_typed.AddExplodeStep(0.05, False, False, False)
            print(f"    AddExplodeStep(0.05, False, False, False): {step1}")

            # Approach 2: Use VARIANT_BOOL values (-1 for True, 0 for False)
            print("\n  Approach 2: VARIANT_BOOL values...")
            comp.Select2(False, 1)
            try:
                step2 = config_typed.AddExplodeStep(0.05, 0, 0, 0)  # 0 = VARIANT_FALSE
                print(f"    AddExplodeStep(0.05, 0, 0, 0): {step2}")
            except Exception as e:
                print(f"    Error: {e}")

            # Approach 3: Use raw InvokeTypes with correct VTs
            print("\n  Approach 3: Raw InvokeTypes...")
            comp.Select2(False, 1)
            try:
                # dispid=14, VT_R8=5, VT_BOOL=11, VT_DISPATCH=9
                step3 = config._oleobj_.InvokeTypes(
                    14,
                    0,
                    1,  # dispid, LCID, INVOKE_FUNC
                    (9, 0),  # returns VT_DISPATCH
                    ((5, 1), (11, 1), (11, 1), (11, 1)),  # args
                    0.05,
                    0,
                    0,
                    0,  # distance_m, VARIANT_FALSE, VARIANT_FALSE, VARIANT_FALSE
                )
                print(f"    InvokeTypes(0.05, 0, 0, 0): {step3}")
                if step3:
                    print(f"    Type: {type(step3)}")
            except Exception as e:
                print(f"    Error: {e}")

            # Approach 4: Check if we need to "edit" the exploded view first
            print("\n  Checking exploded view methods...")
            for method in [
                "EditExplodedView",
                "ActivateExplodedView",
                "GetFirstExplodedView",
            ]:
                try:
                    dispid = asm._oleobj_.GetIDsOfNames(0, method)
                    print(f"    {method}: FOUND (dispid={dispid})")
                except:
                    print(f"    {method}: NOT FOUND")

            # Try getting the first exploded view
            print("\n  Getting exploded view object...")
            try:
                first_ev = asm_typed.GetFirstExplodedView()
                print(f"    GetFirstExplodedView: {first_ev}")
                if first_ev:
                    # Check methods on this object
                    for method in ["AddExplodeStep", "GetExplodeStepCount", "Edit"]:
                        try:
                            dispid = first_ev._oleobj_.GetIDsOfNames(0, method)
                            print(f"      ExplodedView.{method}: FOUND")
                        except:
                            pass
            except Exception as e:
                print(f"    GetFirstExplodedView error: {e}")

            # Check if we need to use IGetExplodedViews
            try:
                evs = asm_typed.IGetExplodedViews(ev_count)
                print(f"    IGetExplodedViews({ev_count}): {evs}")
            except Exception as e:
                print(f"    IGetExplodedViews error: {e}")

            # Approach 5: Maybe need to call EditExplodedView first?
            print("\n  Approach 5: EditExplodedView first...")
            try:
                dispid = asm._oleobj_.GetIDsOfNames(0, "EditExplodedView")
                if dispid:
                    # Call EditExplodedView
                    edit_ret = asm_typed.EditExplodedView()
                    print(f"    EditExplodedView: {edit_ret}")

                    # Now try AddExplodeStep again
                    comp.Select2(False, 1)
                    step5 = config_typed.AddExplodeStep(0.05, False, False, False)
                    print(f"    AddExplodeStep after Edit: {step5}")
            except Exception as e:
                print(f"    EditExplodedView approach error: {e}")

            sw.CloseDoc(asm.GetTitle())

    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    investigate()
