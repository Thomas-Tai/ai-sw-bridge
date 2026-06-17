"""W62 split_line spike — seat-probe for the dual-mode split line handler.

Probes Mode-A (CreateDefinition → ISplitLineFeatureData → CreateFeature) and
Mode-B (InsertSplitLineProject on pre-selected entities) via the lane handler.

Fixture: 40×30×10 mm boss-extrude block (``fx.build_block``) + a Front-plane
line at y=+5 mm that projects +Z onto the top face (``fx.seed_line_over_top``).

Verify-the-EFFECT:
    PASS  := ΔFace > 0 AND ΔVol == 0 AND the split survives save→reopen.
    NO_OP := clean return, zero topological delta (both modes walled).
    ERROR := fixture or harness failure.

Exit codes: 0 = PASS, 2 = NO_OP (both modes walled), 1 = ERROR.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

# Spike-only path setup (handler imports need ``src`` on sys.path).
_SPIKE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SPIKE_DIR.parents[1]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
if str(_SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(_SPIKE_DIR))

from ai_sw_bridge.features.split_line import _metrics, create_split_line  # noqa: E402

import _feature_spike_fixtures as fx  # noqa: E402


def _report(msg: str) -> None:
    print(f"[spike_split_line] {msg}", flush=True)


def main() -> int:
    _report("connecting to running SOLIDWORKS …")
    try:
        sw = fx.connect()
    except Exception as exc:
        _report(f"ERROR: connect failed: {exc}")
        traceback.print_exc()
        return 1

    _report("building 40×30×10 mm block (Boss-Extrude, consumes Sketch1) …")
    try:
        doc = fx.build_block(sw)
    except Exception as exc:
        _report(f"ERROR: build_block failed: {exc}")
        traceback.print_exc()
        return 1

    _report("seeding Front-plane line over top face (Sketch2) …")
    try:
        sketch_name, face_entity = fx.seed_line_over_top(doc)
    except Exception as exc:
        _report(f"ERROR: seed_line_over_top failed: {exc}")
        traceback.print_exc()
        return 1
    _report(f"  sketch={sketch_name!r}, face_entity={type(face_entity).__name__}")

    faces_before, vol_before = _metrics(doc)
    _report(f"  before: faces={faces_before}, vol_mm3={vol_before:.4f}")
    if faces_before == 0:
        _report("ERROR: no solid bodies in the block")
        return 1

    _report("calling create_split_line handler (probes Mode-A then Mode-B) …")
    ok, note = create_split_line(
        doc,
        {"reverse": False, "single_direction": False, "split_type": "projection"},
        {"sketch_name": sketch_name, "face_entity": face_entity},
    )
    _report(f"  handler returned: ok={ok}, note={note!r}")

    faces_after, vol_after = _metrics(doc)
    d_faces = faces_after - faces_before
    d_vol = vol_after - vol_before
    _report(f"  after:  faces={faces_after}, vol_mm3={vol_after:.4f}")
    _report(f"  Δface={d_faces}, Δvol_mm3={d_vol:.6f}")

    if not ok:
        _report(f"NO_OP: handler failed: {note}")
        return 2

    if d_faces <= 0 or abs(d_vol) >= 1e-6:
        _report(
            f"NO_OP: verify failed (Δface={d_faces}, |Δvol|={abs(d_vol):.6f}); "
            f"handler returned ok but topology did not split"
        )
        return 2

    _report("handler ok + verify passed — testing save→reopen persistence …")
    try:
        doc2 = fx.save_and_reopen(sw, doc)
        faces_reopen, vol_reopen = _metrics(doc2)
        d_faces_reopen = faces_reopen - faces_before
        d_vol_reopen = vol_reopen - vol_before
        _report(
            f"  after reopen: faces={faces_reopen}, vol_mm3={vol_reopen:.4f}, "
            f"Δface={d_faces_reopen}, Δvol_mm3={d_vol_reopen:.6f}"
        )
        if d_faces_reopen > 0 and abs(d_vol_reopen) < 1e-6:
            mode = "A" if (note and "mode-A" in note) else "B"
            _report(
                f"PASS: split persisted (mode-{mode}, "
                f"Δface={d_faces_reopen}, Δvol_mm3={d_vol_reopen:.6f})"
            )
            return 0
        else:
            _report(
                f"NO_OP: split did not survive reopen "
                f"(Δface_reopen={d_faces_reopen}, Δvol_reopen={d_vol_reopen:.6f})"
            )
            return 2
    except Exception as exc:
        _report(f"ERROR during save→reopen: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
