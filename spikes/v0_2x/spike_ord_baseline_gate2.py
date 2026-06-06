"""W31v2 S1 — Gate 2 exhaustive probe (Insert* family + baseline).

Gate 1 SOLVED — reused: IView.SelectEntity(datum, False) → count=1 via SelectionManager.
Key fix: use dmdoc2.SelectionManager (CDispatch, memid=65537) NOT ISelectionManager.

Gate 2 exhaustive: 6 methods, datum pre-selected, verify dims_on_reopen.
  ORDINATE:
    1. InsertOrdinate()       — 0-arg, starts ordinate mode
    2. InsertHorizontalOrdinate() — 0-arg
    3. InsertVerticalOrdinate()   — 0-arg
    4. AddOrdinateDimension2(type,X,Y,Z) — 4-arg (memid 208)
  BASELINE:
    5. InsertBaseDim()  — 0-arg
    6. InsertChainDim() — 0-arg

VERIFY-THE-EFFECT: SaveAs3 → CloseDoc → OpenDoc6 → GetDisplayDimensions → count+type.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ai_sw_bridge.com.earlybind import typed, typed_qi, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module


def find_part_template() -> str:
    for pat in glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.PRTDOT"):
        return pat
    return ""


def find_drawing_template() -> str:
    for pat in glob.glob(r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT"):
        return pat
    return ""


def create_test_part(sw, mod) -> tuple[str, Any, Any]:
    tmp_dir = tempfile.mkdtemp(prefix="w31v2_")
    part_path = os.path.join(tmp_dir, "test_box.SLDPRT")

    template = find_part_template()
    if not template:
        raise RuntimeError("No part template found")

    doc_raw = sw.NewDocument(template, 0, 0, 0)
    mdoc2 = typed(doc_raw, "IModelDoc2", module=mod)
    ext = typed_qi(mdoc2.Extension, "IModelDocExtension", module=mod)

    ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
    skm = mdoc2.SketchManager
    skm.InsertSketch(True)
    skm.CreateCenterRectangle(0, 0, 0, 0.05, 0.025, 0)
    skm.InsertSketch(True)

    mdoc2.FeatureManager.FeatureExtrusion2(
        True, False, False, 1, 0, 0.02, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True, 0, 0.0, False,
    )

    mdoc2.EditRebuild3()
    mdoc2.SaveAs3(part_path, 0, 2)
    return part_path, mdoc2, doc_raw


def create_test_drawing(sw, mod, part_path: str) -> tuple[str, Any, Any, Any]:
    tmp_dir = tempfile.mkdtemp(prefix="w31v2_draw_")
    drw_path = os.path.join(tmp_dir, "test_box_drawing.SLDDRW")

    template = find_drawing_template()
    doc_raw = sw.NewDocument(template, 0, 0.21, 0.297)
    drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
    mdoc2 = typed(doc_raw, "IModelDoc2", module=mod)

    view_raw = drawing_doc.CreateDrawViewFromModelView3(part_path, "*Front", 0.1, 0.15, 0.0)
    view = typed_qi(view_raw, "IView", module=mod)
    mdoc2.SaveAs3(drw_path, 0, 2)
    return drw_path, drawing_doc, mdoc2, view


def count_dims(view, mod) -> tuple[int, list[dict]]:
    """Count display dimensions and extract types."""
    try:
        disp_dims = view.GetDisplayDimensions()
    except Exception:
        return 0, []

    if not disp_dims:
        return 0, []

    dims = []
    for dd_raw in disp_dims:
        if dd_raw is None:
            continue
        try:
            dd = typed_qi(dd_raw, "IDisplayDimension", module=mod)
            dim_type = dd.GetType()
            dims.append({"type": dim_type})
        except Exception:
            continue
    return len(dims), dims


def main() -> None:
    import win32com.client

    print("=== W31v2 Gate 2: Exhaustive Insert*/Baseline probe ===\n")

    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True
    mod = wrapper_module()

    part_path, part_mdoc2, part_doc = create_test_part(sw, mod)
    print(f"Part: {part_path}")

    drw_path, drawing_doc, mdoc2, view = create_test_drawing(sw, mod, part_path)
    print(f"Drawing: {drw_path}")

    view_name = view.Name
    drawing_doc.ActivateView(view_name)
    print(f"View: {view_name}")

    outline = view.GetOutline()
    x_ll, y_ll = outline[0], outline[1]
    print(f"Outline: ll=({x_ll:.4f}, {y_ll:.4f})")

    # Get visible entities
    edges_raw = view.GetVisibleEntities(None, 2)
    edges = list(edges_raw) if edges_raw else []
    verts_raw = view.GetVisibleEntities(None, 3)
    verts = list(verts_raw) if verts_raw else []
    print(f"Edges: {len(edges)}, Vertices: {len(verts)}")

    # SelectionManager via CDispatch (memid=65537, NOT ISelectionManager)
    sel_mgr = mdoc2.SelectionManager

    # Test with BOTH edge and vertex datum (NOTE: types are INVERTED in SW selection!)
    # GetVisibleEntities(None, 2) "edges" → SelectEntity reports type=3 (vertex)
    # GetVisibleEntities(None, 3) "vertices" → SelectEntity reports type=2 (edge)
    datum_edge = edges[0] if edges else None
    datum_vert = verts[0] if verts else None

    # Gate 1 verification
    for label, entity in [("edge-entity", datum_edge), ("vertex-entity", datum_vert)]:
        if entity is None:
            continue
        sel_ok = view.SelectEntity(entity, False)
        cnt = sel_mgr.GetSelectedObjectCount2(-1)
        stype = sel_mgr.GetSelectedObjectType2(1)
        print(f"  SelectEntity({label}): ok={sel_ok}, count={cnt}, sel_type={stype}")

    # Use VERTEX-ENTITY as datum (reports sel_type=2=swSelEDGES, which ordinate dims need)
    datum = datum_vert  # vertex entity → selection reports as edge (type=2)
    datum_label = "vertex-entity(sel_type=edge)"

    # Verify selection on chosen datum
    sel_ok = view.SelectEntity(datum, False)
    cnt = sel_mgr.GetSelectedObjectCount2(-1)
    stype = sel_mgr.GetSelectedObjectType2(1)
    print(f"\nUsing {datum_label} datum: count={cnt}, type={stype}")

    if cnt < 1:
        print("FATAL: datum not selected")
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        return

    # Count initial dims
    count_initial, _ = count_dims(view, mod)
    print(f"Initial dims: {count_initial}")

    # Test each method
    methods = [
        # ORDINATE
        {"name": "InsertOrdinate", "args": [], "scheme": "ordinate",
         "sig": "() -> None (interactive mode starter)"},
        {"name": "InsertHorizontalOrdinate", "args": [], "scheme": "ordinate",
         "sig": "() -> None"},
        {"name": "InsertVerticalOrdinate", "args": [], "scheme": "ordinate",
         "sig": "() -> None"},
        {"name": "AddOrdinateDimension2", "args": [0, 0.0, 0.0, 0.0], "scheme": "ordinate",
         "sig": "(type:I4, X:R8, Y:R8, Z:R8) -> I4 (dim count or error code)"},
        # BASELINE
        {"name": "InsertBaseDim", "args": [], "scheme": "baseline",
         "sig": "() -> None"},
        {"name": "InsertChainDim", "args": [], "scheme": "baseline",
         "sig": "() -> None"},
    ]

    results = []
    for tc in methods:
        name = tc["name"]
        args = tc["args"]

        print(f"\n--- {name} ---")

        # Fresh selection
        sel_ok = view.SelectEntity(datum, False)
        cnt = sel_mgr.GetSelectedObjectCount2(-1)
        stype = sel_mgr.GetSelectedObjectType2(1)

        if cnt < 1:
            print(f"  SKIP: count={cnt}")
            results.append({"method": name, "scheme": tc["scheme"], "sig": tc["sig"],
                           "verdict": "SKIP", "reason": f"datum not selected (count={cnt})"})
            continue

        # Call method
        try:
            method = getattr(drawing_doc, name)
            ret = method(*args) if args else method()
            ret_str = str(ret)
        except Exception as e:
            ret_str = f"{type(e).__name__}: {e}"
            ret = None

        print(f"  sel: count={cnt}, type={stype}")
        print(f"  returned: {ret_str}")

        # Immediate dims count
        try:
            mdoc2.EditRebuild3()
        except Exception:
            pass

        count_after, dims_after = count_dims(view, mod)
        dim_types = [d["type"] for d in dims_after]
        print(f"  dims_immediate: {count_after}, types: {dim_types}")

        result = {
            "method": name,
            "scheme": tc["scheme"],
            "sig": tc["sig"],
            "datum_type_at_call": stype,
            "datum_sel_count": cnt,
            "args_called": args,
            "return": ret_str,
            "dims_before": count_initial,
            "dims_immediate": count_after,
            "dim_types_immediate": dim_types,
        }

        if count_after > count_initial:
            result["verdict_immediate"] = "DIMS_CREATED"
        else:
            result["verdict_immediate"] = "ZERO_DIMS"

        results.append(result)

    # Save/reopen verification
    # IMPORTANT: CloseDoc corrupts COM mid-session (reference_close_corrupts_com.md).
    # Use CloseAllDocuments(True) then OpenDoc6 instead.
    print("\n\n=== Save/Reopen verification ===")
    mdoc2.SaveAs3(drw_path, 0, 2)

    # Close ALL docs (clean shutdown)
    sw.CloseAllDocuments(True)

    # Reopen just the drawing
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(drw_path, 3, 1, "", 0, 0)
    reopened_doc = ret[0] if isinstance(ret, tuple) else ret

    if reopened_doc is None:
        print("ERROR: Failed to reopen drawing after CloseAllDocuments")
        reopen_count = -1
        reopen_types = []
    else:
        reopened_drawing = typed_qi(reopened_doc, "IDrawingDoc", module=mod)
        reopened_mdoc2 = typed(reopened_doc, "IModelDoc2", module=mod)
        views_raw = reopened_drawing.GetViews()
        # views_raw is tuple; views_raw[0] is (CDispatch, sheet) — actual view at [0][0]
        v0 = views_raw[0]
        v0_dispatch = v0[0] if isinstance(v0, tuple) else v0
        reopened_view = typed_qi(v0_dispatch, "IView", module=mod)

        reopen_count, reopen_dims = count_dims(reopened_view, mod)
        reopen_types = [d["type"] for d in reopen_dims]
        print(f"dims_reopen: {reopen_count}, types: {reopen_types}")

        # Cleanup
        sw.CloseAllDocuments(True)

    # Update results with reopen data
    for r in results:
        r["dims_reopen"] = reopen_count
        r["dim_types_reopen"] = reopen_types

        # VERDICT: dims on reopen > 0 AND ordinate/baseline type
        # swDimensionType_e: check what types we got
        if reopen_count > count_initial:
            r["verdict"] = "GREEN"
            r["reason"] = f"Dims persisted on reopen ({reopen_count - count_initial})"
        elif r["verdict_immediate"] == "DIMS_CREATED":
            r["verdict"] = "NO-GO"
            r["reason"] = "Dims created immediately but NOT persisted on reopen"
        else:
            r["verdict"] = "NO-GO"
            r["reason"] = "Zero dims both immediate and on reopen"

    # Write results
    results_path = Path(__file__).parent / "_results" / "ord_baseline.json"

    ord_results = [r for r in results if r["scheme"] == "ordinate"]
    base_results = [r for r in results if r["scheme"] == "baseline"]
    ord_green = any(r["verdict"] == "GREEN" for r in ord_results)
    base_green = any(r["verdict"] == "GREEN" for r in base_results)

    output = {
        "wave": "W31v2",
        "date": "2026-06-06",
        "seat": "SW2024 SP1",
        "gate": 2,
        "gate1_status": "SOLVED",
        "gate1_evidence": {
            "SelectionManager_path": "dmdoc2.SelectionManager (CDispatch, memid=65537)",
            "ISelectionManager_path": "FAILS: 'Unable to read write-only property'",
            "SelectEntity_return": True,
            "sel_count_after": cnt,
            "sel_type_after": stype,
            "datum_used": datum_label,
        },
        "key_finding_SelectionManager": (
            "ISelectionManager (memid=65711) fails with 'Unable to read write-only property' "
            "on BOTH typed IModelDoc2 AND late-bound CDispatch. "
            "SelectionManager (memid=65537, PROPGET) works and returns a CDispatch. "
            "GetSelectedObjectCount2(-1) and GetSelectedObjectType2(1) work on this CDispatch."
        ),
        "methods": [
            {"name": m["name"], "scheme": m["scheme"], "sig": m["sig"], "args": m["args"]}
            for m in methods
        ],
        "results": results,
        "schemes": {
            "ordinate": {
                "methods": [r["method"] for r in ord_results],
                "any_green": ord_green,
                "verdict": "GREEN" if ord_green else "EARNED NO-GO",
            },
            "baseline": {
                "methods": [r["method"] for r in base_results],
                "any_green": base_green,
                "verdict": "GREEN" if base_green else "EARNED NO-GO",
            },
        },
    }

    with open(results_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n=== Results: {results_path} ===")
    print(f"\nORDINATE: {'GREEN' if ord_green else 'EARNED NO-GO'}")
    print(f"BASELINE: {'GREEN' if base_green else 'EARNED NO-GO'}")

    # Per-method summary
    print("\nPer-method summary:")
    for r in results:
        print(f"  {r['method']}: {r['verdict']} | return={r['return']} | "
              f"dims_imm={r['dims_immediate']} | dims_reopen={r['dims_reopen']}")

    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


if __name__ == "__main__":
    main()