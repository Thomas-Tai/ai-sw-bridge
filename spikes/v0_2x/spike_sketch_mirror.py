"""W61 derisk spike — ``sketch_mirror`` (IModelDoc2.SketchMirror).

W0-FIRED on the live seat (DO NOT RUN offline — there is no seat here).

Builds the W0 mirror-seed fixture (a vertical centerline + an L of two lines
on the +X side, 3 segments total), registers the mirror OP (W0 hasn't wired
``__init__.py`` yet), and drives the production orchestrator
``apply_sketch_edit``. SketchMirror() takes NO args — it mirrors the selected
entities about the selected centerline. The W0 mirror fixture returns
``("Sketch1", 3, [1, 2], 0)`` so the spike passes ``entities=[1,2],
centerline=0``.

Verify-the-EFFECT is a sketch-segment COUNT delta that SURVIVES save->reopen —
a clean ``True``/void return is never proof (the W21/W42 ghost trap).

Expected: 3-segment seed, mirror the two +X lines about the Y centerline ->
adds two -X copies, so ``segments_after > segments_before`` (3->5, delta +2),
and the new count survives reopen.

Exit codes (per §5 / pause-on-errors):
  0 = PASS  — delta in the expected direction AND survived reopen.
  2 = NO_OP — clean COM return but ZERO segment delta (likely the centerline
              selection-mark protocol — STOP, report to W0 who fixes on seat).
  1 = ERROR — fixture/harness/COM exception.
"""

from __future__ import annotations

import json
import sys
import traceback

import _sketch_edit_fixtures as fx

from ai_sw_bridge.spec.sketch_editing import apply_sketch_edit, register
from ai_sw_bridge.spec.sketch_editing.mirror import OP


def main() -> int:
    sw = fx.connect()
    try:
        register(OP)
        doc = fx.new_part(sw)
        sketch, n0, ents, cl = fx.build_mirror_seed_sketch(doc)  # ("Sketch1", 3, [1,2], 0)
        params = {"entities": ents, "centerline": cl}
        res = apply_sketch_edit(doc, sketch, "sketch_mirror", params)

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
                    "op": "sketch_mirror",
                    "sketch": sketch,
                    "params": params,
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
