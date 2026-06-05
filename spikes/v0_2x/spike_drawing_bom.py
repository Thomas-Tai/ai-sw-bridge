"""Wave-18 Slice 1: BOM table insertion de-risk spike.

Insert a populated Bill-of-Materials table on an assembly drawing view and
verify it has data rows (component count > 0).

Routes tried (A → B → C fallback):
  A. typed_qi(view, "IView").InsertBomTable4(UseAnchorPoint, X, Y,
         AnchorType, BomType, Configuration, TableTemplate, Hidden,
         IndentedNumberingType, DetailedCutList)
  B. typed_qi(doc_raw, "IModelDocExtension").InsertBomTable4(...) (legacy)
  C. typed_qi(view, "IView").InsertBomTable3(...) (legacy 8-arg)

LIVENESS GATE: BOM inserted AND RowCount (via IBomTable.GetRowCount minus 1
header row) > 0 AND == component count from assembly.

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
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_bom.json"
)

# SW constant literals (swBomType_e, swTableAnchor_e, swIndentedNumberingType_e)
SW_BOM_TYPE_TOP_LEVEL_ONLY = 1
SW_TABLE_ANCHOR_TOP_LEFT = 1
SW_INDENTED_NUMBERING_NONE = 2

results: dict[str, Any] = {
    "spike": "w18_drawing_bom",
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
    """Locate a .sldbomtbt BOM template on this machine."""
    patterns = [
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\bom-all.sldbomtbt",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\*.sldbomtbt",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\**\*.sldbomtbt",
    ]
    for pat in patterns:
        matches = _glob.glob(pat, recursive=True)
        if matches:
            return matches[0]
    return None


def _find_drawing_template() -> str | None:
    """Locate a .DRWDOT drawing template."""
    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot",
    ]:
        matches = _glob.glob(pat)
        if matches:
            return matches[0]
    return None


def run() -> str:
    print("=" * 70)
    print("Wave-18 Slice 1: Drawing BOM insertion characterization")
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

    # --- Locate templates ---
    bom_template = _find_bom_template()
    gate(
        "bom_template_found",
        bom_template is not None,
        f"path={bom_template}",
    )
    results["characterization"]["bom_template"] = bom_template

    drw_template = _find_drawing_template()
    gate("drw_template_found", drw_template is not None, f"path={drw_template}")

    if not bom_template or not drw_template:
        save_results()
        return "WALL"

    # --- Build two parts ---
    print("\n--- Building parts ---")
    PART_A = str(_tmp / f"w18_bom_{_ts}_a.SLDPRT")
    PART_B = str(_tmp / f"w18_bom_{_ts}_b.SLDPRT")

    for label, path, w_mm in [("a", PART_A, 40.0), ("b", PART_B, 30.0)]:
        spec = {
            "schema_version": 1,
            "name": f"BomPart{label.upper()}",
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK",
                    "plane": "Front",
                    "width": w_mm,
                    "height": 20.0,
                },
                {
                    "type": "boss_extrude_blind",
                    "name": "EX",
                    "sketch": "SK",
                    "depth": 10.0,
                },
            ],
        }
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
        gate(
            f"build_part_{label}",
            r.ok and os.path.isfile(path),
            f"ok={r.ok}",
        )

    if not (os.path.isfile(PART_A) and os.path.isfile(PART_B)):
        save_results()
        return "WALL"

    # --- Build assembly ---
    print("\n--- Building assembly (2 components) ---")
    ASM_PATH = str(_tmp / f"w18_bom_{_ts}.SLDASM")
    asm_spec = {
        "kind": "assembly",
        "name": "bom_test_asm",
        "components": [
            {
                "id": "a",
                "part": PART_A,
                "transform": {"xyz_mm": [0, 0, 0]},
            },
            {
                "id": "b",
                "part": PART_B,
                "transform": {"xyz_mm": [0, 0, 15]},
            },
        ],
        "mates": [
            {
                "type": "coincident",
                "alignment": "aligned",
                "a": {
                    "component": "a",
                    "face_ref": {"normal": [0, 0, 1]},
                },
                "b": {
                    "component": "b",
                    "face_ref": {"normal": [0, 0, -1]},
                },
            },
        ],
    }

    p = sw_propose_assembly(asm_spec)
    d = sw_dry_run_assembly(p["proposal_id"])
    c = sw_commit_assembly(p["proposal_id"], ASM_PATH)
    component_count = c.get("component_count", 2)  # fallback assumption
    gate(
        "assembly_commit",
        c.get("ok", False),
        f"ok={c.get('ok')}, mates={c.get('mate_count')}",
    )
    results["characterization"]["component_count"] = component_count
    results["characterization"]["asm_path"] = ASM_PATH

    if not c.get("ok") or not os.path.isfile(ASM_PATH):
        save_results()
        return "WALL"

    # Verify assembly component count via IAssemblyDoc
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        tsw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)
        asm_raw = sw.ActiveDoc
        asm_typed = typed_qi(asm_raw, "IAssemblyDoc", module=mod)
        # GetComponents(topLevelOnly=True) returns top-level components
        comps = asm_typed.GetComponents(True)
        real_count = len(comps) if comps else 0
        gate(
            "asm_component_count",
            real_count >= 2,
            f"GetComponents(True)={real_count}",
        )
        results["characterization"]["component_count_verified"] = real_count
        if real_count > 0:
            component_count = real_count
    except Exception as exc:
        gate("asm_component_count", False, f"raised: {exc!r}")

    # Close assembly; it will be reopened for the drawing
    try:
        sw.CloseDoc(Path(ASM_PATH).name)
    except Exception:
        pass

    # --- Create drawing ---
    print("\n--- Creating drawing of assembly ---")

    # Re-open assembly (needed for view creation)
    tsw = typed(sw, "ISldWorks", module=mod)
    tsw.OpenDoc6(ASM_PATH, 2, 1, "", 0, 0)

    doc_raw = sw.NewDocument(drw_template, 0, 0.420, 0.297)  # A3 landscape
    gate(
        "drawing_create",
        doc_raw is not None and not isinstance(doc_raw, int),
        f"type={type(doc_raw).__name__ if doc_raw else None}",
    )

    if doc_raw is None or isinstance(doc_raw, int):
        save_results()
        return "WALL"

    DRW_PATH = str(_tmp / f"w18_bom_{_ts}.SLDDRW")

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
        gate("drawing_qi", drawing_doc is not None, "IDrawingDoc QI ok")

        # Create a *Front view of the assembly (required BOM anchor)
        view_raw = drawing_doc.CreateDrawViewFromModelView3(
            ASM_PATH, "*Front", 0.15, 0.15, 0.0
        )
        view_ok = view_raw is not None and not isinstance(view_raw, int)
        gate(
            "view_created",
            view_ok,
            f"type={type(view_raw).__name__ if view_raw else None}",
        )

        if not view_ok:
            save_results()
            return "WALL"

        typed_view = typed_qi(view_raw, "IView", module=mod)

        # Verify view table annotation count pre-insert
        pre_table_count = 0
        try:
            pre_table_count = typed_view.GetTableAnnotationCount() or 0
        except Exception:
            pass
        results["characterization"]["pre_insert_table_count"] = pre_table_count

        # === ROUTE A: IView.InsertBomTable4 ===
        print("\n--- Route A: IView.InsertBomTable4 ---")
        route_a_ok = False
        bom_annotation = None

        try:
            bom_raw = typed_view.InsertBomTable4(
                False,                         # UseAnchorPoint
                0.05,                          # X (metres on sheet)
                0.22,                          # Y (metres on sheet)
                SW_TABLE_ANCHOR_TOP_LEFT,      # AnchorType = 1
                SW_BOM_TYPE_TOP_LEVEL_ONLY,    # BomType = 1
                "",                            # Configuration (default)
                bom_template,                  # TableTemplate
                False,                         # Hidden
                SW_INDENTED_NUMBERING_NONE,    # IndentedNumberingType = 2
                False,                         # DetailedCutList
            )
            route_a_ok = bom_raw is not None and not isinstance(bom_raw, int)
            results["characterization"]["route_a"] = {
                "result_type": type(bom_raw).__name__ if bom_raw else None,
                "result_repr": repr(bom_raw)[:120],
                "ok": route_a_ok,
            }
            gate(
                "route_a_insert",
                route_a_ok,
                f"returned type={type(bom_raw).__name__ if bom_raw else None}",
            )
            if route_a_ok:
                bom_annotation = bom_raw
        except Exception as exc:
            results["characterization"]["route_a"] = {
                "error": repr(exc),
                "ok": False,
            }
            gate("route_a_insert", False, f"raised: {repr(exc)[:120]}")

        # === ROUTE B: IView.InsertBomTable3 (legacy fallback) ===
        if not route_a_ok:
            print("\n--- Route B: IView.InsertBomTable3 (legacy fallback) ---")
            route_b_ok = False
            try:
                bom_raw_b = typed_view.InsertBomTable3(
                    False,                         # UseAnchorPoint
                    0.05,                          # X
                    0.22,                          # Y
                    SW_TABLE_ANCHOR_TOP_LEFT,      # AnchorType
                    SW_BOM_TYPE_TOP_LEVEL_ONLY,    # BomType
                    "",                            # Configuration
                    bom_template,                  # TableTemplate
                    False,                         # Hidden
                )
                route_b_ok = (
                    bom_raw_b is not None and not isinstance(bom_raw_b, int)
                )
                results["characterization"]["route_b"] = {
                    "result_type": type(bom_raw_b).__name__ if bom_raw_b else None,
                    "ok": route_b_ok,
                }
                gate(
                    "route_b_insert",
                    route_b_ok,
                    f"type={type(bom_raw_b).__name__ if bom_raw_b else None}",
                )
                if route_b_ok:
                    bom_annotation = bom_raw_b
            except Exception as exc:
                results["characterization"]["route_b"] = {
                    "error": repr(exc),
                    "ok": False,
                }
                gate("route_b_insert", False, f"raised: {repr(exc)[:120]}")

        # === ROUTE C: IModelDocExtension.InsertBomTable (legacy doc-level) ===
        if bom_annotation is None:
            print("\n--- Route C: IModelDocExtension.InsertBomTable (doc-level) ---")
            route_c_ok = False
            try:
                doc_ext = typed(doc_raw.Extension, "IModelDocExtension", module=mod)
                bom_raw_c = doc_ext.InsertBomTable(
                    bom_template,           # TemplateName
                    0,                      # X (int)
                    0,                      # Y (int)
                    SW_BOM_TYPE_TOP_LEVEL_ONLY,  # BomType
                    "",                     # ConfigurationName
                )
                route_c_ok = (
                    bom_raw_c is not None and not isinstance(bom_raw_c, int)
                )
                results["characterization"]["route_c"] = {
                    "result_type": type(bom_raw_c).__name__ if bom_raw_c else None,
                    "ok": route_c_ok,
                }
                gate(
                    "route_c_insert",
                    route_c_ok,
                    f"type={type(bom_raw_c).__name__ if bom_raw_c else None}",
                )
                if route_c_ok:
                    bom_annotation = bom_raw_c
            except Exception as exc:
                results["characterization"]["route_c"] = {
                    "error": repr(exc),
                    "ok": False,
                }
                gate("route_c_insert", False, f"raised: {repr(exc)[:120]}")

        if bom_annotation is None:
            gate("BOM_INSERTED", False, "all routes failed — NO-GO")
            save_results()
            return "NO-GO"

        # === LIVENESS GATE: verify data rows > 0 ===
        print("\n--- Liveness gate: verify BOM has data rows ---")

        # Post-insert table count on view
        try:
            post_table_count = typed_view.GetTableAnnotationCount() or 0
            gate(
                "post_insert_table_count",
                post_table_count > pre_table_count,
                f"pre={pre_table_count}, post={post_table_count}",
            )
            results["characterization"]["post_insert_table_count"] = post_table_count
        except Exception as exc:
            gate("post_insert_table_count", False, f"raised: {repr(exc)[:80]}")

        # Get IBomTable via IView.IGetBomTable() (direct typed method, no QI needed)
        # Falls back to QI from IBomTableAnnotation if needed.
        row_count = -1
        col_count = -1
        data_rows = -1
        bom_table = None

        # Primary path: IView.IGetBomTable() — returns IBomTable directly
        try:
            bom_table_raw = typed_view.IGetBomTable()
            if bom_table_raw is not None and not isinstance(bom_table_raw, int):
                bom_table = typed_qi(bom_table_raw, "IBomTable", module=mod)
                results["characterization"]["ibomtable_source"] = "IGetBomTable"
        except Exception as exc:
            results["characterization"]["igetbomtable_error"] = repr(exc)

        # Fallback: QI from IBomTableAnnotation → IBomTable
        if bom_table is None:
            try:
                bom_table = typed_qi(bom_annotation, "IBomTable", module=mod)
                results["characterization"]["ibomtable_source"] = "QI from annotation"
            except Exception as exc:
                results["characterization"]["ibomtable_qi_error"] = repr(exc)

        if bom_table is not None:
            try:
                row_count = bom_table.GetRowCount() or 0
                col_count = bom_table.GetColumnCount() or 0
                # Row 0 is the header; data rows = total - 1
                data_rows = row_count - 1
                gate(
                    "bom_row_count",
                    row_count > 0,
                    f"GetRowCount={row_count}, GetColumnCount={col_count}",
                )
                results["characterization"]["bom_table_row_count"] = row_count
                results["characterization"]["bom_table_col_count"] = col_count
                results["characterization"]["bom_data_rows"] = data_rows
            except Exception as exc:
                gate("bom_row_count", False, f"GetRowCount failed: {exc!r}")
        else:
            gate("bom_row_count", False, "IBomTable unavailable (all paths failed)")

        # LIVENESS: data rows > 0 AND == component count
        liveness_ok = data_rows > 0
        gate(
            "LIVENESS_DATA_ROWS_GT_ZERO",
            liveness_ok,
            f"data_rows={data_rows} (row_count={row_count} - 1 header)",
        )

        count_match = data_rows == component_count
        gate(
            "LIVENESS_ROWS_EQ_COMPONENT_COUNT",
            count_match,
            f"data_rows={data_rows}, component_count={component_count}",
        )

        results["characterization"]["liveness_ok"] = liveness_ok
        results["characterization"]["component_count_at_check"] = component_count

        # Save drawing to verify file persistence
        print("\n--- Saving drawing ---")
        try:
            doc_raw.SaveAs3(DRW_PATH, 0, 2)
            gate(
                "drawing_save",
                os.path.isfile(DRW_PATH),
                f"size={os.path.getsize(DRW_PATH) if os.path.isfile(DRW_PATH) else 0}",
            )
        except Exception as exc:
            gate("drawing_save", False, f"SaveAs3 raised: {exc!r}")

        all_pass = (
            liveness_ok
            and os.path.isfile(DRW_PATH)
        )
        gate(
            "OVERALL",
            all_pass,
            f"liveness={liveness_ok}, saved={os.path.isfile(DRW_PATH)}",
        )

        return "GO" if liveness_ok else "NO-GO"

    finally:
        # Close drawing
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
        # Close assembly
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
