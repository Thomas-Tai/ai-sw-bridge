"""Seat-proof: ``sketch_circular_pattern`` (CreateCircularSketchStepAndRepeat).

W0 fires this on the live SOLIDWORKS seat (workers have no seat — DO NOT RUN).

Fixture: a closed sketch with one Ø6 mm circle whose CENTRE is 20 mm from the
sketch origin (``Sketch1``, 1 segment).  A 4-instance circular step-and-repeat
around the origin (``entities=[0]``, ``num=4``, ``radius_mm=20``,
``arc_angle_deg=360``) rotates that seed to 0/90/180/270 deg, so the sketch
should hold 4 segments afterwards (+3).

Verify-the-EFFECT (the W21/W42 ghost trap): success is the sketch-segment
COUNT delta that SURVIVES save->reopen — never the COM ``True`` return.

Exit codes: 0 = PASS, 2 = NO_OP, 1 = ERROR.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

import _sketch_edit_fixtures as fx
from ai_sw_bridge.spec.sketch_editing import (
    apply_sketch_edit,
)  # OP auto-registered via package import


def _build_offset_circle_sketch(doc: Any) -> tuple[str, int]:
    """Ø6 mm circle centred 20 mm from the origin -> closed Sketch1 (1 seg)."""
    fx._open_sketch_on_plane(doc, "Front Plane")
    # CreateCircle(cx, cy, cz, px, py, pz): centre (20mm,0), point-on (23mm,0) -> r=3mm
    doc.SketchManager.CreateCircle(0.020, 0.0, 0.0, 0.023, 0.0, 0.0)
    fx._close_sketch(doc)
    return "Sketch1", 1


def main() -> int:
    sw = fx.connect()
    try:
        doc = fx.new_part(sw)
        sketch, n0 = _build_offset_circle_sketch(doc)

        params = {"entities": [0], "num": 4, "radius_mm": 20.0, "arc_angle_deg": 360.0}
        res = apply_sketch_edit(doc, sketch, "sketch_circular_pattern", params)

        delta_ok = res["segments_after"] > res["segments_before"]  # expect +3 -> 4
        doc2 = fx.save_and_reopen(sw, doc)
        n_reopen = fx.count_named_segments(doc2, sketch)
        survived = n_reopen == res["segments_after"]

        verdict = (
            "PASS"
            if (res["ok"] and delta_ok and survived)
            else (
                "NO_OP"
                if res.get("call_ok") and res.get("segment_delta") == 0
                else "FAIL"
            )
        )
        print(
            json.dumps(
                {
                    "verdict": verdict,
                    "result": res,
                    "n_reopen": n_reopen,
                    "survived": survived,
                    "expected_segments_after": 4,
                },
                default=str,
                indent=2,
            )
        )
        return 0 if verdict == "PASS" else (2 if verdict == "NO_OP" else 1)
    except Exception as exc:  # noqa: BLE001 — spike top-level guard
        print(
            json.dumps(
                {
                    "verdict": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                    "tb": traceback.format_exc(),
                },
                default=str,
            )
        )
        return 1
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
