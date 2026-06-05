"""Wave-18 Slice 3: Drawing BOM production PAE.

End-to-end: build 2-component assembly → propose/dry_run/commit drawing
with bom:true → re-open .SLDDRW, verify BOM table exists with data row
count == component count (> 0).

Prereq: SOLIDWORKS 2024 SP1 running.
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
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_bom_pae.json"
)

results: dict[str, Any] = {
    "pae": "w18_drawing_bom",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
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


def run() -> str:
    print("=" * 70)
    print("Wave-18 Slice 3: Drawing BOM production PAE")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.drawing.lifecycle import _count_bom_data_rows
    from ai_sw_bridge.mutate import (
        sw_commit_assembly,
        sw_commit_drawing,
        sw_dry_run_assembly,
        sw_dry_run_drawing,
        sw_propose_assembly,
        sw_propose_drawing,
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

    # Suppress dimension popups (precaution from W17)
    for tid in [9, 10, 22, 23]:
        try:
            sw.SetUserPreferenceToggle(tid, False)
        except Exception:
            pass

    # --- Build 2-component assembly ---
    print("\n--- Building 2-component assembly ---")
    PART_A = str(_tmp / f"w18pae_{_ts}_a.SLDPRT")
    PART_B = str(_tmp / f"w18pae_{_ts}_b.SLDPRT")

    for label, path, w_mm in [("a", PART_A, 40.0), ("b", PART_B, 30.0)]:
        spec = {
            "schema_version": 1,
            "name": f"PaeBom{label.upper()}",
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

    ASM_PATH = str(_tmp / f"w18pae_{_ts}.SLDASM")
    asm_spec = {
        "kind": "assembly",
        "name": "bom_pae_asm",
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

    pa = sw_propose_assembly(asm_spec)
    da = sw_dry_run_assembly(pa["proposal_id"])
    ca = sw_commit_assembly(pa["proposal_id"], ASM_PATH)
    component_count = ca.get("component_count") or 2
    gate("asm_commit", ca.get("ok", False),
         f"components={component_count}, mates={ca.get('mate_count')}")

    if not ca.get("ok") or not os.path.isfile(ASM_PATH):
        save_results()
        return "WALL"

    results["component_count"] = component_count

    # --- Propose drawing with bom:true ---
    print("\n--- Drawing lifecycle: propose ---")
    DRW_PATH = str(_tmp / f"w18pae_{_ts}.SLDDRW")
    drawing_spec = {
        "kind": "drawing",
        "name": "bom_pae",
        "model": ASM_PATH,
        "views": ["front", "isometric"],
        "bom": True,
        "sheet": {"template_size": "A3"},
    }

    dp = sw_propose_drawing(drawing_spec)
    gate("drw_propose", dp.get("ok", False),
         f"pid={dp.get('proposal_id')}")

    if not dp.get("ok"):
        results["propose_error"] = dp.get("error")
        save_results()
        return "PARTIAL"

    print("\n--- Drawing lifecycle: dry_run ---")
    dd = sw_dry_run_drawing(dp["proposal_id"])
    gate("drw_dry_run", dd.get("ok", False))

    print("\n--- Drawing lifecycle: commit ---")
    dc = sw_commit_drawing(dp["proposal_id"], DRW_PATH)
    gate("drw_commit", dc.get("ok", False),
         f"views={dc.get('views_placed')}, "
         f"bom_inserted={dc.get('bom_inserted')}, "
         f"bom_data_rows={dc.get('bom_data_rows')}")

    if not dc.get("ok"):
        results["commit_error"] = dc.get("error")
        save_results()
        return "PARTIAL"

    bom_data_rows_commit = dc.get("bom_data_rows", 0)
    gate("bom_data_rows_gt_zero_commit",
         bom_data_rows_commit > 0,
         f"bom_data_rows={bom_data_rows_commit}")
    gate("bom_data_rows_eq_components",
         bom_data_rows_commit == component_count,
         f"bom_data_rows={bom_data_rows_commit}, component_count={component_count}")

    # --- File on disk ---
    print("\n--- Verify drawing file ---")
    drw_size = (
        os.path.getsize(DRW_PATH) if os.path.isfile(DRW_PATH) else 0
    )
    gate("drw_file_exists", os.path.isfile(DRW_PATH), f"size={drw_size}")
    results["drawing_path"] = DRW_PATH

    # --- Re-open drawing and verify BOM rows ---
    print("\n--- Re-open drawing and verify BOM ---")
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        ret = tsw.OpenDoc6(DRW_PATH, 3, 1, "", 0, 0)
        drw_doc = ret[0] if isinstance(ret, tuple) else ret

        if drw_doc:
            drw_typed = typed_qi(drw_doc, "IDrawingDoc", module=mod)

            # Walk views looking for a BOM via IView.GetBomTable() (late-bound
            # Dispatch path, dispid 108). Then QI to IBomTableAnnotation to
            # use _count_bom_data_rows — the confirmed working probe.
            # NOTE: IGetBomTable() (dispid 109) fails with SW error 61836;
            #       IView.GetTableAnnotationCount() always 0 for BOM tables.
            reopen_bom_rows = 0
            reopen_errors: list[str] = []
            try:
                v = drw_typed.GetFirstView()
                while v is not None:
                    tv = typed_qi(v, "IView", module=mod)
                    try:
                        bom_raw = tv.GetBomTable()
                        if bom_raw is not None and not isinstance(bom_raw, int):
                            try:
                                bom_ann = typed_qi(
                                    bom_raw, "IBomTableAnnotation", module=mod
                                )
                                rows = _count_bom_data_rows(bom_ann)
                                if rows > 0:
                                    reopen_bom_rows = rows
                            except Exception as exc2:
                                reopen_errors.append(
                                    f"IBomTableAnnotation QI: {exc2!r}"[:80]
                                )
                    except Exception as exc3:
                        reopen_errors.append(f"GetBomTable: {exc3!r}"[:80])
                    try:
                        v = tv.GetNextView()
                    except Exception:
                        break
            except Exception as exc:
                gate("reopen_walk", False, str(exc)[:80])

            if reopen_errors:
                results["reopen_probe_errors"] = reopen_errors

            gate("reopen_bom_rows_gt_zero",
                 reopen_bom_rows > 0,
                 f"reopen_bom_rows={reopen_bom_rows}")
            gate("reopen_bom_rows_eq_components",
                 reopen_bom_rows == component_count,
                 f"reopen_bom_rows={reopen_bom_rows}, component_count={component_count}")
            results["reopen_bom_rows"] = reopen_bom_rows

            try:
                t = drw_doc.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
        else:
            gate("reopen_drawing", False, "OpenDoc6 returned None")
    except Exception as exc:
        gate("reopen_drawing", False, str(exc)[:80])

    # Overall: commit bom_data_rows > 0 and file on disk are the load-bearing gates
    all_pass = all(g["ok"] for g in results["gates"].values())
    gate("OVERALL_GREEN", all_pass,
         f"{sum(1 for g in results['gates'].values() if g['ok'])}/"
         f"{len(results['gates'])} gates pass")

    return "GREEN" if all_pass else "PARTIAL"


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
    sys.exit(0 if verdict == "GREEN" else 1)
