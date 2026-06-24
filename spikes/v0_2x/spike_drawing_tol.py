"""Wave-28 Slice 1: Drawing dimension tolerance set + persist de-risk.

HARD GO/NO-GO checkpoint. Characterizes whether dimension tolerances can be
set on drawing display dimensions and persist across save/reopen.

CRITICAL INSIGHT (diag3 confirmed): Tolerances are MODEL-OWNED.
  - Drawing's IDimension IS a reference to the PART's IDimension (same COM object)
  - Setting tolerance on drawing dim affects the PART directly
  - Tolerances are stored in .SLDPRT, NOT in .SLDDRW
  - To persist: set tolerance -> save PART (not just drawing)

Test recipe:
  1. Build part (saved) + create drawing with dims
  2. Open part alongside drawing (drawing dims reference part dims)
  3. Set tolerance on drawing's display dimension
  4. Verify tolerance appears on PART's dimension (immediate check)
  5. Save PART
  6. Save drawing
  7. Close all
  8. Reopen PART and verify tolerance persisted

Tests all three v1 tolerance types: symmetric (±), bilateral (+/-), limit.

swTolType_e values:
  swTolNone      = 0
  swTolBasic     = 1
  swTolBilateral = 2
  swTolLimit     = 3
  swTolSymmetric = 4

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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_tol.json"

POPUP_SUPPRESS_TOGGLES = [9, 10, 22, 23]

SW_TOL_NONE = 0
SW_TOL_SYMMETRIC = 4
SW_TOL_BILATERAL = 2
SW_TOL_LIMIT = 3

results: dict[str, Any] = {
    "spike": "w28_drawing_tol",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "tolerance_tests": {},
    "confirmed_recipe": {},
    "verdict": "UNKNOWN",
}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": ok, "detail": detail}
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return ok


def save_results() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(f"  wrote {RESULTS_PATH}", file=sys.stderr)


def _close_all_docs(sw: Any) -> None:
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


def run() -> str:
    print("=" * 70)
    print("Wave-28 Slice 1: Drawing dimension tolerance set + persist de-risk")
    print("=" * 70)
    print("\nKEY INSIGHT: Tolerances are MODEL-OWNED (stored in .SLDPRT)")
    print("Recipe: set tolerance via drawing dim -> SAVE PART -> persist")
    print("=" * 70)

    import win32com.client as w32
    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    tsw = typed(sw, "ISldWorks", module=mod)

    _close_all_docs(sw)

    # Suppress popups
    for tid in POPUP_SUPPRESS_TOGGLES:
        try:
            sw.SetUserPreferenceToggle(tid, False)
        except Exception:
            pass

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())
    PART_PATH = str(_tmp / f"w28_tol_{_ts}_box.SLDPRT")
    DRW_PATH = str(_tmp / f"w28_tol_{_ts}.SLDDRW")

    # ================================================================
    # Phase 0: Build part (saved) and create drawing
    # ================================================================
    print("\n--- Phase 0: Build part and create drawing ---")

    spec = {
        "schema_version": 1,
        "name": "TolTestBox",
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
    gate("build_part", r.ok and os.path.isfile(PART_PATH), f"path={PART_PATH}")
    if not r.ok:
        save_results()
        return "WALL"

    # Open the part (drawing dims will reference this)
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc = ret[0] if isinstance(ret, tuple) else ret
    gate("open_part", part_doc is not None, "part opened for tolerance reference")
    if part_doc is None:
        save_results()
        return "WALL"

    part_mdoc2 = typed_qi(part_doc, "IModelDoc2", module=mod)

    # Create drawing
    drwdots = glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT")
    if not drwdots:
        gate("template", False, "no .drwdot found")
        save_results()
        return "WALL"

    doc_raw = sw.NewDocument(drwdots[0], 0, 0.420, 0.297)
    gate("create_drawing", doc_raw is not None)
    if doc_raw is None:
        save_results()
        return "WALL"

    drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)

    # Create front view
    view_raw = drawing_doc.CreateDrawViewFromModelView3(
        PART_PATH, "*Front", 0.15, 0.15, 0.0
    )
    gate(
        "create_view",
        view_raw is not None and not isinstance(view_raw, int),
        f"type={type(view_raw).__name__}",
    )
    if view_raw is None or isinstance(view_raw, int):
        save_results()
        return "WALL"

    front_view = typed_qi(view_raw, "IView", module=mod)

    # Insert dimensions
    try:
        drawing_doc.InsertModelAnnotations3(0, -1, True, False, True, 0)
        print("  Dimensions inserted via InsertModelAnnotations3")
    except Exception as e:
        gate("dims_insert", False, str(e)[:100])
        save_results()
        return "WALL"

    # Enumerate display dimensions
    try:
        disp_dims = front_view.GetDisplayDimensions()
    except Exception as e:
        gate("dims_enum", False, str(e)[:100])
        save_results()
        return "WALL"

    dim_count = len(disp_dims) if disp_dims else 0
    gate("dims_inserted", dim_count > 0, f"count={dim_count}")
    if dim_count == 0:
        save_results()
        return "WALL"

    # Get first display dimension
    try:
        dd = typed_qi(disp_dims[0], "IDisplayDimension", module=mod)
        drw_dim_raw = dd.GetDimension2(0)
        drw_dim = typed_qi(drw_dim_raw, "IDimension", module=mod)
        dim_name = drw_dim.FullName
    except Exception as e:
        gate("get_first_dim", False, str(e)[:100])
        save_results()
        return "WALL"

    print(f"  First dim: {dim_name}")

    # Short name for IModelDoc2.Parameter lookup
    dim_short_name = (
        dim_name.split("@")[0] + "@" + dim_name.split("@")[1]
    )  # e.g., "D1@SK"

    results["dim_name"] = dim_name
    results["dim_short_name"] = dim_short_name

    # ================================================================
    # Phase 1: In-memory set + read-back for all three types
    # ================================================================
    print("\n--- Phase 1: In-memory tolerance set + read-back ---")

    tolerance_types = [
        {
            "label": "symmetric",
            "type": SW_TOL_SYMMETRIC,
            "min": -0.00005,
            "max": 0.00005,
        },
        {
            "label": "bilateral",
            "type": SW_TOL_BILATERAL,
            "min": -0.00005,
            "max": 0.0001,
        },
        {"label": "limit", "type": SW_TOL_LIMIT, "min": -0.00005, "max": 0.0001},
    ]

    for tt in tolerance_types:
        label = tt["label"]
        print(f"\n  Testing {label}...")

        # Set via drawing dim
        drw_dim.SetToleranceType(tt["type"])
        drw_dim.SetToleranceValues(tt["min"], tt["max"])

        # Read back from drawing dim
        rb_type = drw_dim.GetToleranceType()
        rb_vals = drw_dim.GetToleranceValues()

        print(f"    Drawing dim: type={rb_type}, vals={rb_vals}")

        # Read from PART via Parameter()
        part_dim = part_mdoc2.Parameter(dim_short_name)
        if part_dim is not None:
            part_dim_typed = typed_qi(part_dim, "IDimension", module=mod)
            part_type = part_dim_typed.GetToleranceType()
            part_vals = part_dim_typed.GetToleranceValues()
            print(f"    PART dim:    type={part_type}, vals={part_vals}")

            matches = rb_type == tt["type"] and part_type == tt["type"]
            nontrivial = (
                rb_vals is not None
                and len(rb_vals) >= 2
                and (rb_vals[0] != 0 or rb_vals[1] != 0)
            )

            gate(
                f"{label}_set_read",
                matches and nontrivial,
                f"type={rb_type}, vals={rb_vals}, part_matches={part_type == rb_type}",
            )

            results["tolerance_tests"][label] = {
                "drw_type": rb_type,
                "drw_vals": str(rb_vals),
                "part_type": part_type,
                "part_vals": str(part_vals),
                "matches": matches,
                "nontrivial": nontrivial,
            }
        else:
            gate(f"{label}_part_dim", False, "Parameter() returned None")

    # ================================================================
    # Phase 2: Persistence test - symmetric
    # ================================================================
    print("\n--- Phase 2: Persistence test — symmetric tolerance ---")

    # Set symmetric on drawing dim
    drw_dim.SetToleranceType(SW_TOL_SYMMETRIC)
    drw_dim.SetToleranceValues(-0.00005, 0.00005)
    print(f"  Set symmetric: ±0.05mm")

    # Rebuild PART
    try:
        part_mdoc2.EditRebuild3()
        print("  Part rebuilt")
    except Exception as e:
        print(f"  EditRebuild3: {e}")

    # Save PART (critical!)
    try:
        part_doc.SaveAs3(PART_PATH, 0, 2)
        print(f"  Part saved: {PART_PATH}")
        gate("save_part_symmetric", True)
    except Exception as e:
        gate("save_part_symmetric", False, str(e)[:100])
        save_results()
        return "WALL"

    # Save drawing too
    try:
        doc_raw.SaveAs3(DRW_PATH, 0, 2)
        print(f"  Drawing saved: {DRW_PATH}")
        gate("save_drawing_symmetric", True)
    except Exception as e:
        gate("save_drawing_symmetric", False, str(e)[:100])

    # Close all
    _close_all_docs(sw)

    # Reopen PART and check tolerance
    print("\n  Reopening PART...")
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc2 = ret[0] if isinstance(ret, tuple) else ret
    gate("reopen_part_symmetric", part_doc2 is not None)

    if part_doc2 is not None:
        part_mdoc2_2 = typed_qi(part_doc2, "IModelDoc2", module=mod)
        part_dim2 = part_mdoc2_2.Parameter(dim_short_name)

        if part_dim2 is not None:
            part_dim_t2 = typed_qi(part_dim2, "IDimension", module=mod)
            reopen_type = part_dim_t2.GetToleranceType()
            reopen_vals = part_dim_t2.GetToleranceValues()
            print(f"    Reopened PART dim: type={reopen_type}, vals={reopen_vals}")

            persisted = (
                reopen_type == SW_TOL_SYMMETRIC
                and reopen_vals is not None
                and len(reopen_vals) >= 2
            )
            gate(
                "symmetric_persisted",
                persisted,
                f"type={reopen_type}, vals={reopen_vals}",
            )

            results["tolerance_tests"]["symmetric_persist"] = {
                "reopen_type": reopen_type,
                "reopen_vals": str(reopen_vals),
                "persisted": persisted,
            }
        else:
            gate("symmetric_persisted", False, "Parameter() returned None on reopen")

        # Close part
        try:
            t = part_doc2.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass

    # ================================================================
    # Phase 3: Persistence test — bilateral
    # ================================================================
    print("\n--- Phase 3: Persistence test — bilateral tolerance ---")

    # Reopen part
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc3 = ret[0] if isinstance(ret, tuple) else ret
    if part_doc3 is None:
        gate("reopen_part_bilateral", False, "OpenDoc6 failed")
        save_results()
        return "WALL"

    part_mdoc2_3 = typed_qi(part_doc3, "IModelDoc2", module=mod)
    part_dim3 = part_mdoc2_3.Parameter(dim_short_name)

    if part_dim3 is None:
        gate("bilateral_part_dim", False, "Parameter() returned None")
        save_results()
        return "WALL"

    part_dim_t3 = typed_qi(part_dim3, "IDimension", module=mod)

    # Set bilateral
    part_dim_t3.SetToleranceType(SW_TOL_BILATERAL)
    part_dim_t3.SetToleranceValues(-0.00005, 0.0001)
    print(f"  Set bilateral: +0.1mm/-0.05mm")

    # Rebuild + save
    try:
        part_mdoc2_3.EditRebuild3()
    except Exception:
        pass
    try:
        part_doc3.SaveAs3(PART_PATH, 0, 2)
        gate("save_part_bilateral", True)
    except Exception as e:
        gate("save_part_bilateral", False, str(e)[:100])

    # Close
    try:
        t = part_doc3.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # Reopen and verify
    print("  Reopening PART...")
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc4 = ret[0] if isinstance(ret, tuple) else ret
    gate("reopen_part_bilateral_check", part_doc4 is not None)

    if part_doc4 is not None:
        part_mdoc2_4 = typed_qi(part_doc4, "IModelDoc2", module=mod)
        part_dim4 = part_mdoc2_4.Parameter(dim_short_name)

        if part_dim4 is not None:
            part_dim_t4 = typed_qi(part_dim4, "IDimension", module=mod)
            reopen_type = part_dim_t4.GetToleranceType()
            reopen_vals = part_dim_t4.GetToleranceValues()
            print(f"    Reopened PART dim: type={reopen_type}, vals={reopen_vals}")

            persisted = (
                reopen_type == SW_TOL_BILATERAL
                and reopen_vals is not None
                and len(reopen_vals) >= 2
            )
            gate(
                "bilateral_persisted",
                persisted,
                f"type={reopen_type}, vals={reopen_vals}",
            )

            results["tolerance_tests"]["bilateral_persist"] = {
                "reopen_type": reopen_type,
                "reopen_vals": str(reopen_vals),
                "persisted": persisted,
            }

        try:
            t = part_doc4.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass

    # ================================================================
    # Phase 4: Persistence test — limit
    # ================================================================
    print("\n--- Phase 4: Persistence test — limit tolerance ---")

    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc5 = ret[0] if isinstance(ret, tuple) else ret
    if part_doc5 is None:
        gate("reopen_part_limit", False, "OpenDoc6 failed")
        save_results()
        return "WALL"

    part_mdoc2_5 = typed_qi(part_doc5, "IModelDoc2", module=mod)
    part_dim5 = part_mdoc2_5.Parameter(dim_short_name)

    if part_dim5 is None:
        gate("limit_part_dim", False, "Parameter() returned None")
        save_results()
        return "WALL"

    part_dim_t5 = typed_qi(part_dim5, "IDimension", module=mod)

    # Set limit
    part_dim_t5.SetToleranceType(SW_TOL_LIMIT)
    part_dim_t5.SetToleranceValues(-0.00005, 0.0001)
    print(f"  Set limit: -0.05mm/+0.1mm")

    try:
        part_mdoc2_5.EditRebuild3()
    except Exception:
        pass
    try:
        part_doc5.SaveAs3(PART_PATH, 0, 2)
        gate("save_part_limit", True)
    except Exception as e:
        gate("save_part_limit", False, str(e)[:100])

    try:
        t = part_doc5.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # Reopen and verify
    print("  Reopening PART...")
    ret = tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)
    part_doc6 = ret[0] if isinstance(ret, tuple) else ret
    gate("reopen_part_limit_check", part_doc6 is not None)

    if part_doc6 is not None:
        part_mdoc2_6 = typed_qi(part_doc6, "IModelDoc2", module=mod)
        part_dim6 = part_mdoc2_6.Parameter(dim_short_name)

        if part_dim6 is not None:
            part_dim_t6 = typed_qi(part_dim6, "IDimension", module=mod)
            reopen_type = part_dim_t6.GetToleranceType()
            reopen_vals = part_dim_t6.GetToleranceValues()
            print(f"    Reopened PART dim: type={reopen_type}, vals={reopen_vals}")

            persisted = (
                reopen_type == SW_TOL_LIMIT
                and reopen_vals is not None
                and len(reopen_vals) >= 2
            )
            gate(
                "limit_persisted", persisted, f"type={reopen_type}, vals={reopen_vals}"
            )

            results["tolerance_tests"]["limit_persist"] = {
                "reopen_type": reopen_type,
                "reopen_vals": str(reopen_vals),
                "persisted": persisted,
            }

        try:
            t = part_doc6.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass

    # ================================================================
    # Verdict
    # ================================================================
    print("\n--- Verdict ---")

    sym_p = (
        results["tolerance_tests"].get("symmetric_persist", {}).get("persisted", False)
    )
    bil_p = (
        results["tolerance_tests"].get("bilateral_persist", {}).get("persisted", False)
    )
    lim_p = results["tolerance_tests"].get("limit_persist", {}).get("persisted", False)

    all_go = sym_p and bil_p and lim_p

    verdict = "GO" if all_go else "NO-GO"
    gate("OVERALL", all_go, f"symmetric={sym_p}, bilateral={bil_p}, limit={lim_p}")

    # Record confirmed recipe
    results["confirmed_recipe"] = {
        "ownership": "MODEL-OWNED — tolerances stored in .SLDPRT, not .SLDDRW",
        "com_chain": "IView.GetDisplayDimensions() -> IDisplayDimension.GetDimension2(0) -> IDimension",
        "set_methods": "IDimension.SetToleranceType(swTolType_e), IDimension.SetToleranceValues(min, max)",
        "read_methods": "IDimension.GetToleranceType(), IDimension.GetToleranceValues()",
        "persist_sequence": "set tolerance -> EditRebuild3 -> Save PART (SaveAs3 on .SLDPRT)",
        "swTolType_e": {
            "swTolNone": SW_TOL_NONE,
            "swTolSymmetric": SW_TOL_SYMMETRIC,
            "swTolBilateral": SW_TOL_BILATERAL,
            "swTolLimit": SW_TOL_LIMIT,
        },
        "unit": "metres (SW system units)",
        "key_insight": "Drawing's IDimension IS the PART's IDimension (same COM object)",
    }

    results["verdict"] = verdict
    return verdict


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception as exc:
        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        verdict = "NO-GO"
        results["verdict"] = verdict
    finally:
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict == "GO" else 1)
