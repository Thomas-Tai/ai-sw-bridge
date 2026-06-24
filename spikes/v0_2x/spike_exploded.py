"""
W32 S1 spike — exploded view creation GO/NO-GO probe.

CREATION WORKFLOW (CONFIRMED):
  1. IAssemblyDoc.CreateExplodedView() → creates view
  2. IModelDoc2.GetActiveConfiguration() → IConfiguration
  3. IConfiguration.AddExplodeStep(dist_m, reverse, rigid, related) → IExplodeStep
  4. IExplodeStep.SetComponents([comp])
  5. ShowExploded2(True) with VARIANT_TRUE=-1

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_exploded.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "exploded.json"


def run() -> dict[str, Any]:
    import pythoncom
    from spike_earlybind_persist import connect_running_sw, ensure_sw_module
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build
    from win32com.client import VARIANT

    pythoncom.CoInitialize()
    try:
        result: dict[str, Any] = {
            "spike": "w32_exploded_view_probe",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        sw = connect_running_sw()
        mod = wrapper_module()
        early_mod, mod_info = ensure_sw_module()

        try:
            result["sw_revision"] = str(sw.RevisionNumber)
        except:
            result["sw_revision"] = "<unreadable>"
        result["typelib_info"] = mod_info

        # Build part using proven spec builder
        _tmp = Path(tempfile.gettempdir())
        _ts = int(time.time())
        part_path = str(_tmp / f"w32box_{_ts}.SLDPRT")
        asm_path = str(_tmp / f"w32asm_{_ts}.SLDASM")

        box_spec = {
            "schema_version": 1,
            "name": "W32Box",
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
        if not br.ok or not os.path.isfile(part_path):
            result["overall"] = "NO-GO"
            result["failure_point"] = f"part build failed: {br.error}"
            return result

        result["part_path"] = part_path

        # === Create assembly ===
        print("\n" + "=" * 80)
        print("Creating 2-component assembly")
        print("=" * 80)

        typed_sw = typed(sw, "ISldWorks", module=mod)
        asm_template = (
            r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"
        )

        asm_doc = sw.NewDocument(asm_template, 0, 0.0, 0.0)
        if asm_doc is None:
            result["overall"] = "NO-GO"
            result["failure_point"] = "NewDocument assembly failed"
            return result

        typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
        typed_model = typed(asm_doc, "IModelDoc2", module=mod)

        # Pre-open part
        open_ret = typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
        if isinstance(open_ret, tuple):
            open_ret[0]

        # Add components
        comp1 = typed_asm.AddComponent4(part_path, "", 0, 0, 0)
        comp2 = typed_asm.AddComponent4(part_path, "", 0.02, 0, 0)  # 20mm X offset
        print(f"  comp1={comp1}, comp2={comp2}")

        result["components_added"] = comp1 is not None and comp2 is not None
        typed_model.SaveAs3(asm_path, 0, 0)
        result["asm_path"] = asm_path

        # === CREATE EXPLODED VIEW ===
        print("\n" + "=" * 80)
        print("STEP 1: CreateExplodedView")
        print("=" * 80)

        explode_result = {}

        try:
            view_created = typed_asm.CreateExplodedView()
            print(f"  CreateExplodedView() = {view_created}")
            explode_result["view_created"] = view_created

            if view_created:
                ev_count = typed_asm.GetExplodedViewCount()
                print(f"  GetExplodedViewCount() = {ev_count}")
                explode_result["exploded_view_count"] = ev_count

                # === ADD EXPLODE STEP via IConfiguration ===
                print("\n" + "=" * 80)
                print("STEP 2: IConfiguration.AddExplodeStep")
                print("=" * 80)

                config = typed_model.GetActiveConfiguration()
                print(f"  GetActiveConfiguration() = {config}")

                if config:
                    typed_config = early_mod.IConfiguration(config._oleobj_)

                    # Get components
                    comps = typed_asm.GetComponents(False)
                    if isinstance(comps, tuple):
                        comps = list(comps)

                    print(f"  Components count: {len(comps) if comps else 0}")

                    if comps and len(comps) >= 2:
                        comp_to_explode = comps[1]
                        comp_name = comp_to_explode.Name
                        if callable(comp_name):
                            comp_name = comp_name()
                        print(f"  Component: {comp_name}")

                        # Select component
                        select_ok = comp_to_explode.Select2(False, 1)
                        print(f"  Select2(False, 1) = {select_ok}")
                        explode_result["select_result"] = select_ok

                        # AddExplodeStep on IConfiguration
                        print("\n  Calling AddExplodeStep...")
                        distance_m = 0.05  # 50mm
                        reverse = False
                        rigid = False
                        related = False

                        try:
                            step = typed_config.AddExplodeStep(
                                distance_m, reverse, rigid, related
                            )
                            print(
                                f"  AddExplodeStep({distance_m}, {reverse}, {rigid}, {related}) = {step}"
                            )
                            explode_result["step_returned"] = str(step)

                            if step is not None and step != 0:
                                explode_result["step_created"] = True
                                print("  EXPLODE STEP CREATED!")

                                # Get typed IExplodeStep
                                typed_step = early_mod.IExplodeStep(step._oleobj_)

                                # Set components
                                print("\n  Setting components...")
                                try:
                                    comps_var = VARIANT(
                                        pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
                                        [comp_to_explode],
                                    )
                                    typed_step.SetComponents(comps_var)
                                    print("    SetComponents OK")
                                    explode_result["set_components"] = "OK"
                                except Exception as e:
                                    print(f"    SetComponents error: {e}")
                                    explode_result["set_components_error"] = str(e)

                                # Verify
                                try:
                                    num = typed_step.GetNumOfComponents()
                                    print(f"    GetNumOfComponents = {num}")
                                    explode_result["step_num_components"] = num
                                except Exception as e:
                                    print(f"    GetNumOfComponents error: {e}")

                            else:
                                explode_result["step_error"] = (
                                    f"AddExplodeStep returned {step}"
                                )

                        except Exception as e:
                            print(f"  AddExplodeStep error: {e}")
                            import traceback

                            traceback.print_exc()
                            explode_result["step_error"] = str(e)

                    else:
                        explode_result["error"] = "No components"
                else:
                    explode_result["error"] = "GetActiveConfiguration returned None"

        except Exception as e:
            explode_result["error"] = str(e)
            print(f"  Error: {e}")
            import traceback

            traceback.print_exc()

        result["explode_creation"] = explode_result

        # === LIVENESS GATE ===
        print("\n" + "=" * 80)
        print("LIVENESS GATE")
        print("=" * 80)

        liveness = {"checked": False, "passed": False}

        try:
            comps = typed_asm.GetComponents(False)
            if isinstance(comps, tuple):
                comps = list(comps)

            if comps and len(comps) >= 2:
                comp = comps[1]

                # Collapsed transform
                xform_c = comp.Transform2
                if xform_c:
                    arr_c = xform_c.ArrayData
                    pos_c = [arr_c[9] * 1000, arr_c[10] * 1000, arr_c[11] * 1000]
                    print(f"  Collapsed: {pos_c} mm")
                    liveness["collapsed_pos_mm"] = pos_c

                # Show exploded (VARIANT_TRUE = -1)
                print("\n  ShowExploded2(True)...")
                try:
                    ret = asm_doc._oleobj_.InvokeTypes(
                        156, 0, 1, (11, 0), ((11, 1),), -1
                    )
                    print(f"    Result: {ret}")
                    liveness["show_result"] = ret
                except Exception as e:
                    print(f"    Error: {e}")
                    liveness["show_error"] = str(e)

                # Exploded transform
                xform_e = comp.Transform2
                if xform_e:
                    arr_e = xform_e.ArrayData
                    pos_e = [arr_e[9] * 1000, arr_e[10] * 1000, arr_e[11] * 1000]
                    print(f"  Exploded: {pos_e} mm")
                    liveness["exploded_pos_mm"] = pos_e

                    if "collapsed_pos_mm" in liveness:
                        delta = [pos_e[i] - pos_c[i] for i in range(3)]
                        mag = (delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2) ** 0.5
                        print(f"  Delta: {delta} mm, magnitude: {mag:.3f}")
                        liveness["delta_mm"] = delta
                        liveness["magnitude_mm"] = mag

                        liveness["checked"] = True
                        if mag > 0.5:
                            liveness["passed"] = True
                            print("  LIVENESS PASS!")
                        else:
                            print("  LIVENESS FAIL")

                # Collapse back
                try:
                    asm_doc._oleobj_.InvokeTypes(156, 0, 1, (11, 0), ((11, 1),), 0)
                    print("  Collapsed back")
                except:
                    pass

        except Exception as e:
            liveness["error"] = str(e)
            print(f"  Error: {e}")

        result["liveness"] = liveness

        # === PERSISTENCE ===
        if liveness.get("passed"):
            print("\n" + "=" * 80)
            print("PERSISTENCE")
            print("=" * 80)

            persist = {"checked": False, "passed": False}

            try:
                typed_model.Save()
                sw.CloseDoc(typed_model.GetTitle())

                open_ret = typed_sw.OpenDoc6(asm_path, 2, 1, "", 0, 0)
                reopened = open_ret[0] if isinstance(open_ret, tuple) else open_ret

                if reopened:
                    reopened_asm = typed(reopened, "IAssemblyDoc", module=mod)
                    ev_count = reopened_asm.GetExplodedViewCount()
                    print(f"  GetExplodedViewCount = {ev_count}")

                    if ev_count > 0:
                        persist["checked"] = True
                        persist["passed"] = True
                        print("  PERSISTENCE PASS!")

                    sw.CloseDoc(reopened.GetTitle())

            except Exception as e:
                persist["error"] = str(e)

            result["persistence"] = persist

        # === Verdict ===
        if (
            explode_result.get("step_created")
            and liveness.get("passed")
            and result.get("persistence", {}).get("passed")
        ):
            result["overall"] = "GREEN"
            result["recipe"] = {
                "workflow": [
                    "IAssemblyDoc.CreateExplodedView() → creates view",
                    "IModelDoc2.GetActiveConfiguration() → IConfiguration",
                    "IComponent2.Select2(False, mark=1)",
                    "IConfiguration.AddExplodeStep(dist_m, reverse, rigid, related) → IExplodeStep",
                    "IExplodeStep.SetComponents([comps])",
                    "ShowExploded2(True) via InvokeTypes(156,...,-1)",
                ],
                "key_findings": [
                    "AddExplodeStep is on IConfiguration, NOT IAssemblyDoc",
                    "distance in meters",
                    "VARIANT_TRUE = -1 for ShowExploded2",
                ],
            }
        else:
            result["overall"] = "NO-GO"
            reasons = []
            if not explode_result.get("view_created"):
                reasons.append("CreateExplodedView failed")
            if not explode_result.get("step_created"):
                reasons.append(
                    f"AddExplodeStep: {explode_result.get('step_error', 'unknown')}"
                )
            if not liveness.get("passed"):
                reasons.append(
                    f"Liveness: magnitude={liveness.get('magnitude_mm', 'N/A')}"
                )
            result["failure_point"] = "; ".join(reasons)

        return result

    except Exception as e:
        result["overall"] = "NO-GO"
        result["failure_point"] = f"Unexpected: {e}"
        import traceback

        traceback.print_exc()
        return result
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    r = run()
    print("\n" + "=" * 80)
    print(f"FINAL VERDICT: {r.get('overall')}")
    if r.get("overall") == "GREEN":
        print(f"RECIPE: {r.get('recipe')}")
    else:
        print(f"FAILURE: {r.get('failure_point')}")
    print("=" * 80)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(r, f, indent=2)
    print(f"\nResults: {RESULTS_PATH}")
