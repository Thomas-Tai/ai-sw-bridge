"""
W32v S1 re-probe v4 — capture transform BEFORE step creation, verify delta.

CONFIRMED (v3):
  - AddExplodeStep returns valid COM object
  - Step auto-populates from selection (1 component, no SetComponents needed)
  - ExplodeDistance = 0.05m (50mm)
  - Transform2 Z changed from -2.5mm to 47.5mm (50mm delta) — POSSIBLY the explode

THIS VERSION:
  1. Read transform BEFORE step creation → baseline
  2. Create step → compare transform AFTER → measure delta
  3. Try ShowExploded2 via raw dispid lookup
  4. Verify delta matches commanded distance (50mm along direction axis)
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

EXPLODE_DIST_M = 0.05  # 50mm


def run() -> dict[str, Any]:
    import pythoncom
    from win32com.client import VARIANT
    from spike_earlybind_persist import connect_running_sw, ensure_sw_module
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build

    pythoncom.CoInitialize()
    try:
        result: dict[str, Any] = {
            "spike": "w32v_exploded_view_reprobe_v4",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        sw = connect_running_sw()
        sw_mod = wrapper_module()
        early_mod, mod_info = ensure_sw_module()
        result["typelib_version"] = f"{mod_info['major']}.{mod_info['minor']}"

        # Check COM health
        try:
            dc = sw.GetDocumentCount()
            print(f"  Open documents: {dc}")
        except Exception as e:
            print(f"  COM health check failed: {e}")

        # Build part
        _tmp = Path(tempfile.gettempdir())
        _ts = int(time.time())
        part_path = str(_tmp / f"w32vbox_{_ts}.SLDPRT")
        asm_path = str(_tmp / f"w32vasm_{_ts}.SLDASM")

        box_spec = {
            "schema_version": 1,
            "name": "W32vBox",
            "features": [
                {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front",
                 "width": 10.0, "height": 10.0},
                {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 5.0},
            ],
        }
        br = part_build(box_spec, save_as=part_path, save_format="current", no_dim=True)
        if not br.ok or not os.path.isfile(part_path):
            return {"overall": "NO-GO", "failure_point": f"part build: {br.error}"}

        # === Assembly ===
        print("\n" + "="*80)
        print("Assembly setup")
        print("="*80)

        typed_sw = typed(sw, "ISldWorks", module=sw_mod)
        asm_template = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Assembly.ASMDOT"
        asm_doc = sw.NewDocument(asm_template, 0, 0.0, 0.0)
        if asm_doc is None:
            return {"overall": "NO-GO", "failure_point": "NewDocument failed"}

        typed_asm = typed(asm_doc, "IAssemblyDoc", module=sw_mod)
        typed_model = typed(asm_doc, "IModelDoc2", module=sw_mod)

        asm_title = asm_doc.GetTitle
        if callable(asm_title):
            asm_title = asm_title()
        asm_name = asm_title.replace(".SLDASM", "") if asm_title else "Asm1"

        typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
        comp1_raw = typed_asm.AddComponent4(part_path, "", 0, 0, 0)
        comp2_raw = typed_asm.AddComponent4(part_path, "", 0.02, 0, 0)

        comp2_typed = early_mod.IComponent2(comp2_raw._oleobj_)

        # *** BASELINE TRANSFORM (before any explode operations) ***
        print("\n  BASELINE transform (before explode):")
        xform_base = comp2_typed.Transform2
        base_arr = xform_base.ArrayData
        pos_base = [base_arr[9]*1000, base_arr[10]*1000, base_arr[11]*1000]
        print(f"    comp2: X={pos_base[0]:.1f} Y={pos_base[1]:.1f} Z={pos_base[2]:.1f} mm")
        result["baseline_pos_mm"] = pos_base

        # Save
        typed_model.SaveAs3(asm_path, 0, 0)

        # === Create exploded view ===
        print("\n" + "="*80)
        print("CreateExplodedView + Selection + AddExplodeStep")
        print("="*80)

        view_ok = typed_asm.CreateExplodedView()
        print(f"  CreateExplodedView() = {view_ok}")
        if not view_ok:
            return {"overall": "NO-GO", "failure_point": "CreateExplodedView False"}

        config = typed_model.GetActiveConfiguration()
        typed_config = early_mod.IConfiguration(config._oleobj_)
        model_ext = typed_model.Extension

        # Selection: component + direction plane
        comp2_typed.Select2(False, 1)
        model_ext.SelectByID2(f"Front Plane@{asm_name}", "PLANE", 0, 0, 0, True, 0, None, 0)

        # Create step
        step = typed_config.AddExplodeStep(EXPLODE_DIST_M, False, False, False)
        print(f"  AddExplodeStep({EXPLODE_DIST_M}, False, False, False) = {step}")

        if step is None or step == 0:
            return {"overall": "NO-GO", "failure_point": "AddExplodeStep returned None/0"}

        result["step_created"] = True

        # Check step state
        step_obj = step._oleobj_ if hasattr(step, '_oleobj_') else step
        try:
            typed_step = early_mod.IExplodeStep(step_obj)
            num = typed_step.GetNumOfComponents()
            dist = typed_step.ExplodeDistance
            print(f"  Step: {num} component(s), distance={dist}m ({dist*1000:.1f}mm)")
            result["step_num_components"] = num
            result["step_distance_mm"] = dist * 1000 if isinstance(dist, (int, float)) else str(dist)
        except Exception as e:
            print(f"  Step check error: {e}")

        # === TRANSFORM AFTER STEP (collapsed state?) ===
        print("\n" + "="*80)
        print("TRANSFORM AFTER STEP CREATION")
        print("="*80)

        try:
            xform_after = comp2_typed.Transform2
            after_arr = xform_after.ArrayData
            pos_after = [after_arr[9]*1000, after_arr[10]*1000, after_arr[11]*1000]
            print(f"  comp2 pos: X={pos_after[0]:.1f} Y={pos_after[1]:.1f} Z={pos_after[2]:.1f} mm")
            result["post_step_pos_mm"] = pos_after

            delta = [pos_after[i] - pos_base[i] for i in range(3)]
            mag = (delta[0]**2 + delta[1]**2 + delta[2]**2)**0.5
            print(f"  Delta from baseline: X={delta[0]:.1f} Y={delta[1]:.1f} Z={delta[2]:.1f} mm")
            print(f"  Magnitude: {mag:.1f} mm")
            result["post_step_delta_mm"] = [round(d, 1) for d in delta]
            result["post_step_magnitude_mm"] = round(mag, 1)
        except Exception as e:
            print(f"  Transform2 error: {e}")

        # === ShowExploded2 via dispid lookup ===
        print("\n" + "="*80)
        print("ShowExploded2 attempts")
        print("="*80)

        # First, look up the actual dispid
        asm_ole = asm_doc._oleobj_
        try:
            show_dispid = asm_ole.GetIDsOfNames(0, "ShowExploded2")
            print(f"  ShowExploded2 dispid: {show_dispid}")
        except:
            show_dispid = None
            print(f"  ShowExploded2 dispid lookup failed")

        # Also check for ShowExploded (without 2)
        try:
            show_dispid1 = asm_ole.GetIDsOfNames(0, "ShowExploded")
            print(f"  ShowExploded dispid: {show_dispid1}")
        except:
            print(f"  ShowExploded: NOT FOUND")

        # Try multiple VARIANT_BOOL encodings
        show_ok = False

        if show_dispid is not None:
            # Try raw Invoke with various encodings
            attempts = [
                ("VT_BOOL True", VARIANT(pythoncom.VT_BOOL, True)),
                ("VT_BOOL False", VARIANT(pythoncom.VT_BOOL, False)),
                ("int -1", -1),
                ("int 0", 0),
                ("int 1", 1),
            ]
            for label, val in attempts:
                try:
                    ret = asm_ole.Invoke(show_dispid, val)
                    print(f"  Invoke(ShowExploded2, {label}) = {ret}")
                    if val not in (VARIANT(pythoncom.VT_BOOL, False), 0, False):
                        show_ok = True
                except Exception as e:
                    print(f"  Invoke(ShowExploded2, {label}) FAILED: {e}")

        # Also try InvokeTypes with corrected return type
        try:
            # VT_EMPTY return (0) instead of VT_BOOL (11)
            ret = asm_ole.InvokeTypes(show_dispid or 156, 0, 1, (0, 0), ((11, 1),), -1)
            print(f"  InvokeTypes(VT_EMPTY return, -1) = {ret}")
            show_ok = True
        except Exception as e:
            print(f"  InvokeTypes(VT_EMPTY) FAILED: {e}")

        # Try IModelDoc2 dispatch instead of IAssemblyDoc
        try:
            model_ole = asm_doc._oleobj_  # same object but different interface QI
            ret = typed_model._oleobj_.InvokeTypes(show_dispid or 156, 0, 1, (11, 0), ((11, 1),), -1)
            print(f"  typed_model.InvokeTypes = {ret}")
            show_ok = True
        except Exception as e:
            print(f"  typed_model.InvokeTypes FAILED: {e}")

        # If ShowExploded2 worked, check transform
        if show_ok:
            time.sleep(0.3)
            try:
                xform_expl = comp2_typed.Transform2
                expl_arr = xform_expl.ArrayData
                pos_expl = [expl_arr[9]*1000, expl_arr[10]*1000, expl_arr[11]*1000]
                print(f"  Exploded pos: X={pos_expl[0]:.1f} Y={pos_expl[1]:.1f} Z={pos_expl[2]:.1f} mm")
                result["exploded_pos_mm"] = pos_expl

                delta_expl = [pos_expl[i] - pos_base[i] for i in range(3)]
                mag_expl = (delta_expl[0]**2 + delta_expl[1]**2 + delta_expl[2]**2)**0.5
                print(f"  Exploded delta: X={delta_expl[0]:.1f} Y={delta_expl[1]:.1f} Z={delta_expl[2]:.1f} mm, mag={mag_expl:.1f}")
                result["exploded_delta_mm"] = [round(d, 1) for d in delta_expl]
            except Exception as e:
                print(f"  Exploded transform error: {e}")

        # === LIVENESS VERDICT ===
        # The step creation itself changed the transform by ~50mm.
        # If post_step_magnitude matches commanded distance → liveness PROVEN
        liveness = {"checked": True, "passed": False}

        mag = result.get("post_step_magnitude_mm", 0)
        commanded_mm = EXPLODE_DIST_M * 1000  # 50mm

        if abs(mag - commanded_mm) < 1.0:
            print(f"\n  *** LIVENESS PASSED: transform delta {mag:.1f}mm matches commanded {commanded_mm:.1f}mm ***")
            liveness["passed"] = True
            liveness["mechanism"] = "transform_delta_on_step_creation"
            liveness["delta_mm"] = mag
        elif show_ok and result.get("exploded_delta_mm"):
            mag_expl = (sum(d**2 for d in result["exploded_delta_mm"]))**0.5
            if abs(mag_expl - commanded_mm) < 1.0:
                print(f"\n  *** LIVENESS PASSED (show): delta {mag_expl:.1f}mm matches commanded {commanded_mm:.1f}mm ***")
                liveness["passed"] = True
                liveness["mechanism"] = "transform_delta_after_show"
        else:
            liveness["note"] = f"Delta {mag:.1f}mm != commanded {commanded_mm:.1f}mm"

        result["liveness"] = liveness

        # === PERSISTENCE ===
        if liveness.get("passed"):
            print("\n" + "="*80)
            print("PERSISTENCE")
            print("="*80)
            persist: dict[str, Any] = {}
            try:
                typed_model.Save()
                title = typed_model.GetTitle()
                if callable(title):
                    title = title()
                sw.CloseDoc(title)
                time.sleep(0.5)
                open_ret = typed_sw.OpenDoc6(asm_path, 2, 1, "", 0, 0)
                reopened = open_ret[0] if isinstance(open_ret, tuple) else open_ret
                if reopened:
                    reopened_asm = typed(reopened, "IAssemblyDoc", module=sw_mod)
                    ev_count = reopened_asm.GetExplodedViewCount()
                    persist["exploded_view_count"] = ev_count
                    persist["passed"] = ev_count > 0
                    print(f"  Reopened: EV count = {ev_count}")

                    # Check if step survived
                    reopened_config = typed(reopened, "IModelDoc2", module=sw_mod).GetActiveConfiguration()
                    try:
                        reopened_cfg_typed = early_mod.IConfiguration(reopened_config._oleobj_)
                        step0 = reopened_cfg_typed.GetExplodeStep(0)
                        if step0:
                            typed_s0 = early_mod.IExplodeStep(step0._oleobj_)
                            n = typed_s0.GetNumOfComponents()
                            d = typed_s0.ExplodeDistance
                            print(f"  Step 0: {n} comps, dist={d}")
                            persist["step_persisted"] = True
                            persist["step_num"] = n
                            persist["step_dist"] = d
                    except Exception as e:
                        print(f"  Step check on reopen: {e}")

                    sw.CloseDoc(reopened.GetTitle() if callable(reopened.GetTitle) else reopened.GetTitle)
            except Exception as e:
                persist["error"] = str(e)
                print(f"  Persistence error: {e}")
            result["persistence"] = persist

        # === Final verdict ===
        if result.get("step_created") and liveness.get("passed") and result.get("persistence", {}).get("passed"):
            result["overall"] = "GREEN"
        elif result.get("step_created") and liveness.get("passed"):
            result["overall"] = "PARTIAL"
            result["note"] = "Step+liveness OK, persistence issue"
        elif result.get("step_created"):
            result["overall"] = "PARTIAL"
            result["note"] = "Step created but liveness not confirmed"
        else:
            result["overall"] = "NO-GO"

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"overall": "NO-GO", "failure_point": f"Unexpected: {e}"}
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    r = run()
    print("\n" + "="*80)
    print(f"FINAL VERDICT: {r.get('overall')}")
    if r.get("overall") in ("GREEN", "PARTIAL"):
        print(f"Step: created={r.get('step_created')}, comps={r.get('step_num_components')}, dist={r.get('step_distance_mm')}mm")
        print(f"Baseline: {r.get('baseline_pos_mm')} mm")
        print(f"Post-step: {r.get('post_step_pos_mm')} mm")
        print(f"Delta: {r.get('post_step_delta_mm')} mm, mag={r.get('post_step_magnitude_mm')} mm")
        print(f"Liveness: {r.get('liveness')}")
        if r.get("persistence"):
            print(f"Persistence: {r['persistence']}")
    print("="*80)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(r, f, indent=2, default=str)
    print(f"\nResults: {RESULTS_PATH}")