"""W60 derisk spike: ``sketch_pattern`` (CreateLinearSketchStepAndRepeat).

W0 fires this on the live SOLIDWORKS seat (workers have no seat — DO NOT RUN).

Fixture (shared W0-owned helper): a closed sketch with one Ø10 mm circle
(``Sketch1``, 1 segment). A 3x1 linear step-and-repeat of that seed
(``entities=[0]``, ``spacing_x_mm=20``) multiplies it into 3 instances, so the
sketch should hold 3 segments afterwards (+2).

Verify-the-EFFECT (the W21/W42 ghost trap): success is the sketch-segment
COUNT delta that SURVIVES save->reopen — never the COM ``True`` return.
  PASS  := res.ok AND segments_after > segments_before AND survives reopen.
  NO_OP := clean COM return but segment_delta == 0 (the o-o-p wall signature,
           cf. rib / move-copy-body) — exit 2, surface for joint diagnosis.
  ERROR := fixture/harness failure — exit 1.

Exit codes: 0 = PASS, 2 = NO_OP, 1 = ERROR.
"""

from __future__ import annotations

import json
import sys
import traceback

import _sketch_edit_fixtures as fx
from ai_sw_bridge.spec.sketch_editing import apply_sketch_edit, register
from ai_sw_bridge.spec.sketch_editing.pattern import OP


def main() -> int:
    sw = fx.connect()
    try:
        register(OP)  # W0 hasn't wired __init__.py yet — register in the spike
        doc = fx.new_part(sw)
        sketch, n0 = fx.build_circle_sketch(doc)  # ("Sketch1", 1)

        params = {"entities": [0], "num_x": 3, "num_y": 1, "spacing_x_mm": 20}
        res = apply_sketch_edit(doc, sketch, "sketch_pattern", params)

        delta_ok = res["segments_after"] > res["segments_before"]  # expect +2 -> 3
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
                    "n_reopen": n_reopen,
                    "survived": survived,
                    "expected_segments_after": 3,
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
