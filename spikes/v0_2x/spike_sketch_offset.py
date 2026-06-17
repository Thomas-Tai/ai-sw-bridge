"""W60 derisk spike — ``sketch_offset`` (ISketchManager.SketchOffset2).

W0-FIRED on the live seat (DO NOT RUN offline — there is no seat here).

Builds its OWN fixture (a 4-segment corner rectangle on Front), registers the
offset OP (W0 hasn't wired ``__init__.py`` yet), and drives the production
orchestrator ``apply_sketch_edit`` with a 5 mm chained offset of all four
seeds. Verify-the-EFFECT is a sketch-segment COUNT delta that SURVIVES
save->reopen — a clean ``True`` return is never proof (the W21/W42 ghost trap).

Expected: a 4-segment rect, offset 5 mm (chain) -> the offset adds a second
closed loop, so ``segments_after > segments_before`` (>= +1; the orchestrator
records the exact delta), and the new count survives reopen.

Exit codes (per §5 / pause-on-errors):
  0 = PASS  — delta in the expected direction AND survived reopen.
  2 = NO_OP — clean COM return but ZERO segment delta (silent o-o-p wall;
              the rib/move-copy-body signature — STOP, report to W0).
  1 = ERROR — fixture/harness/COM exception.
"""

from __future__ import annotations

import json
import sys
import traceback

import _sketch_edit_fixtures as fx

from ai_sw_bridge.spec.sketch_editing import apply_sketch_edit, register
from ai_sw_bridge.spec.sketch_editing.offset import OP


def main() -> int:
    sw = fx.connect()
    try:
        register(OP)
        doc = fx.new_part(sw)
        sketch, n0 = fx.build_rect_sketch(doc)  # ("Sketch1", 4)
        params = {"distance_mm": 5, "entities": [0, 1, 2, 3], "chain": True}
        res = apply_sketch_edit(doc, sketch, "sketch_offset", params)

        delta_ok = res["segments_after"] > res["segments_before"]
        doc2 = fx.save_and_reopen(sw, doc)
        n_reopen = fx.count_named_segments(doc2, sketch)
        survived = n_reopen == res["segments_after"]

        verdict = (
            "PASS"
            if (res["ok"] and delta_ok and survived)
            else (
                "NO_OP"
                if res["call_ok"] and res["segment_delta"] == 0
                else "FAIL"
            )
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
