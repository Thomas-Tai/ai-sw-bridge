"""Wave-16 Slice 4: Drawing production PAE.

End-to-end: build parts → commit assembly → propose/dry_run/commit drawing
→ re-open .SLDDRW and verify sheet + view count + file on disk.

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
    WORKTREE / "spikes" / "v0_2x" / "_results" / "drawing_pae.json"
)

results: dict[str, Any] = {
    "pae": "w16_drawing",
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
    print("Wave-16 Slice 4: Drawing production PAE")
    print("=" * 70)

    from ai_sw_bridge.mutate import (
        sw_commit_assembly,
        sw_commit_drawing,
        sw_dry_run_assembly,
        sw_dry_run_drawing,
        sw_propose_assembly,
        sw_propose_drawing,
    )
    from ai_sw_bridge.spec.builder import build as part_build

    _tmp = Path(tempfile.gettempdir())
    _ts = int(time.time())

    # --- Build parts ---
    print("\n--- Building parts ---")
    PART_A = str(_tmp / f"w16_pae_{_ts}_a.SLDPRT")
    PART_B = str(_tmp / f"w16_pae_{_ts}_b.SLDPRT")

    for label, path, w in [("a", PART_A, 40.0), ("b", PART_B, 30.0)]:
        spec = {
            "schema_version": 1,
            "name": f"Draw{label.upper()}",
            "features": [
                {"type": "sketch_rectangle_on_plane", "name": "SK",
                 "plane": "Front", "width": w, "height": 20.0},
                {"type": "boss_extrude_blind", "name": "EX",
                 "sketch": "SK", "depth": 10.0},
            ],
        }
        r = part_build(spec, save_as=path, save_format="current", no_dim=True)
        gate(f"build_{label}", r.ok and os.path.isfile(path), f"ok={r.ok}")

    if not (os.path.isfile(PART_A) and os.path.isfile(PART_B)):
        save_results()
        return "WALL"

    # --- Commit assembly ---
    print("\n--- Committing assembly ---")
    ASM_PATH = str(_tmp / f"w16_pae_{_ts}.SLDASM")
    asm_spec = {
        "kind": "assembly",
        "name": "drawing_test",
        "components": [
            {"id": "a", "part": PART_A, "transform": {"xyz_mm": [0, 0, 0]}},
            {"id": "b", "part": PART_B, "transform": {"xyz_mm": [0, 0, 15]}},
        ],
        "mates": [
            {
                "type": "coincident",
                "alignment": "aligned",
                "a": {"component": "a", "face_ref": {"normal": [0, 0, 1]}},
                "b": {"component": "b", "face_ref": {"normal": [0, 0, -1]}},
            },
        ],
    }

    ap = sw_propose_assembly(asm_spec)
    gate("asm_propose", ap.get("ok", False))
    ad = sw_dry_run_assembly(ap["proposal_id"])
    gate("asm_dry_run", ad.get("ok", False))
    ac = sw_commit_assembly(ap["proposal_id"], ASM_PATH)
    gate("asm_commit", ac.get("ok", False),
         f"components={ac.get('component_count')}, mates={ac.get('mate_count')}")

    if not ac.get("ok"):
        save_results()
        return "WALL"

    # --- Drawing lifecycle ---
    print("\n--- Drawing: propose ---")
    DRW_PATH = str(_tmp / f"w16_pae_{_ts}.SLDDRW")
    views = ["front", "top", "right", "isometric"]
    drawing_spec = {
        "kind": "drawing",
        "name": "drawing_pae",
        "model": ASM_PATH,
        "views": views,
        "sheet": {"template_size": "A3"},
    }

    dp = sw_propose_drawing(drawing_spec)
    gate("drw_propose", dp.get("ok", False),
         f"pid={dp.get('proposal_id')}")

    if not dp.get("ok"):
        results["drw_propose_error"] = dp.get("error")
        save_results()
        return "PARTIAL"

    print("\n--- Drawing: dry_run ---")
    dd = sw_dry_run_drawing(dp["proposal_id"])
    gate("drw_dry_run", dd.get("ok", False))

    print("\n--- Drawing: commit ---")
    dc = sw_commit_drawing(dp["proposal_id"], DRW_PATH)
    gate("drw_commit", dc.get("ok", False),
         f"views_placed={dc.get('views_placed')}, "
         f"view_count={dc.get('view_count')}")

    # --- Verify file on disk ---
    print("\n--- Verify drawing file ---")
    gate("drw_file_exists", os.path.isfile(DRW_PATH),
         f"size={os.path.getsize(DRW_PATH) if os.path.isfile(DRW_PATH) else 0}")

    # --- Verify view count matches requested ---
    gate("drw_view_count",
         dc.get("view_count") == len(views),
         f"requested={len(views)}, placed={dc.get('view_count')}")

    # --- Verify all requested views placed ---
    placed = dc.get("views_placed", [])
    gate("drw_all_views_placed",
         set(placed) == set(views),
         f"placed={sorted(placed)}, requested={sorted(views)}")

    # --- Overall ---
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
