"""W62 project_curve v2 spike -- exercise the patched handler's Mode-B paths.

This spike sidesteps the SPIKE_STATUS gate to fire the real handler
sub-routines (_try_mode_b_insert, _try_mode_b_convert) with full
telemetry. Built on the v1 spike's findings (verdict LEAD):
  * Mode-A QUARANTINED -- no QI succeeds, no creation enum.
  * Mode-B-insert: probe InsertProjectedSketch2(Reverse:int) -- the
    correct method discovered by the v1 typelib walk.
  * Mode-B-convert: probe SketchUseEdge3(IsChain:bool) with corrected
    1-arg sig (v1 used 3-arg, raised "Invalid number of parameters").

PASS = ref-curve node count goes up by >=1 AND survives save->reopen.
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

logging.basicConfig(
    level=logging.WARNING, format="%(name)s %(levelname)s %(message)s",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_SPIKE_DIR = str(Path(__file__).resolve().parent)
if _SPIKE_DIR not in sys.path:
    sys.path.insert(0, _SPIKE_DIR)

import _feature_spike_fixtures as fx  # noqa: E402
from ai_sw_bridge.features import project_curve as pc  # noqa: E402


def main() -> int:
    print("[project_curve_v2] connecting to live seat...", flush=True)
    sw = fx.connect()
    doc = fx.build_block(sw)
    sketch_name, face = fx.seed_line_over_top(doc)
    print(
        f"[project_curve_v2] fixture: sketch={sketch_name!r}, "
        f"face_type={type(face).__name__}",
        flush=True,
    )

    count_before = pc._count_feature_nodes(doc)
    print(f"[project_curve_v2] ref-curve nodes before: {count_before}", flush=True)

    feature = {"sketch_name": sketch_name, "reverse": False}
    target = {"face": face, "sketch_name": sketch_name}

    print("[project_curve_v2] firing _try_mode_b_insert...", flush=True)
    result_insert = pc._try_mode_b_insert(doc, feature, target)
    print(f"[project_curve_v2] _try_mode_b_insert -> {result_insert!r}", flush=True)

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    count_after_insert = pc._count_feature_nodes(doc)
    delta_insert = count_after_insert - count_before
    print(
        f"[project_curve_v2] ref-curve nodes after insert: "
        f"{count_after_insert} (delta={delta_insert})",
        flush=True,
    )

    mode_fired = None
    if delta_insert > 0:
        mode_fired = "B-insert"
    else:
        print("[project_curve_v2] insert path produced no new node; "
              "firing _try_mode_b_convert...", flush=True)
        converted = pc._try_mode_b_convert(doc, feature, target)
        print(f"[project_curve_v2] _try_mode_b_convert -> {converted!r}", flush=True)
        try:
            doc.ForceRebuild3(False)
        except Exception:
            pass
        count_after_convert = pc._count_feature_nodes(doc)
        delta_convert = count_after_convert - count_before
        print(
            f"[project_curve_v2] ref-curve nodes after convert: "
            f"{count_after_convert} (delta={delta_convert})",
            flush=True,
        )
        if delta_convert > 0:
            mode_fired = "B-convert"

    if mode_fired is None:
        print("[project_curve_v2] NO_OP: no mode produced a ref-curve node", flush=True)
        return 2

    print(
        f"[project_curve_v2] handler-side PASS via mode-{mode_fired}; "
        f"running save->reopen...", flush=True,
    )
    try:
        doc2 = fx.save_and_reopen(sw, doc)
    except Exception as e:
        print(f"[project_curve_v2] save_and_reopen RAISED: {e!r}", flush=True)
        traceback.print_exc()
        return 1
    count_reopen = pc._count_feature_nodes(doc2)
    delta_reopen = count_reopen - count_before
    print(
        f"[project_curve_v2] ref-curve nodes after reopen: "
        f"{count_reopen} (delta={delta_reopen})",
        flush=True,
    )
    if delta_reopen > 0:
        print(
            f"[project_curve_v2] PASS: ref-curve survived reopen "
            f"(mode={mode_fired}, delta={delta_reopen})",
            flush=True,
        )
        return 0
    print("[project_curve_v2] PASS-but-not-persisted", flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
