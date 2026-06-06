"""Wave-28 S1 Diagnostic 3: Simpler test using IModelDoc2.Parameter(name).

Key test:
1. Build part, create drawing with dims
2. Set tolerance on drawing's first dim (which is the PART's dim)
3. Use IModelDoc2.Parameter(name) to check PART's dim directly
4. Save PART
5. Reopen PART, use Parameter(name) to check tolerance persists
"""

from __future__ import annotations

import glob
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_tol_diag3.json"

SW_TOL_SYMMETRIC = 4

results: dict[str, Any] = {
    "spike": "w28_tol_diag3",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "tests": {},
}


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


def run() -> None:
    print("=" * 60)
    print("Wave-28 S1 Diagnostic 3: IModelDoc2.Parameter route")
    print("=" * 60)

    import win32com.client as w32
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # Close all docs
    try:
        for d in (sw.GetDocuments() or []):
            try:
                t = d.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
    except Exception:
        pass

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    PART_PATH = str(_tmp / f"w28_d3_{_ts}_box.SLDPRT")

    # Build part
    spec = {
        "schema_version": 1,
        "name": "TolDiag3Box",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK",
             "plane": "Front", "width": 40.0, "height": 25.0},
            {"type": "boss_extrude_blind", "name": "EX",
             "sketch": "SK", "depth": 15.0},
        ],
    }
    r = part_build(spec, save_as=PART_PATH, save_format="current", no_dim=False)
    print(f"  Built part: ok={r.ok}, path={PART_PATH}")
    results["tests"]["build"] = {"ok": r.ok}

    if not os.path.isfile(PART_PATH):
        save_results()
        return

    # Open part
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc = ret[0] if isinstance(ret, tuple) else ret
    part_mdoc2 = typed_qi(part_doc, "IModelDoc2", module=mod)

    # Get initial dimension via IModelDoc2.Parameter
    # Dimension names are like "D1@SK" or full "D1@SK@PartName.Part"
    dim_name_short = "D1@SK"
    print(f"\n--- Getting dimension via Parameter({dim_name_short}) ---")

    try:
        dim_via_param = part_mdoc2.Parameter(dim_name_short)
        if dim_via_param is not None:
            param_dim = typed_qi(dim_via_param, "IDimension", module=mod)
            param_full_name = param_dim.FullName
            init_tol = param_dim.GetToleranceType()
            init_vals = param_dim.GetToleranceValues()
            print(f"  Parameter dim: {param_full_name}")
            print(f"  Initial tolerance: type={init_tol}, vals={init_vals}")
            results["tests"]["param_dim_initial"] = {
                "full_name": param_full_name,
                "tol_type": init_tol,
                "tol_vals": str(init_vals),
            }
        else:
            print("  Parameter() returned None")
            results["tests"]["param_dim_initial"] = {"found": False}
    except Exception as e:
        print(f"  Parameter() failed: {e}")
        results["tests"]["param_dim_initial"] = {"error": str(e)}

    # Create drawing with dims
    print("\n--- Creating drawing ---")
    drwdots = glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT")
    DRW_PATH = str(_tmp / f"w28_d3_{_ts}.SLDDRW")
    doc_raw = sw.NewDocument(drwdots[0], 0, 0.420, 0.297)
    drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
    drw_mdoc2 = typed_qi(doc_raw, "IModelDoc2", module=mod)

    view_raw = drawing_doc.CreateDrawViewFromModelView3(PART_PATH, "*Front", 0.15, 0.15, 0.0)
    front_view = typed_qi(view_raw, "IView", module=mod)
    drawing_doc.InsertModelAnnotations3(0, -1, True, False, True, 0)

    # Get first display dimension
    disp_dims = front_view.GetDisplayDimensions()
    print(f"  Display dimensions: {len(disp_dims) if disp_dims else 0}")
    results["tests"]["display_dims"] = {"count": len(disp_dims) if disp_dims else 0}

    if not disp_dims:
        save_results()
        return

    dd = typed_qi(disp_dims[0], "IDisplayDimension", module=mod)
    drw_dim_raw = dd.GetDimension2(0)
    drw_dim = typed_qi(drw_dim_raw, "IDimension", module=mod)
    drw_dim_name = drw_dim.FullName
    print(f"  First drawing dim: {drw_dim_name}")
    results["tests"]["drw_dim"] = {"name": drw_dim_name}

    # Set tolerance on drawing's dimension
    print("\n--- Setting tolerance on drawing's dimension ---")
    drw_dim.SetToleranceType(SW_TOL_SYMMETRIC)
    drw_dim.SetToleranceValues(-0.00005, 0.00005)
    print(f"  Set: type={SW_TOL_SYMMETRIC}, vals=(-0.00005, 0.00005)")

    # Read back drawing dim
    drw_post_tol = drw_dim.GetToleranceType()
    drw_post_vals = drw_dim.GetToleranceValues()
    print(f"  Drawing dim after set: type={drw_post_tol}, vals={drw_post_vals}")
    results["tests"]["drw_dim_after_set"] = {"tol_type": drw_post_tol, "tol_vals": str(drw_post_vals)}

    # Now check PART's dimension via Parameter() - is it affected?
    print("\n--- Checking if PART's dimension is affected ---")
    try:
        dim_via_param2 = part_mdoc2.Parameter(dim_name_short)
        if dim_via_param2 is not None:
            param_dim2 = typed_qi(dim_via_param2, "IDimension", module=mod)
            part_tol = param_dim2.GetToleranceType()
            part_vals = param_dim2.GetToleranceValues()
            print(f"  PART dim after drawing set: type={part_tol}, vals={part_vals}")
            results["tests"]["part_dim_after_drw_set"] = {
                "tol_type": part_tol,
                "tol_vals": str(part_vals),
                "matches_drw": part_tol == drw_post_tol,
            }
            # Key test: if part's dim matches drawing's, they're the same object
            if part_tol == SW_TOL_SYMMETRIC and (part_vals is not None and len(part_vals) >= 2):
                print("  YES! Drawing's dim IS the PART's dim (tolerance propagates)")
        else:
            print("  Parameter() returned None")
    except Exception as e:
        print(f"  Parameter() check failed: {e}")
        results["tests"]["part_dim_after_drw_set"] = {"error": str(e)}

    # Rebuild and save PART
    print("\n--- Rebuilding and saving PART ---")
    try:
        part_mdoc2.EditRebuild3()
        print("  EditRebuild3 done")
    except Exception as e:
        print(f"  EditRebuild3 failed: {e}")

    try:
        part_doc.SaveAs3(PART_PATH, 0, 2)
        print("  Part saved")
    except Exception as e:
        print(f"  Part save failed: {e}")

    # Close all
    try:
        t = doc_raw.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass
    try:
        t = part_doc.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # Reopen PART and check tolerance via Parameter()
    print("\n--- Reopening PART and checking tolerance ---")
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc2 = ret[0] if isinstance(ret, tuple) else ret

    if part_doc2 is None:
        print("  OpenDoc6 returned None")
        results["tests"]["reopen_part"] = {"ok": False}
        save_results()
        return

    part_mdoc2_2 = typed_qi(part_doc2, "IModelDoc2", module=mod)

    try:
        dim_via_param3 = part_mdoc2_2.Parameter(dim_name_short)
        if dim_via_param3 is not None:
            param_dim3 = typed_qi(dim_via_param3, "IDimension", module=mod)
            reopen_tol = param_dim3.GetToleranceType()
            reopen_vals = param_dim3.GetToleranceValues()
            print(f"  Reopened PART dim: type={reopen_tol}, vals={reopen_vals}")
            results["tests"]["reopen_part_dim"] = {
                "tol_type": reopen_tol,
                "tol_vals": str(reopen_vals),
                "persisted": reopen_tol == SW_TOL_SYMMETRIC,
            }
        else:
            print("  Parameter() returned None on reopen")
            results["tests"]["reopen_part_dim"] = {"found": False}
    except Exception as e:
        print(f"  Parameter() on reopen failed: {e}")
        results["tests"]["reopen_part_dim"] = {"error": str(e)}

    try:
        t = part_doc2.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # Verdict
    if "reopen_part_dim" in results["tests"]:
        persisted = results["tests"]["reopen_part_dim"].get("persisted", False)
        verdict = "GO" if persisted else "NO-GO"
        results["verdict"] = verdict
        print(f"\n  VERDICT: {verdict}")
        if persisted:
            print("  Tolerance persisted in PART after drawing dim set + part save")
        else:
            print("  Tolerance NOT persisted - drawing dim is NOT affecting PART dim")
    else:
        results["verdict"] = "UNKNOWN"


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        results["tests"]["UNEXPECTED"] = {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        save_results()