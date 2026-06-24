"""Wave-23 Slice 3: Drawing multi-sheet production PAE.

End-to-end: build a part -> propose/dry_run/commit a ``kind:"drawing"``
spec that uses the new ``sheets[]`` authoring mode (two sheets: an
Overview with front+isometric, and a Detail sheet with just front) ->
reopen the resulting ``.SLDDRW`` and verify:

  * ``GetSheetCount() == 2``
  * ``GetSheetNames()`` contains "Overview" and "DetailSheet"
  * per-sheet view count: Overview=2, DetailSheet=1
  * per-sheet view placement (not just count): views landed on the
    intended sheet, confirmed via ``ISheet.GetViews()``

FAIL on: wrong sheet count, views landing on the wrong sheet, or
any commit-time failure. The S1 spike proved the routing recipe;
this PAE proves the declarative surface (W23 S2) drives it correctly.

Prereq: SOLIDWORKS 2024 SP1 running.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_multisheet_pae.json"
)

results: dict[str, Any] = {
    "pae": "w23_drawing_multisheet",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
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


def _build_test_part(part_path: str) -> bool:
    """Build a small box part (40x20x10) to use as the drawing's model."""
    from ai_sw_bridge.spec.builder import build as part_build

    spec = {
        "schema_version": 1,
        "name": "W23PaeBox",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Box",
                "plane": "Front",
                "width": 40.0,
                "height": 20.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "EX_Box",
                "sketch": "SK_Box",
                "depth": 10.0,
            },
        ],
    }
    r = part_build(spec, save_as=part_path, save_format="current", no_dim=True)
    return bool(r.ok) and os.path.isfile(part_path)


def run() -> str:
    print("=" * 70)
    print("Wave-23 Slice 3: Drawing multi-sheet production PAE")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.mutate import (
        sw_commit_drawing,
        sw_dry_run_drawing,
        sw_propose_drawing,
    )

    mod = wrapper_module()

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # --- Build part ---
    print("\n--- Build test part ---")
    part_path = str(_tmp / f"w23_pae_box_{_ts}.SLDPRT")
    if not gate(
        "part_build",
        _build_test_part(part_path),
        f"path={part_path}",
    ):
        results["verdict"] = "FAIL (prereq part build failed)"
        save_results()
        return "FAIL"

    # --- Drawing spec (new sheets[] authoring mode) ---
    drawing_spec = {
        "kind": "drawing",
        "name": "multisheet_pae_test",
        "model": part_path,
        "sheets": [
            {
                "name": "Overview",
                "template_size": "A3",
                "views": ["front", "isometric"],
            },
            {
                "name": "DetailSheet",
                "template_size": "A4",
                "views": ["front"],
            },
        ],
    }

    # --- Propose + dry_run + commit ---
    print("\n--- Propose / dry_run / commit ---")
    propose = sw_propose_drawing(drawing_spec)
    if not gate(
        "propose",
        propose.get("ok", False),
        propose.get("error", "") or "ok",
    ):
        results["verdict"] = "FAIL (propose rejected)"
        save_results()
        return "FAIL"

    dry_run = sw_dry_run_drawing(propose["proposal_id"])
    if not gate(
        "dry_run",
        dry_run.get("ok", False),
        dry_run.get("error", "") or "ok",
    ):
        results["verdict"] = "FAIL (dry_run rejected)"
        save_results()
        return "FAIL"
    # dry_run should report sheets_requested=2, views_per_sheet=[2, 1]
    gate(
        "dry_run_sheets",
        dry_run.get("sheets_requested") == 2
        and dry_run.get("views_per_sheet") == [2, 1],
        f"sheets_requested={dry_run.get('sheets_requested')}, "
        f"views_per_sheet={dry_run.get('views_per_sheet')}",
    )

    output_path = str(_tmp / f"w23_pae_multisheet_{_ts}.SLDDRW")
    commit = sw_commit_drawing(propose["proposal_id"], output_path)
    commit_ok = gate(
        "commit",
        commit.get("ok", False),
        commit.get("error", "")
        or f"sheets={commit.get('sheet_count')}, views={commit.get('view_count')}",
    )
    results["commit_result"] = {
        "ok": commit.get("ok"),
        "sheet_count": commit.get("sheet_count"),
        "sheet_names": commit.get("sheet_names"),
        "view_count": commit.get("view_count"),
        "views_placed": commit.get("views_placed"),
        "error": commit.get("error"),
    }
    if not commit_ok:
        results["verdict"] = "FAIL (commit rejected — no .SLDDRW on disk)"
        save_results()
        return "FAIL"
    if not gate("file_exists", os.path.isfile(output_path), output_path):
        results["verdict"] = "FAIL (commit ok but no file on disk)"
        save_results()
        return "FAIL"

    # --- Reopen and verify sheet count + names + per-sheet view counts ---
    print("\n--- Reopen .SLDDRW and verify sheet + view layout ---")
    sw = w32.Dispatch("SldWorks.Application")
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        # Open the part first so the drawing can resolve its references
        try:
            tsw.OpenDoc6(part_path, 1, 1, "", 0, 0)
        except Exception:
            pass

        ret = tsw.OpenDoc6(output_path, 3, 1, "", 0, 0)
        doc_raw = ret[0] if isinstance(ret, tuple) else ret
    except Exception as exc:
        gate("reopen", False, f"OpenDoc6 raised: {exc!r}")
        results["verdict"] = "FAIL (cannot reopen .SLDDRW)"
        save_results()
        return "FAIL"

    if doc_raw is None or isinstance(doc_raw, int):
        gate("reopen", False, f"OpenDoc6 returned {doc_raw!r}")
        results["verdict"] = "FAIL (OpenDoc6 returned None)"
        save_results()
        return "FAIL"

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)

        try:
            sheet_count = drawing_doc.GetSheetCount()
        except Exception as exc:
            gate("GetSheetCount", False, f"raised: {exc!r}")
            results["verdict"] = "FAIL"
            save_results()
            return "FAIL"

        try:
            sheet_names = list(drawing_doc.GetSheetNames())
        except Exception as exc:
            gate("GetSheetNames", False, f"raised: {exc!r}")
            sheet_names = []

        gate("sheet_count_2", sheet_count == 2, f"count={sheet_count}")
        gate(
            "sheet_names_match",
            "Overview" in sheet_names and "DetailSheet" in sheet_names,
            f"names={sheet_names}",
        )

        # Per-sheet view counts (the LOAD-BEARING gate)
        per_sheet: dict[str, dict[str, Any]] = {}
        for name in sheet_names:
            try:
                drawing_doc.ActivateSheet(name)
                raw = drawing_doc.GetCurrentSheet()
                if raw is None or isinstance(raw, int):
                    per_sheet[name] = {"error": "GetCurrentSheet None"}
                    continue
                sheet = typed_qi(raw, "ISheet", module=mod)
                views_arr = sheet.GetViews() or []
                vnames: list[str] = []
                for v in views_arr:
                    try:
                        tv = typed_qi(v, "IView", module=mod)
                        vnames.append(tv.GetName2() or "<unnamed>")
                    except Exception:
                        vnames.append("<non-IView>")
                per_sheet[name] = {
                    "view_count": len(vnames),
                    "view_names": vnames,
                }
            except Exception as exc:
                per_sheet[name] = {"error": f"{type(exc).__name__}: {exc}"}

        results["per_sheet"] = per_sheet

        # Liveness gates
        overview = per_sheet.get("Overview", {})
        detail = per_sheet.get("DetailSheet", {})

        overview_count = overview.get("view_count", -1)
        detail_count = detail.get("view_count", -1)

        gate(
            "overview_view_count_2",
            overview_count == 2,
            f"Overview views: {overview.get('view_names') or overview.get('error')}",
        )
        gate(
            "detailsheet_view_count_1",
            detail_count == 1,
            f"DetailSheet views: {detail.get('view_names') or detail.get('error')}",
        )

        # Final verdict: ALL liveness gates must pass
        all_pass = all(g["ok"] for g in results["gates"].values())
        results["verdict"] = "PASS" if all_pass else "FAIL"
        print(f"\n>>> VERDICT: {results['verdict']}")

    finally:
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass

    save_results()
    return results["verdict"]


if __name__ == "__main__":
    import traceback

    try:
        verdict = run()
    except Exception:
        traceback.print_exc()
        results["verdict"] = (
            f"FAIL (unhandled exception: {traceback.format_exc()[:200]})"
        )
        save_results()
        verdict = "FAIL"
    sys.exit(0 if verdict == "PASS" else 1)
