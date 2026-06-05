"""Wave-17 Slice 3: Drawing dimensions production PAE.

End-to-end: build dimensioned part -> propose/dry_run/commit drawing with
dimensions:true -> re-open .SLDDRW and verify annotation count > 0.

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
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_dims_pae.json"
)

POPUP_SUPPRESS_TOGGLES = [9, 10, 22, 23]

results: dict[str, Any] = {
    "pae": "w17_drawing_dims",
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
    print("Wave-17 Slice 3: Drawing dimensions production PAE")
    print("=" * 70)

    import win32com.client as w32

    from ai_sw_bridge.com.earlybind import typed, typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.mutate import (
        sw_commit_drawing,
        sw_dry_run_drawing,
        sw_propose_drawing,
    )
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

    # Suppress dimension popups
    print("\n--- Suppressing dimension popups ---")
    for tid in POPUP_SUPPRESS_TOGGLES:
        try:
            sw.SetUserPreferenceToggle(tid, False)
        except Exception:
            pass
    gate("popup_suppressed", True, f"toggles={POPUP_SUPPRESS_TOGGLES}")

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # Build dimensioned part
    print("\n--- Building dimensioned part ---")
    PART_PATH = str(_tmp / f"w17_pae_{_ts}_dimbox.SLDPRT")
    PART_SPEC = {
        "schema_version": 1,
        "name": "PaeDimBox",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK",
             "plane": "Front", "width": 40.0, "height": 25.0},
            {"type": "boss_extrude_blind", "name": "EX",
             "sketch": "SK", "depth": 15.0},
        ],
    }

    r = part_build(PART_SPEC, save_as=PART_PATH, save_format="current",
                   no_dim=False)
    gate("build_dim_part", r.ok and os.path.isfile(PART_PATH),
         f"ok={r.ok}")

    if not os.path.isfile(PART_PATH):
        save_results()
        return "WALL"

    # Drawing lifecycle with dimensions:true
    print("\n--- Drawing: propose ---")
    DRW_PATH = str(_tmp / f"w17_pae_{_ts}.SLDDRW")
    drawing_spec = {
        "kind": "drawing",
        "name": "dims_pae",
        "model": PART_PATH,
        "views": ["front", "top", "right", "isometric"],
        "dimensions": True,
        "sheet": {"template_size": "A3"},
    }

    dp = sw_propose_drawing(drawing_spec)
    gate("drw_propose", dp.get("ok", False),
         f"pid={dp.get('proposal_id')}")

    if not dp.get("ok"):
        results["propose_error"] = dp.get("error")
        save_results()
        return "PARTIAL"

    print("\n--- Drawing: dry_run ---")
    dd = sw_dry_run_drawing(dp["proposal_id"])
    gate("drw_dry_run", dd.get("ok", False))

    print("\n--- Drawing: commit ---")
    dc = sw_commit_drawing(dp["proposal_id"], DRW_PATH)
    gate("drw_commit", dc.get("ok", False),
         f"views={dc.get('views_placed')}, "
         f"annotations={dc.get('total_annotations')}")

    # Verify file on disk
    print("\n--- Verify drawing ---")
    gate("drw_file_exists", os.path.isfile(DRW_PATH),
         f"size={os.path.getsize(DRW_PATH) if os.path.isfile(DRW_PATH) else 0}")

    # Verify dimensions were inserted
    dims_inserted = dc.get("dimensions_inserted", False)
    total_annots = dc.get("total_annotations", 0)
    gate("dimensions_inserted", dims_inserted,
         f"dimensions_inserted={dims_inserted}")
    gate("annotations_gt_zero", total_annots > 0,
         f"total_annotations={total_annots}")

    # Re-open drawing and verify annotations persist
    print("\n--- Re-open and verify ---")
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        ret = tsw.OpenDoc6(DRW_PATH, 3, 1, "", 0, 0)
        drw_doc = ret[0] if isinstance(ret, tuple) else ret

        if drw_doc:
            drw_typed = typed_qi(drw_doc, "IDrawingDoc", module=mod)
            # Walk all views (GetFirstView returns sheet; GetNextView
            # traverses model views)
            reopen_total = 0
            view_count = 0
            try:
                v = drw_typed.GetFirstView()
                while v is not None:
                    tv = typed_qi(v, "IView", module=mod)
                    try:
                        ac = tv.GetAnnotationCount()
                        reopen_total += ac if ac else 0
                    except Exception:
                        pass
                    view_count += 1
                    try:
                        v = tv.GetNextView()
                    except Exception:
                        break
            except Exception as e:
                gate("reopen_walk", False, str(e)[:80])

            gate("reopen_annotations",
                 reopen_total > 0,
                 f"views={view_count}, total_annotations={reopen_total}")

            try:
                t = drw_doc.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass
        else:
            gate("reopen_drawing", False, "OpenDoc6 returned None")
    except Exception as e:
        gate("reopen_drawing", False, str(e)[:80])

    # Overall
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
