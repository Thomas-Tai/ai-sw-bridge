"""Wave-18 Slice 1 v2: BOM insertion with H1+H2+H3 hypotheses.

Run 1 showed InsertBomTable4 → IBomTableAnnotation but GetTableAnnotationCount=0,
IGetBomTable fails "Unable to read write-only property", IBomTable E_NOINTERFACE.

This run adds:
  H3: ActivateView(view_name) before InsertBomTable4 (view must be active context)
  H1: ForceRebuild3(False) after insert (lazy-population rebuild flush)
  H2: probe IBomTableAnnotation directly via GetModelPathNamesCount / GetComponentsCount2
      AND GetTableAnnotations() array walk (in case GetTableAnnotationCount is wrong)

Also tries: UseAnchorPoint=True (sheet anchor), and template="" (SW default BOM).

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import glob as _glob
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
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_bom_v2.json"
)

SW_BOM_TYPE_TOP_LEVEL_ONLY = 1
SW_TABLE_ANCHOR_TOP_LEFT = 1
SW_TABLE_ANCHOR_TOP_RIGHT = 2
SW_INDENTED_NUMBERING_NONE = 2

results: dict[str, Any] = {
    "spike": "w18_drawing_bom_v2",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "characterization": {},
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


def _find_bom_template() -> str | None:
    for pat in [
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\bom-all.sldbomtbt",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\*.sldbomtbt",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\**\*.sldbomtbt",
    ]:
        matches = _glob.glob(pat, recursive=True)
        if matches:
            return matches[0]
    return None


def _find_drawing_template() -> str | None:
    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot",
    ]:
        matches = _glob.glob(pat)
        if matches:
            return matches[0]
    return None


def _probe_bom_annotation(bom_annotation: Any) -> dict[str, Any]:
    """Probe IBomTableAnnotation for row/component data (H2)."""
    info: dict[str, Any] = {}
    # GetAllCustomPropertiesCount — total custom prop columns
    try:
        info["custom_props_count"] = bom_annotation.GetAllCustomPropertiesCount()
    except Exception as e:
        info["custom_props_count_error"] = repr(e)[:100]

    # Try GetModelPathNamesCount for row indices 0..4
    row_counts: dict[int, Any] = {}
    for row_idx in range(5):
        try:
            cnt = bom_annotation.GetModelPathNamesCount(row_idx)
            row_counts[row_idx] = cnt
        except Exception as e:
            row_counts[row_idx] = repr(e)[:80]
    info["model_path_names_count_by_row"] = row_counts

    # Try GetComponentsCount2 for row indices 0..4
    comp_counts: dict[int, Any] = {}
    for row_idx in range(5):
        try:
            cnt = bom_annotation.GetComponentsCount2(row_idx, "")
            comp_counts[row_idx] = cnt
        except Exception as e:
            comp_counts[row_idx] = repr(e)[:80]
    info["components_count2_by_row"] = comp_counts

    # Try GetModelPathNames for row 1 (first data row after header)
    try:
        paths = bom_annotation.GetModelPathNames(1)
        info["model_path_names_row1"] = list(paths) if paths else []
    except Exception as e:
        info["model_path_names_row1_error"] = repr(e)[:80]

    return info


def run() -> str:
    print("=" * 70)
    print("Wave-18 Slice 1 v2: BOM insertion H1+H2+H3")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.mutate import (
        sw_commit_assembly,
        sw_dry_run_assembly,
        sw_propose_assembly,
    )
    from ai_sw_bridge.spec.builder import build as part_build

    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")

    # Close all open docs
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

    bom_template = _find_bom_template()
    drw_template = _find_drawing_template()
    gate("bom_template_found", bom_template is not None, f"path={bom_template}")
    gate("drw_template_found", drw_template is not None, f"path={drw_template}")
    if not bom_template or not drw_template:
        save_results()
        return "WALL"

    # Build parts + assembly
    print("\n--- Building parts + assembly ---")
    PART_A = str(_tmp / f"w18v2_{_ts}_a.SLDPRT")
    PART_B = str(_tmp / f"w18v2_{_ts}_b.SLDPRT")

    for label, path, w_mm in [("a", PART_A, 40.0), ("b", PART_B, 30.0)]:
        spec = {
            "schema_version": 1,
            "name": f"BomV2{label.upper()}",
            "features": [
                {"type": "sketch_rectangle_on_plane", "name": "SK",
                 "plane": "Front", "width": w_mm, "height": 20.0},
                {"type": "boss_extrude_blind", "name": "EX",
                 "sketch": "SK", "depth": 10.0},
            ],
        }
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
        gate(f"build_{label}", r.ok and os.path.isfile(path), f"ok={r.ok}")

    if not (os.path.isfile(PART_A) and os.path.isfile(PART_B)):
        save_results()
        return "WALL"

    ASM_PATH = str(_tmp / f"w18v2_{_ts}.SLDASM")
    asm_spec = {
        "kind": "assembly",
        "name": "bom_v2_asm",
        "components": [
            {"id": "a", "part": PART_A, "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": PART_B, "transform": {"xyz_mm": [0, 0, 15]}},
        ],
        "mates": [
            {"type": "coincident", "alignment": "aligned",
             "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
             "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}}},
        ],
    }

    p = sw_propose_assembly(asm_spec)
    d = sw_dry_run_assembly(p["proposal_id"])
    c = sw_commit_assembly(p["proposal_id"], ASM_PATH)
    component_count = c.get("component_count") or 2
    gate("assembly_commit", c.get("ok", False), f"components={component_count}")

    if not c.get("ok") or not os.path.isfile(ASM_PATH):
        save_results()
        return "WALL"

    results["characterization"]["component_count"] = component_count

    # Open assembly, create drawing, create view
    print("\n--- Drawing setup ---")
    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)

    doc_raw = sw.NewDocument(drw_template, 0, 0.420, 0.297)
    gate("drawing_create", doc_raw is not None and not isinstance(doc_raw, int),
         f"type={type(doc_raw).__name__ if doc_raw else None}")
    if doc_raw is None or isinstance(doc_raw, int):
        save_results()
        return "WALL"

    DRW_PATH = str(_tmp / f"w18v2_{_ts}.SLDDRW")

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
        gate("drawing_qi", drawing_doc is not None, "IDrawingDoc QI ok")

        view_raw = drawing_doc.CreateDrawViewFromModelView3(
            ASM_PATH, "*Front", 0.15, 0.15, 0.0
        )
        view_ok = view_raw is not None and not isinstance(view_raw, int)
        gate("view_created", view_ok,
             f"type={type(view_raw).__name__ if view_raw else None}")
        if not view_ok:
            save_results()
            return "WALL"

        typed_view = typed_qi(view_raw, "IView", module=mod)

        # Get view name for ActivateView (H3)
        view_name = ""
        try:
            view_name = typed_view.GetName2() or ""
            gate("view_name", bool(view_name), f"name={view_name!r}")
            results["characterization"]["view_name"] = view_name
        except Exception as exc:
            gate("view_name", False, f"GetName2 failed: {exc!r}")

        # H3: ActivateView before insert
        print("\n--- H3: ActivateView before BOM insert ---")
        try:
            activated = drawing_doc.ActivateView(view_name) if view_name else None
            gate("h3_activate_view", bool(activated),
                 f"ActivateView({view_name!r})={activated}")
        except Exception as exc:
            gate("h3_activate_view", False, f"raised: {repr(exc)[:80]}")

        # Insert BOM with UseAnchorPoint=False (explicit coordinates)
        print("\n--- BOM insert attempt A (UseAnchorPoint=False, template path) ---")
        bom_ann_a = None
        try:
            bom_ann_a = typed_view.InsertBomTable4(
                False, 0.05, 0.22,
                SW_TABLE_ANCHOR_TOP_LEFT,
                SW_BOM_TYPE_TOP_LEVEL_ONLY,
                "", bom_template, False,
                SW_INDENTED_NUMBERING_NONE, False,
            )
            gate("insert_A", bom_ann_a is not None and not isinstance(bom_ann_a, int),
                 f"type={type(bom_ann_a).__name__ if bom_ann_a else None}")
        except Exception as exc:
            gate("insert_A", False, f"raised: {repr(exc)[:100]}")

        # Insert BOM with UseAnchorPoint=True (sheet anchor)
        print("\n--- BOM insert attempt B (UseAnchorPoint=True) ---")
        bom_ann_b = None
        try:
            bom_ann_b = typed_view.InsertBomTable4(
                True, 0.0, 0.0,
                SW_TABLE_ANCHOR_TOP_RIGHT,
                SW_BOM_TYPE_TOP_LEVEL_ONLY,
                "", bom_template, False,
                SW_INDENTED_NUMBERING_NONE, False,
            )
            gate("insert_B", bom_ann_b is not None and not isinstance(bom_ann_b, int),
                 f"type={type(bom_ann_b).__name__ if bom_ann_b else None}")
        except Exception as exc:
            gate("insert_B", False, f"raised: {repr(exc)[:100]}")

        # Insert BOM with empty template string
        print("\n--- BOM insert attempt C (template='') ---")
        bom_ann_c = None
        try:
            bom_ann_c = typed_view.InsertBomTable4(
                False, 0.05, 0.22,
                SW_TABLE_ANCHOR_TOP_LEFT,
                SW_BOM_TYPE_TOP_LEVEL_ONLY,
                "", "", False,
                SW_INDENTED_NUMBERING_NONE, False,
            )
            gate("insert_C", bom_ann_c is not None and not isinstance(bom_ann_c, int),
                 f"type={type(bom_ann_c).__name__ if bom_ann_c else None}")
        except Exception as exc:
            gate("insert_C", False, f"raised: {repr(exc)[:100]}")

        # H1: ForceRebuild3 — flush lazy population
        print("\n--- H1: ForceRebuild3 ---")
        try:
            imd2 = typed(doc_raw, "IModelDoc2", module=mod)
            rebuild_ok = imd2.ForceRebuild3(False)
            gate("h1_force_rebuild", bool(rebuild_ok), f"ForceRebuild3(False)={rebuild_ok}")
        except Exception as exc:
            gate("h1_force_rebuild", False, f"raised: {repr(exc)[:80]}")

        # Check table annotation count after all inserts + rebuild
        try:
            post_count = typed_view.GetTableAnnotationCount() or 0
            gate("post_rebuild_table_count", post_count > 0,
                 f"GetTableAnnotationCount={post_count}")
            results["characterization"]["post_rebuild_table_count"] = post_count
        except Exception as exc:
            gate("post_rebuild_table_count", False, f"raised: {repr(exc)[:80]}")

        # GetTableAnnotations — walk the array
        print("\n--- Walk table annotations array ---")
        try:
            ta_array = typed_view.GetTableAnnotations()
            if ta_array is not None:
                ta_list = list(ta_array) if hasattr(ta_array, '__iter__') else [ta_array]
                gate("table_annotations_array",
                     len(ta_list) > 0,
                     f"count={len(ta_list)}, types={[type(t).__name__ for t in ta_list[:3]]}")
                results["characterization"]["table_annotations"] = len(ta_list)
            else:
                gate("table_annotations_array", False, "GetTableAnnotations returned None")
        except Exception as exc:
            gate("table_annotations_array", False, f"raised: {repr(exc)[:100]}")

        # H2: probe IBomTableAnnotation objects directly
        print("\n--- H2: IBomTableAnnotation probe ---")
        for label, bom_ann in [("A", bom_ann_a), ("B", bom_ann_b), ("C", bom_ann_c)]:
            if bom_ann is not None and not isinstance(bom_ann, int):
                probe = _probe_bom_annotation(bom_ann)
                results["characterization"][f"probe_{label}"] = probe
                # Summarize key findings
                mpnc_row1 = probe.get("model_path_names_count_by_row", {}).get(1)
                cc2_row1 = probe.get("components_count2_by_row", {}).get(1)
                print(f"  probe_{label}: model_path_names_count[1]={mpnc_row1}, "
                      f"components_count2[1]={cc2_row1}")

        # Liveness: determine working annotation and its data rows
        # Use insert_A as primary; check which annotation has > 0 data
        winning_annotation = None
        winning_label = None
        for label, bom_ann in [("A", bom_ann_a), ("B", bom_ann_b), ("C", bom_ann_c)]:
            if bom_ann is None or isinstance(bom_ann, int):
                continue
            probe = results["characterization"].get(f"probe_{label}", {})
            # Check if row 1 has data
            mpnc_1 = probe.get("model_path_names_count_by_row", {}).get(1)
            cc2_1 = probe.get("components_count2_by_row", {}).get(1)
            # > 0 means data exists
            if isinstance(mpnc_1, int) and mpnc_1 > 0:
                winning_annotation = bom_ann
                winning_label = label
                break
            if isinstance(cc2_1, int) and cc2_1 > 0:
                winning_annotation = bom_ann
                winning_label = label
                break

        # Also try IGetBomTable on view after rebuild
        print("\n--- IGetBomTable probe (post-rebuild) ---")
        row_count_via_ibomtable = -1
        try:
            bom_table_raw = typed_view.IGetBomTable()
            if bom_table_raw is not None and not isinstance(bom_table_raw, int):
                bom_table = typed_qi(bom_table_raw, "IBomTable", module=mod)
                row_count_via_ibomtable = bom_table.GetRowCount() or 0
                col_count = bom_table.GetColumnCount() or 0
                data_rows = row_count_via_ibomtable - 1
                gate("ibomtable_row_count",
                     row_count_via_ibomtable > 0,
                     f"GetRowCount={row_count_via_ibomtable}, data_rows={data_rows}")
                results["characterization"]["ibomtable_row_count"] = row_count_via_ibomtable
                results["characterization"]["ibomtable_col_count"] = col_count
                results["characterization"]["ibomtable_data_rows"] = data_rows
            else:
                gate("ibomtable_row_count", False,
                     f"IGetBomTable returned {type(bom_table_raw).__name__ if bom_table_raw else None}")
        except Exception as exc:
            gate("ibomtable_row_count", False, f"raised: {repr(exc)[:120]}")
            results["characterization"]["ibomtable_error_v2"] = repr(exc)

        # Liveness gate
        data_rows = row_count_via_ibomtable - 1 if row_count_via_ibomtable > 0 else -1
        liveness_ok = data_rows > 0
        gate("LIVENESS_DATA_ROWS_GT_ZERO", liveness_ok,
             f"data_rows={data_rows} (row_count={row_count_via_ibomtable})")
        gate("LIVENESS_ROWS_EQ_COMPONENT_COUNT",
             data_rows == component_count,
             f"data_rows={data_rows}, component_count={component_count}")
        results["characterization"]["liveness_ok"] = liveness_ok

        # Save drawing
        try:
            doc_raw.SaveAs3(DRW_PATH, 0, 2)
            gate("drawing_save", os.path.isfile(DRW_PATH),
                 f"size={os.path.getsize(DRW_PATH) if os.path.isfile(DRW_PATH) else 0}")
        except Exception as exc:
            gate("drawing_save", False, f"SaveAs3 raised: {exc!r}")

        gate("OVERALL", liveness_ok and os.path.isfile(DRW_PATH),
             f"liveness={liveness_ok}, saved={os.path.isfile(DRW_PATH)}")
        return "GO" if liveness_ok else "NO-GO"

    finally:
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
        try:
            sw.CloseDoc(Path(ASM_PATH).name)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception as exc:
        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        verdict = "WALL"
    finally:
        results["verdict"] = verdict
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict in ("GO", "GREEN") else 1)
