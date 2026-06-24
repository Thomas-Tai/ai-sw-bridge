"""Wave-28 S1 Diagnostic: Is tolerance model-owned or drawing-owned?

Key question: When we set tolerance on a drawing's IDisplayDimension.GetDimension2(),
does that IDimension point to the PART's dimension (model-owned, persists in .SLDPRT)
or is it a drawing-local copy (lost on save)?

Test matrix:
  A. Set tolerance on PART dimension BEFORE creating drawing → see if drawing shows it
  B. Set tolerance on drawing dimension → see if PART dimension changes
  C. Keep drawing open after setting tolerance → read back without save/reopen

Prereq: SOLIDWORKS 2024 SP1 running.
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
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_tol_diagnostic.json"
)

POPUP_SUPPRESS_TOGGLES = [9, 10, 22, 23]

SW_TOL_SYMMETRIC = 4
SW_TOL_BILATERAL = 2

results: dict[str, Any] = {
    "spike": "w28_drawing_tol_diagnostic",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "tests": {},
}


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"  wrote {RESULTS_PATH}", file=sys.stderr)


def run() -> None:
    print("=" * 70)
    print("Wave-28 S1 Diagnostic: Tolerance ownership model")
    print("=" * 70)

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

    # Suppress popups
    for tid in POPUP_SUPPRESS_TOGGLES:
        try:
            sw.SetUserPreferenceToggle(tid, False)
        except Exception:
            pass

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    PART_PATH = str(_tmp / f"w28_diag_{_ts}_box.SLDPRT")

    # Build part
    print("\n--- Building dimensioned part ---")
    spec = {
        "schema_version": 1,
        "name": "TolDiagBox",
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
    if not r.ok or not os.path.isfile(PART_PATH):
        results["tests"]["build_part"] = {"ok": False}
        save_results()
        return

    # ================================================================
    # Test A: Set tolerance on PART dimension BEFORE creating drawing
    # ================================================================
    print("\n--- Test A: Set tolerance on PART before drawing ---")

    # Open the part
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc = ret[0] if isinstance(ret, tuple) else ret

    if part_doc is None:
        results["tests"]["open_part_A"] = {
            "ok": False,
            "error": "OpenDoc6 returned None",
        }
        save_results()
        return

    part_mdoc2 = typed_qi(part_doc, "IModelDoc2", module=mod)

    # Enumerate part dimensions via FeatureManager
    # Dimensions are in features - we need to get them from the sketch
    print("  Enumerating part dimensions...")

    # Get the sketch feature
    part_dims: list[Any] = []
    try:
        fm = part_mdoc2.FeatureManager
        # Walk features looking for dimensions
        feat_count = fm.GetFeatureCount(False)
        for i in range(feat_count):
            feat = fm.GetFeatureAtIndex(i)
            if feat is None:
                continue
            feat_name = feat.Name
            # Get dimensions from this feature
            try:
                dims = feat.GetDimensions2(0)
                if dims is not None:
                    for d_raw in dims:
                        if d_raw is None:
                            continue
                        d = typed_qi(d_raw, "IDimension", module=mod)
                        d_name = ""
                        try:
                            d_name = d.FullName
                        except Exception:
                            pass
                        part_dims.append(
                            {
                                "dim": d,
                                "name": d_name,
                                "feat": feat_name,
                            }
                        )
            except Exception:
                pass
    except Exception as e:
        print(f"  FeatureManager walk failed: {e}")

    print(f"  Found {len(part_dims)} part dimensions")
    for pd in part_dims:
        print(f"    {pd['name']} (from {pd['feat']})")

    results["tests"]["part_dims_found"] = {
        "count": len(part_dims),
        "names": [pd["name"] for pd in part_dims],
    }

    # Set symmetric tolerance on first part dimension
    if part_dims:
        first_part_dim = part_dims[0]["dim"]
        first_part_dim_name = part_dims[0]["name"]
        try:
            first_part_dim.SetToleranceType(SW_TOL_SYMMETRIC)
            first_part_dim.SetToleranceValues(-0.00005, 0.00005)  # ±0.05mm
            print(f"  Set symmetric tolerance on part dim {first_part_dim_name}")
        except Exception as e:
            print(f"  Failed to set tolerance on part dim: {e}")

        # Rebuild part
        try:
            part_mdoc2.EditRebuild3()
        except Exception:
            pass

        # Save part
        try:
            part_doc.SaveAs3(PART_PATH, 0, 2)
            print(f"  Saved part")
        except Exception as e:
            print(f"  Failed to save part: {e}")

        # Read back part dim tolerance
        try:
            pt = first_part_dim.GetToleranceType()
            pv = first_part_dim.GetToleranceValues()
            print(f"  Part dim tolerance (in-memory): type={pt}, values={pv}")
            results["tests"]["part_dim_set_tol"] = {
                "name": first_part_dim_name,
                "tol_type": pt,
                "tol_values": str(pv),
            }
        except Exception as e:
            print(f"  Failed to read part dim tolerance: {e}")

    # Create drawing with dimensions:true
    print("\n  Creating drawing with dimensions:true...")
    drwdots = glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT")
    if not drwdots:
        results["tests"]["template"] = {"ok": False}
        save_results()
        return

    template = drwdots[0]
    DRW_PATH = str(_tmp / f"w28_diag_{_ts}.SLDDRW")

    doc_raw = sw.NewDocument(template, 0, 0.420, 0.297)
    if doc_raw is None:
        results["tests"]["drawing_create"] = {"ok": False}
        save_results()
        return

    drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
    drw_mdoc2 = typed_qi(doc_raw, "IModelDoc2", module=mod)

    # Create front view
    view_raw = drawing_doc.CreateDrawViewFromModelView3(
        PART_PATH, "*Front", 0.15, 0.15, 0.0
    )
    if view_raw is None:
        results["tests"]["view_create"] = {"ok": False}
        save_results()
        return

    front_view = typed_qi(view_raw, "IView", module=mod)

    # Insert dimensions
    drawing_doc.InsertModelAnnotations3(0, -1, True, False, True, 0)

    # Enumerate drawing dimensions
    drw_dims: list[dict[str, Any]] = []
    try:
        disp_dims = front_view.GetDisplayDimensions()
        if disp_dims:
            for dd_raw in disp_dims:
                if dd_raw is None:
                    continue
                dd = typed_qi(dd_raw, "IDisplayDimension", module=mod)
                try:
                    d_raw = dd.GetDimension2(0)
                    if d_raw is None:
                        continue
                    d = typed_qi(d_raw, "IDimension", module=mod)
                    d_name = ""
                    try:
                        d_name = d.FullName
                    except Exception:
                        pass
                    tol_type = None
                    tol_vals = None
                    try:
                        tol_type = d.GetToleranceType()
                        tol_vals = d.GetToleranceValues()
                    except Exception:
                        pass
                    drw_dims.append(
                        {
                            "dim": d,
                            "name": d_name,
                            "tol_type": tol_type,
                            "tol_vals": str(tol_vals) if tol_vals else None,
                        }
                    )
                except Exception:
                    pass
    except Exception:
        pass

    print(f"  Drawing has {len(drw_dims)} display dimensions")
    for dd in drw_dims:
        print(f"    {dd['name']}: tol_type={dd['tol_type']}, tol_vals={dd['tol_vals']}")

    results["tests"]["drawing_dims_from_toleranced_part"] = {
        "count": len(drw_dims),
        "dims": [
            {"name": d["name"], "tol_type": d["tol_type"], "tol_vals": d["tol_vals"]}
            for d in drw_dims
        ],
    }

    # Check if part's tolerance is reflected in drawing
    if part_dims and drw_dims:
        part_dim_name = part_dims[0]["name"]
        matching_drw_dim = None
        for dd in drw_dims:
            if dd["name"] == part_dim_name:
                matching_drw_dim = dd
                break

        if matching_drw_dim:
            drw_tol_type = matching_drw_dim["tol_type"]
            print(f"  Matching drawing dim {part_dim_name} has tol_type={drw_tol_type}")
            results["tests"]["part_tol_reflected_in_drawing"] = {
                "part_dim": part_dim_name,
                "part_tol_type": SW_TOL_SYMMETRIC,
                "drw_tol_type": drw_tol_type,
                "matches": drw_tol_type == SW_TOL_SYMMETRIC,
            }

    # Save and close drawing
    try:
        doc_raw.SaveAs3(DRW_PATH, 0, 2)
        print(f"  Saved drawing")
    except Exception as e:
        print(f"  Failed to save drawing: {e}")

    try:
        t = doc_raw.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # Close part
    try:
        t = part_doc.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # ================================================================
    # Reopen BOTH and check if tolerance persists
    # ================================================================
    print("\n--- Reopening part and drawing ---")

    # Reopen part first
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc = ret[0] if isinstance(ret, tuple) else ret

    if part_doc is not None:
        part_mdoc2 = typed_qi(part_doc, "IModelDoc2", module=mod)

        # Re-get the first dimension
        reopen_part_dims: list[dict[str, Any]] = []
        try:
            fm = part_mdoc2.FeatureManager
            feat_count = fm.GetFeatureCount(False)
            for i in range(feat_count):
                feat = fm.GetFeatureAtIndex(i)
                if feat is None:
                    continue
                try:
                    dims = feat.GetDimensions2(0)
                    if dims is not None:
                        for d_raw in dims:
                            if d_raw is None:
                                continue
                            d = typed_qi(d_raw, "IDimension", module=mod)
                            d_name = ""
                            try:
                                d_name = d.FullName
                            except Exception:
                                pass
                            tol_type = None
                            tol_vals = None
                            try:
                                tol_type = d.GetToleranceType()
                                tol_vals = d.GetToleranceValues()
                            except Exception:
                                pass
                            reopen_part_dims.append(
                                {
                                    "dim": d,
                                    "name": d_name,
                                    "tol_type": tol_type,
                                    "tol_vals": str(tol_vals) if tol_vals else None,
                                }
                            )
                except Exception:
                    pass
        except Exception:
            pass

        print(f"  Reopened part has {len(reopen_part_dims)} dimensions")
        for pd in reopen_part_dims:
            print(
                f"    {pd['name']}: tol_type={pd['tol_type']}, tol_vals={pd['tol_vals']}"
            )

        results["tests"]["reopen_part_dims"] = {
            "count": len(reopen_part_dims),
            "dims": [
                {
                    "name": d["name"],
                    "tol_type": d["tol_type"],
                    "tol_vals": d["tol_vals"],
                }
                for d in reopen_part_dims
            ],
        }

        try:
            t = part_doc.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass

    # Reopen drawing
    ret = tsw.OpenDoc6(DRW_PATH, 3, 1, "", 0, 0)
    drw_doc = ret[0] if isinstance(ret, tuple) else ret

    if drw_doc is not None:
        drw_typed = typed_qi(drw_doc, "IDrawingDoc", module=mod)

        # Get first model view (skip sheet view)
        reopen_drw_dims: list[dict[str, Any]] = []
        try:
            v = drw_typed.GetFirstView()
            while v is not None:
                tv = typed_qi(v, "IView", module=mod)
                try:
                    disp_dims = tv.GetDisplayDimensions()
                    if disp_dims:
                        for dd_raw in disp_dims:
                            if dd_raw is None:
                                continue
                            dd = typed_qi(dd_raw, "IDisplayDimension", module=mod)
                            try:
                                d_raw = dd.GetDimension2(0)
                                if d_raw is None:
                                    continue
                                d = typed_qi(d_raw, "IDimension", module=mod)
                                d_name = ""
                                try:
                                    d_name = d.FullName
                                except Exception:
                                    pass
                                tol_type = None
                                tol_vals = None
                                try:
                                    tol_type = d.GetToleranceType()
                                    tol_vals = d.GetToleranceValues()
                                except Exception:
                                    pass
                                reopen_drw_dims.append(
                                    {
                                        "name": d_name,
                                        "tol_type": tol_type,
                                        "tol_vals": str(tol_vals) if tol_vals else None,
                                    }
                                )
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    v = tv.GetNextView()
                except Exception:
                    break
        except Exception:
            pass

        print(f"  Reopened drawing has {len(reopen_drw_dims)} dimensions")
        for dd in reopen_drw_dims:
            print(
                f"    {dd['name']}: tol_type={dd['tol_type']}, tol_vals={dd['tol_vals']}"
            )

        results["tests"]["reopen_drw_dims"] = {
            "count": len(reopen_drw_dims),
            "dims": [
                {
                    "name": d["name"],
                    "tol_type": d["tol_type"],
                    "tol_vals": d["tol_vals"],
                }
                for d in reopen_drw_dims
            ],
        }

        try:
            t = drw_doc.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass

    # ================================================================
    # Verdict
    # ================================================================
    print("\n--- Analysis ---")

    # Check if part tolerance persisted
    part_tol_persisted = False
    if reopen_part_dims:
        for pd in reopen_part_dims:
            if pd["tol_type"] == SW_TOL_SYMMETRIC and pd["tol_vals"] is not None:
                part_tol_persisted = True
                break

    # Check if drawing shows tolerance
    drw_shows_tol = False
    if reopen_drw_dims:
        for dd in reopen_drw_dims:
            if dd["tol_type"] == SW_TOL_SYMMETRIC:
                drw_shows_tol = True
                break

    results["verdict"] = {
        "part_tol_persisted": part_tol_persisted,
        "drw_shows_tol": drw_shows_tol,
        "ownership_model": "model-owned" if part_tol_persisted else "unknown",
    }

    print(f"  Part tolerance persisted: {part_tol_persisted}")
    print(f"  Drawing shows tolerance: {drw_shows_tol}")
    print(f"  Ownership model: {results['verdict']['ownership_model']}")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        results["tests"]["UNEXPECTED"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        save_results()
    print("\nDone")
