"""W60 derisk spike — ``sketch_convert`` lane (Convert Entities, SketchUseEdge3).

The HIGHEST-RISK W60 sketch-editing lane: the seeds are MODEL edges, not
sketch segments, so this proves the durable-topology selection + Convert
round-trips across the OUT-OF-PROCESS marshaling boundary AND survives
save->reopen. W0 fires this on the singleton live seat (workers never run it).

Fixture (W0-owned ``_sketch_edit_fixtures``): extrude a 40x30x10 mm box
(``Sketch1`` -> Boss-Extrude1), open an EMPTY ``Sketch2`` on the top face, and
hand back one top-perimeter model edge. ``capture_edge_ref`` serializes it to a
DurableEdgeRef dict for the op's ``refs`` param. Converting that single edge
projects it onto the sketch plane -> +1 segment.

Verify-the-EFFECT (W21/W42 + the rib/move-copy no-op lesson):
  PASS  := SketchUseEdge3 reports ok AND segment_delta > 0 AND the new segment
           SURVIVES save->reopen.
  NO_OP := clean COM return but segment_delta == 0 — the out-of-process wall
           signature. STOP and report (per pause-on-errors); do NOT paper over.
  ERROR := fixture / harness failure.

Exit codes: 0 = PASS, 2 = NO_OP, 1 = ERROR.
"""

from __future__ import annotations

import json
import sys
import traceback

import _sketch_edit_fixtures as fx

from ai_sw_bridge.spec.sketch_editing import apply_sketch_edit, register
from ai_sw_bridge.spec.sketch_editing.convert import OP


def main() -> int:
    sw = fx.connect()
    try:
        register(OP)  # W0 hasn't wired __init__.py yet — register in the spike
        doc = fx.new_part(sw)

        sketch, edge = fx.build_box_top_sketch(doc)  # ("Sketch2", top edge)
        params = {"refs": [fx.capture_edge_ref(doc, edge)]}

        res = apply_sketch_edit(doc, sketch, "sketch_convert", params)

        # +1 segment expected (one edge converts to one new sketch segment).
        delta_ok = res["segments_after"] > res["segments_before"]

        doc2 = fx.save_and_reopen(sw, doc)
        n_reopen = fx.count_named_segments(doc2, sketch)
        survived = n_reopen == res["segments_after"]

        # NO_OP discrimination: a clean COM return (call_ok) with a ZERO segment
        # delta is the silent out-of-process wall (cf. rib / move-copy). It is
        # NOT a PASS and NOT a hard ERROR — exit 2, STOP, report to W0.
        verdict = (
            "PASS"
            if (res["ok"] and delta_ok and survived)
            else "NO_OP" if (res["call_ok"] and res["segment_delta"] == 0) else "FAIL"
        )

        print(
            json.dumps(
                {
                    "verdict": verdict,
                    "result": res,
                    "n_reopen": n_reopen,
                    "survived": survived,
                    "expected": {"segments_before": 0, "segments_after": 1, "delta": 1},
                },
                default=str,
                indent=2,
            )
        )
        return 0 if verdict == "PASS" else (2 if verdict == "NO_OP" else 1)
    except Exception as exc:  # noqa: BLE001 — spike top-level reporter
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
