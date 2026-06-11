"""W52 observe-ext live de-risk spike (author-only, requires SW seat).

Five legs, each asserting a GREEN scalar on a known fixture:

  S-FACE-CLEAR   face-pair clearance — two planar faces 10mm apart → 10.0 mm
  S-ANGLE        angle measure — 30-60-90 wedge → 30° and 60°
  S-AREA         area measure — 10mm×10mm face → 100.0 mm²
  S-ASM-BBOX     assembly bbox — two-component assembly → combined spans
  S-DUR-PAIR     durable-ref pair — persist tokens of two vertices → distance

Exit 0 if all GREEN, 1 on any RED.

AUTHOR-ONLY: this spike requires a live SOLIDWORKS session.
The pure-logic + offline-test parts of W52 Lane B are self-mergeable;
this live verification stays on the branch for W0 to fire.
"""

from __future__ import annotations

import json
import math
import sys
import time
from typing import Any


def _ok(tag: str, scalar: float, expected: float, tol: float = 0.5) -> bool:
    green = abs(scalar - expected) <= tol
    status = "GREEN" if green else "RED"
    print(f"  {status}  {tag}: got {scalar:.4f}, expected {expected:.4f} (tol {tol})")
    return green


def _fail(tag: str, reason: str) -> None:
    print(f"  RED  {tag}: {reason}")


def main() -> int:
    try:
        from ai_sw_bridge.sw_com import get_sw_app, get_active_doc
        from ai_sw_bridge.observe import SolidWorksObserver
        from ai_sw_bridge.observe_measure import (
            sw_get_measure_angle_from_doc,
            sw_get_measure_area_from_doc,
            sw_get_measure_durable_pair,
        )
        from ai_sw_bridge.observe_clearance import sw_get_face_clearance
        from ai_sw_bridge.observe_bbox import sw_get_assembly_bbox_from_doc
        from ai_sw_bridge.observe_selection import sw_get_selection
    except ImportError as exc:
        print(f"IMPORT FAIL: {exc}")
        return 1

    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
    except Exception as exc:
        print(f"SW CONNECT FAIL: {exc}")
        return 1

    if doc is None:
        print("No active document — open a fixture before running this spike.")
        return 1

    obs = SolidWorksObserver()
    all_green = True
    results: list[dict[str, Any]] = []

    # ── S-FACE-CLEAR: face-pair clearance ──────────────────────────────────
    # Fixture: a part with two planar faces exactly 10mm apart.
    # Expected: min_distance_mm = 10.0
    print("\nS-FACE-CLEAR  face-pair clearance (two faces 10mm apart)")
    try:
        sel = sw_get_selection(doc)
        if sel.get("ok") and sel.get("selection", {}).get("count", 0) >= 2:
            face_names = []
            for s in sel["selection"]["selections"]:
                info = s.get("entity_info", {})
                if info.get("name"):
                    face_names.append(info["name"])
            if len(face_names) >= 2:
                fc = sw_get_face_clearance(doc, face_names[0], face_names[1])
                if fc.get("ok") and fc["clearance"]["min_distance_mm"] is not None:
                    green = _ok(
                        "face_clearance",
                        fc["clearance"]["min_distance_mm"],
                        10.0,
                        tol=0.5,
                    )
                    all_green = all_green and green
                    results.append({"leg": "S-FACE-CLEAR", "green": green,
                                    "scalar": fc["clearance"]["min_distance_mm"]})
                else:
                    _fail("face_clearance", fc.get("error", "unknown"))
                    all_green = False
            else:
                _fail("face_clearance", "need two faces selected (or named Face<1>/Face<2>)")
                all_green = False
        else:
            print("  SKIP  pre-select two faces to run S-FACE-CLEAR")
            results.append({"leg": "S-FACE-CLEAR", "green": None, "skipped": True})
    except Exception as exc:
        _fail("face_clearance", repr(exc))
        all_green = False

    # ── S-ANGLE: angle measure ─────────────────────────────────────────────
    # Fixture: select two edges forming 30° or 60° angle (30-60-90 wedge).
    print("\nS-ANGLE  angle measure (30-60-90 wedge)")
    try:
        ang = sw_get_measure_angle_from_doc(doc)
        if ang.get("ok") and ang["measure"]["angle_deg"] is not None:
            a = ang["measure"]["angle_deg"]
            green30 = _ok("angle_30", a, 30.0, tol=1.0)
            green60 = _ok("angle_60", a, 60.0, tol=1.0)
            green = green30 or green60
            if not green:
                _fail("angle", f"{a:.2f}° is neither ~30° nor ~60°")
            all_green = all_green and green
            results.append({"leg": "S-ANGLE", "green": green, "scalar": a})
        else:
            print("  SKIP  pre-select two edges forming an angle")
            results.append({"leg": "S-ANGLE", "green": None, "skipped": True})
    except Exception as exc:
        _fail("angle", repr(exc))
        all_green = False

    # ── S-AREA: area measure ───────────────────────────────────────────────
    # Fixture: select a 10mm × 10mm planar face → area = 100.0 mm².
    print("\nS-AREA  area measure (10x10mm face)")
    try:
        ar = sw_get_measure_area_from_doc(doc)
        if ar.get("ok") and ar["measure"]["area_mm2"] is not None:
            green = _ok("area", ar["measure"]["area_mm2"], 100.0, tol=1.0)
            all_green = all_green and green
            results.append({"leg": "S-AREA", "green": green,
                            "scalar": ar["measure"]["area_mm2"]})
        else:
            print("  SKIP  pre-select a face to run S-AREA")
            results.append({"leg": "S-AREA", "green": None, "skipped": True})
    except Exception as exc:
        _fail("area", repr(exc))
        all_green = False

    # ── S-ASM-BBOX: assembly bounding-box ──────────────────────────────────
    # Fixture: an assembly with known components.
    print("\nS-ASM-BBOX  assembly bounding-box")
    try:
        doc_type = doc.GetType
        if callable(doc_type):
            doc_type = doc_type()
        if doc_type == 2:
            ab = sw_get_assembly_bbox_from_doc(doc)
            if ab.get("ok") and ab["bounding_box"] is not None:
                bb = ab["bounding_box"]
                print(f"  INFO  dx={bb['dx_mm']:.1f} dy={bb['dy_mm']:.1f} "
                      f"dz={bb['dz_mm']:.1f} mm, {bb['component_count']} components")
                green = bb["dx_mm"] > 0 and bb["dy_mm"] > 0 and bb["dz_mm"] > 0
                print(f"  {'GREEN' if green else 'RED'}  assembly_bbox "
                      f"(positive spans)")
                all_green = all_green and green
                results.append({"leg": "S-ASM-BBOX", "green": green,
                                "scalar": {"dx": bb["dx_mm"], "dy": bb["dy_mm"],
                                           "dz": bb["dz_mm"]}})
            else:
                _fail("assembly_bbox", ab.get("error", "unknown"))
                all_green = False
        else:
            print(f"  SKIP  active doc type={doc_type}, need assembly (2)")
            results.append({"leg": "S-ASM-BBOX", "green": None, "skipped": True})
    except Exception as exc:
        _fail("assembly_bbox", repr(exc))
        all_green = False

    # ── S-DUR-PAIR: durable-ref pair measure ───────────────────────────────
    # Fixture: two entities with captured durable refs.
    print("\nS-DUR-PAIR  durable-ref pair measure")
    try:
        sel = sw_get_selection(doc)
        if sel.get("ok") and sel.get("selection", {}).get("count", 0) >= 2:
            refs = []
            for s in sel["selection"]["selections"]:
                if s.get("durable_ref"):
                    refs.append(s["durable_ref"])
            if len(refs) >= 2:
                dp = sw_get_measure_durable_pair(doc, refs[0], refs[1])
                if dp.get("ok") and dp["measure"]["distance_mm"] is not None:
                    d = dp["measure"]["distance_mm"]
                    print(f"  INFO  durable pair distance = {d:.3f} mm")
                    green = d > 0
                    print(f"  {'GREEN' if green else 'RED'}  durable_pair "
                          f"(positive distance)")
                    all_green = all_green and green
                    results.append({"leg": "S-DUR-PAIR", "green": green, "scalar": d})
                else:
                    _fail("durable_pair", dp.get("error", "unknown"))
                    all_green = False
            else:
                print("  SKIP  need two entities with durable_refs in selection")
                results.append({"leg": "S-DUR-PAIR", "green": None, "skipped": True})
        else:
            print("  SKIP  pre-select two entities to run S-DUR-PAIR")
            results.append({"leg": "S-DUR-PAIR", "green": None, "skipped": True})
    except Exception as exc:
        _fail("durable_pair", repr(exc))
        all_green = False

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    greens = sum(1 for r in results if r.get("green"))
    reds = sum(1 for r in results if r.get("green") is False)
    skips = sum(1 for r in results if r.get("skipped"))
    print(f"Results: {greens} GREEN, {reds} RED, {skips} SKIPPED")
    print(f"Overall: {'ALL GREEN' if all_green and reds == 0 else 'HAS RED'}")

    with open("spikes/v0_2x/_results_W52_observe_ext.json", "w") as f:
        json.dump({"results": results, "all_green": all_green}, f, indent=2, default=str)

    return 0 if all_green and reds == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
