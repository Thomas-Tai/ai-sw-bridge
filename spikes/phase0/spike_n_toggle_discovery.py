"""
Spike N - Discover which swUserPreferenceToggle ID actually suppresses
the AddDimension2 popup on SW 2024 SP1.

Background: Spike I (toggle 8 = swInputDimValOnCreate per CHM) failed to
suppress the popup. The toggle IDs are NOT necessarily ABI-stable across
SW versions; the SW 2024 swconst.tlb may have shuffled them.

This spike probes 4 candidate toggle IDs at runtime. For each candidate:
1. Snapshot the current value (so we can restore)
2. Set it to False
3. Open a fresh part
4. Sketch + circle + AddDimension2 (with a 5-second wall-time budget)
5. If AddDimension2 returns in < 2s, that toggle IS the one
6. Close the part WITHOUT saving
7. Restore the toggle

Candidate strategy: we try the four toggles whose NAME most plausibly
gates the Modify-Dimension popup, swept across plausible ID values.

Per the user's hint, we ALSO probe specific named IDs from common forum
advice (8, 78, 95, 167) regardless of name.

PASS: at least one toggle ID brings AddDimension2 to < 2s.
FAIL: all 4 still block > 5s. (Then pivot to spike L: skip AddDimension2.)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402


# Toggles to probe. Names are from the SW 2024 swconst CHM
# (swUserPreferenceToggle_e). Names alone don't give us IDs -- the SW CHM
# only shows names, not values -- so we probe a small set of common-forum
# IDs as a brute-force fallback.
#
# Why these IDs specifically:
#   8   -- swInputDimValOnCreate per old SW 2018 docs (Spike I confirmed
#          it does NOT work here, but include for control)
#   78  -- user's suggestion (claimed swSketchEnableOnScreenNumericInput)
#   95  -- common forum hit for "modify dim popup"
#   167 -- referenced in some SW 2024 release notes; speculative
CANDIDATE_IDS = [8, 78, 95, 167]


def probe_one_toggle(sw, toggle_id: int) -> dict:
    """Test a single toggle ID. Returns the timing result for AddDimension2."""
    # Snapshot before any change
    before = sw.GetUserPreferenceToggle(toggle_id)

    try:
        sw.SetUserPreferenceToggle(toggle_id, False)
        after_set = sw.GetUserPreferenceToggle(toggle_id)

        # Open a fresh part for this probe
        template = sw.GetUserPreferenceStringValue(8)
        if not template:
            return {"toggle_id": toggle_id, "status": "SKIP",
                    "error": "no default Part template"}
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        if doc is None:
            return {"toggle_id": toggle_id, "status": "SKIP",
                    "error": "NewDocument returned None"}

        try:
            if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
                return {"toggle_id": toggle_id, "status": "SKIP",
                        "error": "could not select Front Plane"}
            sm = doc.SketchManager
            sm.InsertSketch(True)
            sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)
            doc.ClearSelection2(True)
            if not doc.SelectByID("", "SKETCHSEGMENT", 0.005, 0.0, 0.0):
                return {"toggle_id": toggle_id, "status": "SKIP",
                        "error": "could not select circle for dim"}

            t0 = time.perf_counter()
            dim = doc.AddDimension2(0.010, 0.005, 0.0)
            elapsed_s = round(time.perf_counter() - t0, 3)

            sm.InsertSketch(True)  # close sketch

            # PASS if dim created AND returned in under 2 seconds
            ok = (dim is not None) and (elapsed_s < 2.0)
            return {
                "toggle_id": toggle_id,
                "status": "PASS" if ok else "BLOCKED",
                "before": before,
                "after_set_false": after_set,
                "add_dim2_elapsed_s": elapsed_s,
                "dim_was_none": dim is None,
            }
        finally:
            # Close the part without saving so we don't pile up windows
            sw.CloseDoc(doc.GetTitle if hasattr(doc, "GetTitle") else "")
    finally:
        # ALWAYS restore the snapshot, even on exception
        sw.SetUserPreferenceToggle(toggle_id, before)


def run_com() -> dict:
    sw = get_sw_app()
    results = []
    winner = None

    for tid in CANDIDATE_IDS:
        print(f"  probing toggle {tid} ... (this may block up to ~15s on FAIL)",
              file=sys.stderr, flush=True)
        try:
            r = probe_one_toggle(sw, tid)
        except Exception as e:
            r = {"toggle_id": tid, "status": "ERROR", "error": repr(e)}
        results.append(r)
        if r.get("status") == "PASS":
            winner = tid
            # Stop probing; we found it
            break

    overall = "PASS" if winner is not None else "FAIL"
    return {
        "status": overall,
        "winner_toggle_id": winner,
        "probes": results,
        "interpretation": (
            f"Toggle ID {winner} suppresses the AddDimension2 popup. "
            f"Patch builder.py to set this toggle False before any sketch dims."
            if winner is not None
            else "None of the probed toggles suppress the popup. "
                 "Pivot to spike L (numeric-resolve, no AddDimension2)."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com"], default="com")
    args = parser.parse_args()
    result = run_com()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
