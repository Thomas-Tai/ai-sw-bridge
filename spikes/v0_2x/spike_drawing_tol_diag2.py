"""Wave-28 S1 Diagnostic 2: Simple test - does setting tolerance on drawing
dim affect the PART, and does saving the PART persist it?

Key hypothesis: Drawing's IDimension is a reference to the PART's dimension.
Setting tolerance affects the PART, so saving the PART (not the drawing)
should persist it.

Test:
1. Build part, create drawing with dims
2. Set tolerance on drawing's first dim
3. Save the PART (not drawing)
4. Reopen PART and check tolerance
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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_tol_diag2.json"

SW_TOL_SYMMETRIC = 4

results: dict[str, Any] = {
    "spike": "w28_tol_diag2",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "tests": {},
}


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )


def run() -> None:
    print("Wave-28 S1 Diagnostic 2: Does drawing dim tolerance affect PART?")

    import win32com.client as w32
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # Close all docs
    try:
        for d in sw.GetDocuments() or []:
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
    PART_PATH = str(_tmp / f"w28_d2_{_ts}_box.SLDPRT")

    # Build part
    spec = {
        "schema_version": 1,
        "name": "TolDiag2Box",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK",
                "plane": "Front",
                "width": 40.0,
                "height": 25.0,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 15.0},
        ],
    }
    r = part_build(spec, save_as=PART_PATH, save_format="current", no_dim=False)
    print(f"  Built part: ok={r.ok}")

    if not os.path.isfile(PART_PATH):
        results["tests"]["build"] = {"ok": False}
        save_results()
        return

    # Open part
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc = ret[0] if isinstance(ret, tuple) else ret
    part_mdoc2 = typed_qi(part_doc, "IModelDoc2", module=mod)

    # Create drawing
    drwdots = glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT")
    DRW_PATH = str(_tmp / f"w28_d2_{_ts}.SLDDRW")
    doc_raw = sw.NewDocument(drwdots[0], 0, 0.420, 0.297)
    drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
    drw_mdoc2 = typed_qi(doc_raw, "IModelDoc2", module=mod)

    # Create front view + insert dims
    view_raw = drawing_doc.CreateDrawViewFromModelView3(
        PART_PATH, "*Front", 0.15, 0.15, 0.0
    )
    front_view = typed_qi(view_raw, "IView", module=mod)
    drawing_doc.InsertModelAnnotations3(0, -1, True, False, True, 0)

    # Get first display dimension
    disp_dims = front_view.GetDisplayDimensions()
    print(f"  Display dimensions: {len(disp_dims) if disp_dims else 0}")

    if not disp_dims:
        results["tests"]["dims"] = {"ok": False, "count": 0}
        save_results()
        return

    dd = typed_qi(disp_dims[0], "IDisplayDimension", module=mod)
    dim_raw = dd.GetDimension2(0)
    dim = typed_qi(dim_raw, "IDimension", module=mod)
    dim_name = dim.FullName

    print(f"  First dim: {dim_name}")

    # Read initial tolerance
    init_tol = dim.GetToleranceType()
    init_vals = dim.GetToleranceValues()
    print(f"  Initial tolerance: type={init_tol}, vals={init_vals}")
    results["tests"]["initial_tol"] = {"type": init_tol, "vals": str(init_vals)}

    # Set symmetric tolerance via drawing's dimension
    dim.SetToleranceType(SW_TOL_SYMMETRIC)
    dim.SetToleranceValues(-0.00005, 0.00005)
    print(f"  Set tolerance: type={SW_TOL_SYMMETRIC}, vals=(-0.00005, 0.00005)")

    # Read back immediately on drawing dim
    post_tol = dim.GetToleranceType()
    post_vals = dim.GetToleranceValues()
    print(f"  Drawing dim after set: type={post_tol}, vals={post_vals}")
    results["tests"]["drawing_dim_after_set"] = {
        "type": post_tol,
        "vals": str(post_vals),
    }

    # Now check PART's dimension - is it affected?
    # Get the part's dimension via a different route
    # Use IModelDoc2.GetDimension (or similar)
    print("\n  Checking if PART's dimension is affected...")

    # Try getting dimension from part via name
    part_dim = None
    try:
        # IDimension via IModelDoc2 - GetDimensions or parameter access
        # Alternative: Get the parameter directly
        # SW stores dimensions as parameters in features
        # Use: IFeature.GetDimensions or IModelDoc2.Parameter
        param_name = dim_name.split("@")[0]  # e.g., "D1"
        # Walk features to find the sketch
        fm = part_mdoc2.FeatureManager
        feats = fm.GetFeatures(False)  # returns tuple
        if feats:
            for feat_raw in feats:
                if feat_raw is None:
                    continue
                feat = typed_qi(feat_raw, "IFeature", module=mod)
                feat_name = feat.Name
                if feat_name == "SK":
                    # Get dimensions from this sketch feature
                    sketch_dims = feat.GetDimensions2(0)
                    if sketch_dims:
                        for sd_raw in sketch_dims:
                            if sd_raw is None:
                                continue
                            sd = typed_qi(sd_raw, "IDimension", module=mod)
                            sd_name = sd.FullName
                            if sd_name == dim_name:
                                part_dim = sd
                                break
                    break
    except Exception as e:
        print(f"    Part dim lookup failed: {e}")
        results["tests"]["part_dim_lookup"] = {"error": str(e)}

    if part_dim is not None:
        part_tol = part_dim.GetToleranceType()
        part_vals = part_dim.GetToleranceValues()
        print(f"    PART's dim {dim_name}: type={part_tol}, vals={part_vals}")
        results["tests"]["part_dim_tolerance"] = {
            "name": dim_name,
            "type": part_tol,
            "vals": str(part_vals),
            "matches_drawing": part_tol == post_tol,
        }
    else:
        # Try alternative: the drawing's IDimension might actually be the PART's
        # IDimension object (same COM pointer). Check if it has a feature owner
        print(
            "    Could not find part dim separately - checking if drawing dim IS part dim"
        )
        try:
            feat_owner = dim.GetFeatureOwner()
            if feat_owner is not None:
                feat_owner_name = feat_owner.Name
                print(f"    Drawing dim's feature owner: {feat_owner_name}")
                results["tests"]["dim_feature_owner"] = {"name": feat_owner_name}
            else:
                print("    Drawing dim has no feature owner (might be reference dim)")
                results["tests"]["dim_feature_owner"] = {"none": True}
        except Exception as e:
            print(f"    GetFeatureOwner failed: {e}")

    # Rebuild PART
    print("\n  Rebuilding PART...")
    try:
        part_mdoc2.EditRebuild3()
    except Exception as e:
        print(f"    EditRebuild3 failed: {e}")

    # Save PART (not drawing)
    print("\n  Saving PART...")
    try:
        part_doc.SaveAs3(PART_PATH, 0, 2)
        print("    Part saved")
    except Exception as e:
        print(f"    Part save failed: {e}")

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

    # Reopen PART and check tolerance
    print("\n  Reopening PART...")
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc2 = ret[0] if isinstance(ret, tuple) else ret

    if part_doc2 is None:
        results["tests"]["reopen_part"] = {"ok": False}
        save_results()
        return

    part_mdoc2_2 = typed_qi(part_doc2, "IModelDoc2", module=mod)

    # Find the dimension again
    reopen_dim = None
    try:
        fm = part_mdoc2_2.FeatureManager
        feats = fm.GetFeatures(False)
        if feats:
            for feat_raw in feats:
                if feat_raw is None:
                    continue
                feat = typed_qi(feat_raw, "IFeature", module=mod)
                if feat.Name == "SK":
                    sketch_dims = feat.GetDimensions2(0)
                    if sketch_dims:
                        for sd_raw in sketch_dims:
                            if sd_raw is None:
                                continue
                            sd = typed_qi(sd_raw, "IDimension", module=mod)
                            sd_name = sd.FullName
                            if sd_name == dim_name:
                                reopen_dim = sd
                                break
                    break
    except Exception as e:
        print(f"    Reopen dim lookup failed: {e}")

    if reopen_dim is not None:
        reopen_tol = reopen_dim.GetToleranceType()
        reopen_vals = reopen_dim.GetToleranceValues()
        print(
            f"    Reopened PART dim {dim_name}: type={reopen_tol}, vals={reopen_vals}"
        )
        results["tests"]["reopen_part_dim"] = {
            "name": dim_name,
            "type": reopen_tol,
            "vals": str(reopen_vals),
            "persisted": reopen_tol == SW_TOL_SYMMETRIC,
        }
    else:
        print("    Could not find dim on reopened part")
        results["tests"]["reopen_part_dim"] = {"found": False}

    try:
        t = part_doc2.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # Verdict
    if "reopen_part_dim" in results["tests"]:
        persisted = results["tests"]["reopen_part_dim"].get("persisted", False)
        results["verdict"] = "GO" if persisted else "NO-GO"
        print(
            f"\n  VERDICT: {results['verdict']} (tolerance {'persisted' if persisted else 'NOT persisted'} in PART)"
        )
    else:
        results["verdict"] = "UNKNOWN"


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        results["tests"]["UNEXPECTED"] = {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        save_results()
