"""Wave-19 Slice 3: Section + Detail view production PAE.

End-to-end: build part with internal pocket -> propose/dry_run/commit
drawing with section view A (vertical) + detail view B -> re-open
.SLDDRW, verify view count >= 3 and both section (type=2) and detail
(type=3) views are present.

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

# Guard against charmap crashes from Unicode COM return values (W19 S1 lesson)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = (
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_section_detail_pae.json"
)

# Empirical IView.Type values confirmed by W19 S1 spike
SW_VIEW_TYPE_SECTION = 2
SW_VIEW_TYPE_DETAIL = 3

results: dict[str, Any] = {
    "pae": "w19_drawing_section_detail",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "confirmed_type_constants": {
        "section": SW_VIEW_TYPE_SECTION,
        "detail": SW_VIEW_TYPE_DETAIL,
        "source": "W19 S1 spike empirical",
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


def run() -> str:
    print("=" * 70)
    print("Wave-19 Slice 3: Section + Detail view production PAE")
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

    # Suppress dimension popups (precaution from W17)
    for tid in [9, 10, 22, 23]:
        try:
            sw.SetUserPreferenceToggle(tid, False)
        except Exception:
            pass

    # Close stale docs
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

    # --- Build part with internal pocket (creates U-shaped cross-section) ---
    print("\n--- Building part ---")
    PART_PATH = str(_tmp / f"w19pae_{_ts}.SLDPRT")
    part_spec = {
        "schema_version": 1,
        "name": "W19PaeDemo",
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_BOX",
                "plane": "Front",
                "width": 40.0,
                "height": 30.0,
            },
            {
                "type": "boss_extrude_blind",
                "name": "BOSS",
                "sketch": "SK_BOX",
                "depth": 15.0,
            },
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_CUT",
                "plane": "Top",
                "width": 20.0,
                "height": 10.0,
            },
            {
                "type": "cut_extrude_blind",
                "name": "POCKET",
                "sketch": "SK_CUT",
                "depth": 15.0,
            },
        ],
    }
    r = part_build(part_spec, save_as=PART_PATH, save_format="current", no_dim=True)
    part_ok = r.ok and os.path.isfile(PART_PATH)
    gate("part_build", part_ok, f"ok={r.ok}, path={PART_PATH}")
    if not part_ok:
        results["part_error"] = str(getattr(r, "error", "unknown"))
        save_results()
        return "WALL"

    results["part_path"] = PART_PATH

    # --- Drawing spec with section + detail ---
    DRW_PATH = str(_tmp / f"w19pae_{_ts}.SLDDRW")
    drawing_spec = {
        "kind": "drawing",
        "name": "w19_sec_det_pae",
        "model": PART_PATH,
        "views": [
            "front",
            {
                "type": "section",
                "name": "A",
                "parent": "front",
                "cut": "vertical",
            },
            {
                "type": "detail",
                "name": "B",
                "parent": "front",
                "center": [0.5, 0.5],
                "radius": 0.25,
            },
        ],
        "sheet": {"template_size": "A3"},
    }
    results["drawing_spec"] = drawing_spec

    # --- Propose ---
    print("\n--- Drawing lifecycle: propose ---")
    dp = sw_propose_drawing(drawing_spec)
    gate(
        "drw_propose",
        dp.get("ok", False),
        f"pid={dp.get('proposal_id')}, err={dp.get('error')}",
    )
    if not dp.get("ok"):
        results["propose_error"] = dp.get("error")
        save_results()
        return "PARTIAL"

    # --- Dry run ---
    print("\n--- Drawing lifecycle: dry_run ---")
    dd = sw_dry_run_drawing(dp["proposal_id"])
    gate(
        "drw_dry_run",
        dd.get("ok", False),
        f"state={dd.get('state')}, err={dd.get('error')}",
    )
    if not dd.get("ok"):
        results["dry_run_error"] = dd.get("error")
        save_results()
        return "PARTIAL"

    # --- Commit ---
    print("\n--- Drawing lifecycle: commit ---")
    dc = sw_commit_drawing(dp["proposal_id"], DRW_PATH)
    gate(
        "drw_commit",
        dc.get("ok", False),
        f"view_count={dc.get('view_count')}, "
        f"views={dc.get('views_placed')}, "
        f"err={dc.get('error')}",
    )
    if not dc.get("ok"):
        results["commit_error"] = dc.get("error")
        results["commit_view_errors"] = dc.get("view_errors")
        save_results()
        return "PARTIAL"

    views_placed = dc.get("views_placed") or []
    view_count = dc.get("view_count", 0)
    results["views_placed"] = views_placed
    results["view_count"] = view_count

    gate(
        "commit_view_count_ge_3",
        view_count >= 3,
        f"view_count={view_count} (front + section A + detail B)",
    )

    # Check that section and detail names appear in views_placed
    has_section = any(
        "section" in str(n).lower() or "A" in str(n)
        for n in views_placed
        if str(n).lower() != "front"
    )
    has_detail = any(
        "detail" in str(n).lower() or "B" in str(n)
        for n in views_placed
        if str(n).lower() != "front"
    )
    gate("commit_has_section_view", has_section, f"views_placed={views_placed}")
    gate("commit_has_detail_view", has_detail, f"views_placed={views_placed}")

    # --- File on disk ---
    drw_size = os.path.getsize(DRW_PATH) if os.path.isfile(DRW_PATH) else 0
    gate("drw_file_exists", os.path.isfile(DRW_PATH), f"size={drw_size}")
    results["drawing_path"] = DRW_PATH

    # --- Re-open drawing: verify view types ---
    print("\n--- Re-open drawing and verify view types ---")
    reopen_section_count = 0
    reopen_detail_count = 0
    reopen_total_model_views = 0

    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        # Open the part first so the drawing can resolve its references
        tsw.OpenDoc6(PART_PATH, 1, 1, "", 0, 0)

        ret = tsw.OpenDoc6(DRW_PATH, 3, 1, "", 0, 0)
        drw_doc = ret[0] if isinstance(ret, tuple) else ret

        if drw_doc is None:
            gate("reopen_drawing", False, "OpenDoc6 returned None")
        else:
            gate("reopen_drawing", True, f"type={type(drw_doc).__name__}")
            drw_typed = typed_qi(drw_doc, "IDrawingDoc", module=mod)

            view_types_seen: list[int] = []
            view_names_seen: list[str] = []

            try:
                v = drw_typed.GetFirstView()
                while v is not None:
                    tv = typed_qi(v, "IView", module=mod)
                    try:
                        vn = tv.GetName2() or ""
                        vt_raw = tv.Type
                        vt = int(vt_raw) if vt_raw is not None else -1
                        view_names_seen.append(vn)
                        view_types_seen.append(vt)
                        if vt == SW_VIEW_TYPE_SECTION:
                            reopen_section_count += 1
                        elif vt == SW_VIEW_TYPE_DETAIL:
                            reopen_detail_count += 1
                        # Count non-sheet views (sheet view name is usually "Sheet1")
                        if vn and not vn.lower().startswith("sheet"):
                            reopen_total_model_views += 1
                    except Exception:
                        pass
                    try:
                        v = tv.GetNextView()
                    except Exception:
                        break
            except Exception as exc:
                gate("reopen_walk", False, str(exc)[:80])

            results["reopen_view_names"] = view_names_seen
            results["reopen_view_types"] = view_types_seen
            print(f"    views found: {list(zip(view_names_seen, view_types_seen))}")

            gate(
                "reopen_total_model_views_ge_3",
                reopen_total_model_views >= 3,
                f"non-sheet views={reopen_total_model_views}",
            )
            gate(
                "reopen_has_section_type",
                reopen_section_count >= 1,
                f"section (type={SW_VIEW_TYPE_SECTION}) count={reopen_section_count}",
            )
            gate(
                "reopen_has_detail_type",
                reopen_detail_count >= 1,
                f"detail (type={SW_VIEW_TYPE_DETAIL}) count={reopen_detail_count}",
            )

            try:
                t = drw_doc.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
            except Exception:
                pass

    except Exception as exc:
        gate("reopen_drawing", False, str(exc)[:120])

    # --- Overall ---
    all_pass = all(g["ok"] for g in results["gates"].values())
    gate(
        "OVERALL_GREEN",
        all_pass,
        f"{sum(1 for g in results['gates'].values() if g['ok'])}/"
        f"{len(results['gates'])} gates pass",
    )

    return "GREEN" if all_pass else "PARTIAL"


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception as exc:
        import traceback

        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        results["unexpected_traceback"] = traceback.format_exc()
        verdict = "WALL"
    finally:
        results["verdict"] = verdict
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict == "GREEN" else 1)
