"""Wave-18 Slice 1 FINAL: BOM insertion definitive run.

Confirmed working route (from v1+v2 characterization):
  IView.InsertBomTable4(UseAnchorPoint, X, Y, AnchorType, BomType,
      Configuration, TableTemplate, Hidden, IndentedNumberingType,
      DetailedCutList) → IBomTableAnnotation

Confirmed liveness probe: IBomTableAnnotation.GetComponentsCount2(rowIdx, "")
  - Returns (count, itemNumber, partNumber) tuple
  - Row 0 is always header (count == 0); data rows start at 1
  - Iterate from row 1 until count == 0 to get total data row count

Dead paths (characterization record only):
  - IView.GetTableAnnotationCount() does NOT count BOM tables → always 0
  - IView.GetTableAnnotations() → None for BOM tables
  - IView.IGetBomTable() → SW DISP_E_EXCEPTION "Unable to read write-only property"
  - IBomTableAnnotation QI to IBomTable → E_NOINTERFACE

Template source: glob C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\lang\\english\\*.sldbomtbt

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
# Write to the canonical drawing_bom.json (S1 definitive result)
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_bom.json"
)

SW_BOM_TYPE_TOP_LEVEL_ONLY = 1   # swBomType_TopLevelOnly
SW_TABLE_ANCHOR_TOP_LEFT = 1     # swTableAnchor_TopLeft
SW_INDENTED_NUMBERING_NONE = 2   # swIndentedNumberingType_None

results: dict[str, Any] = {
    "spike": "w18_drawing_bom_v3_definitive",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "characterization": {
        "dead_paths": {
            "GetTableAnnotationCount": "always 0 for BOM tables",
            "GetTableAnnotations": "returns None for BOM tables",
            "IGetBomTable": "SW error 61836 Unable to read write-only property",
            "IBomTable_QI": "E_NOINTERFACE — IBomTableAnnotation != IBomTable",
        }
    },
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


def _count_bom_data_rows(bom_annotation: Any) -> int:
    """Count data rows via IBomTableAnnotation.GetComponentsCount2 iterator.

    Row 0 is the header (count == 0). Data rows start at index 1.
    Returns the number of data rows with at least 1 component.
    """
    data_rows = 0
    for row_idx in range(1, 256):  # generous upper bound
        try:
            result = bom_annotation.GetComponentsCount2(row_idx, "")
            # Returns (count, itemNumber, partNumber)
            count = result[0] if isinstance(result, (list, tuple)) else result
            if not count:
                break
            data_rows += 1
        except Exception:
            break
    return data_rows


def run() -> str:
    print("=" * 70)
    print("Wave-18 Slice 1 FINAL: Drawing BOM insertion — definitive run")
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
    results["characterization"]["bom_template_source"] = bom_template
    results["characterization"]["bom_template_glob"] = (
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\*.sldbomtbt"
    )

    if not bom_template or not drw_template:
        save_results()
        return "WALL"

    # Build 2 parts + assemble
    print("\n--- Building 2-component assembly ---")
    PART_A = str(_tmp / f"w18v3_{_ts}_a.SLDPRT")
    PART_B = str(_tmp / f"w18v3_{_ts}_b.SLDPRT")

    for label, path, w_mm in [("a", PART_A, 40.0), ("b", PART_B, 30.0)]:
        spec = {
            "schema_version": 1,
            "name": f"BomV3{label.upper()}",
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

    ASM_PATH = str(_tmp / f"w18v3_{_ts}.SLDASM")
    c = sw_commit_assembly(
        sw_dry_run_assembly(
            sw_propose_assembly({
                "kind": "assembly",
                "name": "bom_v3_asm",
                "components": [
                    {"id": "a", "part": PART_A, "transform": {"xyz_mm": [0, 0, 0]}},
                    {"id": "b", "part": PART_B, "transform": {"xyz_mm": [0, 0, 15]}},
                ],
                "mates": [
                    {"type": "coincident", "alignment": "aligned",
                     "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
                     "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}}},
                ],
            })["proposal_id"]
        )["proposal_id"],
        ASM_PATH
    )
    component_count = c.get("component_count") or 2
    gate("assembly_commit", c.get("ok", False), f"components={component_count}")
    results["characterization"]["component_count"] = component_count
    results["characterization"]["asm_path"] = ASM_PATH

    if not c.get("ok") or not os.path.isfile(ASM_PATH):
        save_results()
        return "WALL"

    # Create drawing + view
    print("\n--- Drawing + view of assembly ---")
    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)

    doc_raw = sw.NewDocument(drw_template, 0, 0.420, 0.297)
    gate("drawing_create", doc_raw is not None and not isinstance(doc_raw, int),
         f"type={type(doc_raw).__name__ if doc_raw else None}")
    if doc_raw is None or isinstance(doc_raw, int):
        save_results()
        return "WALL"

    DRW_PATH = str(_tmp / f"w18v3_{_ts}.SLDDRW")

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

        # Activate view before BOM insert (H3, confirmed beneficial)
        try:
            view_name = typed_view.GetName2() or "Drawing View1"
            drawing_doc.ActivateView(view_name)
        except Exception:
            pass

        # INSERT BOM — Route A: IView.InsertBomTable4
        print("\n--- Insert BOM: IView.InsertBomTable4 ---")
        print(f"  signature (CONFIRMED): InsertBomTable4("
              f"UseAnchorPoint:bool, X:float, Y:float, AnchorType:int, "
              f"BomType:int, Configuration:str, TableTemplate:str, "
              f"Hidden:bool, IndentedNumberingType:int, DetailedCutList:bool"
              f") -> IBomTableAnnotation")
        print(f"  template: {bom_template}")

        bom_annotation = typed_view.InsertBomTable4(
            False,                         # UseAnchorPoint
            0.05,                          # X metres on sheet
            0.22,                          # Y metres on sheet
            SW_TABLE_ANCHOR_TOP_LEFT,      # AnchorType = 1
            SW_BOM_TYPE_TOP_LEVEL_ONLY,    # BomType = 1 (swBomType_TopLevelOnly)
            "",                            # Configuration (default)
            bom_template,                  # TableTemplate path
            False,                         # Hidden
            SW_INDENTED_NUMBERING_NONE,    # IndentedNumberingType = 2
            False,                         # DetailedCutList
        )
        bom_ok = (
            bom_annotation is not None and not isinstance(bom_annotation, int)
        )
        gate("bom_inserted", bom_ok,
             f"returned type={type(bom_annotation).__name__ if bom_annotation else None}")

        results["characterization"]["working_route"] = "IView.InsertBomTable4"
        results["characterization"]["signature"] = (
            "InsertBomTable4(UseAnchorPoint:bool, X:float, Y:float, "
            "AnchorType:int, BomType:int, Configuration:str, "
            "TableTemplate:str, Hidden:bool, IndentedNumberingType:int, "
            "DetailedCutList:bool) -> IBomTableAnnotation"
        )
        results["characterization"]["dispid"] = 414  # from typelib

        if not bom_ok:
            save_results()
            return "NO-GO"

        # LIVENESS GATE: IBomTableAnnotation.GetComponentsCount2 iterator
        print("\n--- Liveness gate: GetComponentsCount2 iterator ---")
        data_rows = _count_bom_data_rows(bom_annotation)
        gate("bom_data_rows_gt_zero", data_rows > 0,
             f"data_rows={data_rows}")

        # Detailed row data for the results JSON
        row_data: list[dict[str, Any]] = []
        for row_idx in range(1, data_rows + 1):
            try:
                r = bom_annotation.GetComponentsCount2(row_idx, "")
                count = r[0] if isinstance(r, (list, tuple)) else r
                item = r[1] if isinstance(r, (list, tuple)) and len(r) > 1 else ""
                part = r[2] if isinstance(r, (list, tuple)) and len(r) > 2 else ""
                row_data.append({
                    "row_index": row_idx,
                    "component_count": count,
                    "item_number": item,
                    "part_number": part,
                })
            except Exception:
                break

        results["characterization"]["bom_row_data"] = row_data
        results["characterization"]["bom_data_rows"] = data_rows
        results["characterization"]["component_count"] = component_count
        print(f"  BOM rows: {data_rows}, assembly components: {component_count}")

        count_match = data_rows == component_count
        gate("bom_rows_eq_component_count", count_match,
             f"data_rows={data_rows}, component_count={component_count}")

        # Save drawing
        print("\n--- Saving drawing ---")
        doc_raw.SaveAs3(DRW_PATH, 0, 2)
        gate("drawing_save", os.path.isfile(DRW_PATH),
             f"size={os.path.getsize(DRW_PATH) if os.path.isfile(DRW_PATH) else 0}")
        results["characterization"]["drawing_path"] = DRW_PATH

        liveness_ok = data_rows > 0
        gate("OVERALL_GO", liveness_ok and os.path.isfile(DRW_PATH),
             f"BOM data_rows={data_rows}/{component_count} components, "
             f"file={os.path.isfile(DRW_PATH)}")

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
    sys.exit(0 if verdict == "GO" else 1)
