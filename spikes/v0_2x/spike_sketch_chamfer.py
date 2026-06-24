"""W61 derisk spike — ``sketch_chamfer`` (ISketchManager.CreateChamfer).

W0-FIRED on the live seat (DO NOT RUN offline — there is no seat here).

Builds its OWN fixture (a 4-segment corner rectangle on Front), registers the
chamfer OP (W0 hasn't wired ``__init__.py`` yet), and drives the production
orchestrator ``apply_sketch_edit`` with a 5 mm / 5 mm distance-distance chamfer
on two adjacent sides sharing a corner. Verify-the-EFFECT is a sketch-segment
COUNT delta that SURVIVES save->reopen — a clean ``True``/non-None return is
never proof (the W21/W42 ghost trap).

Expected: a 4-segment rect, chamfered at one corner -> the chamfer trims the
two sides and inserts a new line, net +1 segment (``segments_after == 5``),
and the new count survives reopen.

COM signature (DLL-verified, swSketchChamferType_e):
    CreateChamfer(int Type, double Distance, double DistAngleOrDist2) -> SketchSegment
  Type 1 = DistanceDistance, Type 2 = DistanceEqual. Type 0 (DistanceAngle)
  is out of scope (second arg is an angle in radians, not a distance).

Exit codes (per §5 / pause-on-errors):
  0 = PASS  — delta in the expected direction AND survived reopen.
  2 = NO_OP — clean COM return but ZERO segment delta (silent o-o-p wall;
              STOP, report to W0).
  1 = ERROR — fixture/harness/COM exception.
"""

from __future__ import annotations

import json
import sys
import traceback

import _sketch_edit_fixtures as fx

from ai_sw_bridge.spec.sketch_editing import apply_sketch_edit, register
from ai_sw_bridge.spec.sketch_editing.chamfer import OP


def main() -> int:
    sw = fx.connect()
    try:
        register(OP)
        doc = fx.new_part(sw)
        sketch, n0 = fx.build_rect_sketch(doc)  # ("Sketch1", 4)
        params = {"chamfer_type": 1, "dist1_mm": 5, "dist2_mm": 5, "entities": [0, 1]}
        res = apply_sketch_edit(doc, sketch, "sketch_chamfer", params)

        delta_ok = res["segments_after"] > res["segments_before"]
        doc2 = fx.save_and_reopen(sw, doc)
        n_reopen = fx.count_named_segments(doc2, sketch)
        survived = n_reopen == res["segments_after"]

        verdict = (
            "PASS"
            if (res["ok"] and delta_ok and survived)
            else ("NO_OP" if res["call_ok"] and res["segment_delta"] == 0 else "FAIL")
        )
        print(
            json.dumps(
                {
                    "verdict": verdict,
                    "result": res,
                    "n_initial": n0,
                    "n_reopen": n_reopen,
                    "survived": survived,
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
