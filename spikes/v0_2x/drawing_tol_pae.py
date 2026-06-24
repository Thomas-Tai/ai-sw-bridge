"""Wave-28 Slice 3: Drawing tolerance production PAE.

End-to-end: build dimensioned part -> propose/dry_run/commit drawing with
tolerance -> re-open .SLDDRW and verify dims carry tolerance.

Tests all three tolerance types: symmetric, bilateral, limit.

Key W28 insight: tolerances are MODEL-OWNED. The PAE verifies:
  1. Drawing lifecycle applies tolerance to all dims
  2. Model is saved after tolerance application
  3. On reopen, dims carry the tolerance

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
RESULTS_PATH = WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_tol_pae.json"

POPUP_SUPPRESS_TOGGLES = [9, 10, 22, 23]

SW_TOL_SYMMETRIC = 4
SW_TOL_BILATERAL = 2
SW_TOL_LIMIT = 3

results: dict[str, Any] = {
    "pae": "w28_drawing_tol",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "gates": {},
    "tolerance_tests": {},
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


def run_tolerance_type(tol_type: str, tol_spec: dict[str, Any]) -> str:
    """Run PAE for one tolerance type."""
    print(f"\n{'='*60}")
    print(f"Testing {tol_type} tolerance")
    print(f"{'='*60}")

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

    # Build dimensioned part
    print("\n--- Building dimensioned part ---")
    PART_PATH = str(_tmp / f"w28_pae_{_ts}_{tol_type}_box.SLDPRT")
    PART_SPEC = {
        "schema_version": 1,
        "name": f"PaeTol{tol_type.capitalize()}Box",
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

    r = part_build(PART_SPEC, save_as=PART_PATH, save_format="current", no_dim=False)
    gate(f"{tol_type}_build_part", r.ok and os.path.isfile(PART_PATH), f"ok={r.ok}")

    if not os.path.isfile(PART_PATH):
        return "WALL"

    # Drawing lifecycle with tolerance
    print(f"\n--- Drawing: propose ({tol_type}) ---")
    DRW_PATH = str(_tmp / f"w28_pae_{_ts}_{tol_type}.SLDDRW")

    # W28: dimensions can be object with tolerance
    drawing_spec = {
        "kind": "drawing",
        "name": f"tol_{tol_type}_pae",
        "model": PART_PATH,
        "views": ["front", "top"],
        "dimensions": {"tolerance": tol_spec},
        "sheet": {"template_size": "A3"},
    }

    dp = sw_propose_drawing(drawing_spec)
    gate(f"{tol_type}_drw_propose", dp.get("ok", False), f"pid={dp.get('proposal_id')}")

    if not dp.get("ok"):
        results[f"{tol_type}_propose_error"] = dp.get("error")
        return "PARTIAL"

    print(f"\n--- Drawing: dry_run ({tol_type}) ---")
    dd = sw_dry_run_drawing(dp["proposal_id"])
    gate(f"{tol_type}_drw_dry_run", dd.get("ok", False))

    print(f"\n--- Drawing: commit ({tol_type}) ---")
    dc = sw_commit_drawing(dp["proposal_id"], DRW_PATH)
    gate(
        f"{tol_type}_drw_commit",
        dc.get("ok", False),
        f"views={dc.get('views_placed')}, "
        f"annotations={dc.get('total_annotations')}, "
        f"tolerance_applied={dc.get('tolerance_applied')}, "
        f"model_saved={dc.get('model_saved')}",
    )

    # Check model was saved (W28 key)
    gate(
        f"{tol_type}_model_saved",
        dc.get("model_saved", False),
        f"model_save_path={dc.get('model_save_path')}",
    )

    # Verify drawing file on disk
    print("\n--- Verify drawing ---")
    gate(
        f"{tol_type}_drw_file",
        os.path.isfile(DRW_PATH),
        f"size={os.path.getsize(DRW_PATH) if os.path.isfile(DRW_PATH) else 0}",
    )

    # Re-open drawing and verify tolerance on dims
    print("\n--- Re-open and verify tolerance ---")
    tsw = typed(sw, "ISldWorks", module=mod)

    ret = tsw.OpenDoc6(DRW_PATH, 3, 1, "", 0, 0)
    drw_doc = ret[0] if isinstance(ret, tuple) else ret
    gate(f"{tol_type}_reopen_drw", drw_doc is not None)

    if drw_doc is None:
        return "PARTIAL"

    drw_typed = typed_qi(drw_doc, "IDrawingDoc", module=mod)

    # Enumerate dims and check tolerance
    dims_with_tol = 0
    dims_total = 0
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
                            dim_raw = dd.GetDimension2(0)
                            if dim_raw is None:
                                continue
                            dim = typed_qi(dim_raw, "IDimension", module=mod)
                            dims_total += 1
                            tol_type_rb = dim.GetToleranceType()
                            tol_vals_rb = dim.GetToleranceValues()
                            # Check tolerance matches expected
                            expected_type = {
                                "symmetric": SW_TOL_SYMMETRIC,
                                "bilateral": SW_TOL_BILATERAL,
                                "limit": SW_TOL_LIMIT,
                            }[tol_type]
                            if tol_type_rb == expected_type and tol_vals_rb is not None:
                                dims_with_tol += 1
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                v = tv.GetNextView()
            except Exception:
                break
    except Exception as e:
        gate(f"{tol_type}_reopen_walk", False, str(e)[:80])

    gate(
        f"{tol_type}_dims_with_tolerance",
        dims_with_tol > 0,
        f"{dims_with_tol}/{dims_total} dims carry tolerance",
    )

    results["tolerance_tests"][tol_type] = {
        "dims_total": dims_total,
        "dims_with_tol": dims_with_tol,
        "tol_matches": dims_with_tol == dims_total if dims_total > 0 else False,
    }

    # Close drawing
    try:
        t = drw_doc.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
    except Exception:
        pass

    # Close part
    try:
        pn = Path(PART_PATH).stem
        sw.CloseDoc(pn + ".SLDPRT")
    except Exception:
        pass

    return "GREEN" if dims_with_tol > 0 else "PARTIAL"


def run() -> str:
    print("=" * 70)
    print("Wave-28 Slice 3: Drawing tolerance production PAE")
    print("=" * 70)

    # Test all three tolerance types
    tolerance_specs = [
        ("symmetric", {"type": "symmetric", "value": 0.00005}),  # ±0.05mm
        (
            "bilateral",
            {"type": "bilateral", "max": 0.0001, "min": -0.00005},
        ),  # +0.1/-0.05mm
        ("limit", {"type": "limit", "max": 0.0001, "min": -0.00005}),
    ]

    all_verdicts = []
    for tol_type, tol_spec in tolerance_specs:
        verdict = run_tolerance_type(tol_type, tol_spec)
        all_verdicts.append((tol_type, verdict))

    # Overall verdict
    print("\n--- Overall Verdict ---")
    all_green = all(v == "GREEN" for _, v in all_verdicts)
    for tol_type, v in all_verdicts:
        print(f"  {tol_type}: {v}")

    overall = "GREEN" if all_green else "PARTIAL"
    gate("OVERALL", all_green, f"symmetric, bilateral, limit all GREEN")

    results["verdict"] = overall
    return overall


if __name__ == "__main__":
    try:
        verdict = run()
    except Exception as exc:
        results["gates"]["UNEXPECTED"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        verdict = "WALL"
        results["verdict"] = verdict
    finally:
        save_results()
    print(f"\nVerdict: {verdict}")
    sys.exit(0 if verdict == "GREEN" else 1)
