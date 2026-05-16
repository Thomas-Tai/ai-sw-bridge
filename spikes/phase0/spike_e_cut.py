"""
Spike E - find a working FeatureCut signature on this SW 2024 build via late-binding.

Tries multiple variants. Reports which ones succeed.

Requires: SW running with a part containing:
- A boss extrude (any solid)
- An ACTIVE selected sketch on a face of that boss that doesn't fully cover it

We do NOT build the prerequisite shape here; just exercise FeatureCut signatures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"ok": False, "error": "no active doc"}))
        return 1

    # Probe what overloads exist by trying each. We don't actually need to
    # produce geometry - we just want to know which signatures pywin32 accepts
    # without "Parameter not optional".
    # Each variant is a list of positional args to FeatureCut4.

    fm = doc.FeatureManager
    results = []

    # Reference SW API arg order for FeatureCut4 (SW 2024):
    #   Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2,
    #   Dang1, Dang2, OffsetReverse1, OffsetReverse2,
    #   TranslateSurface1, TranslateSurface2, NormalCut,
    #   UseFeatScope, UseAutoSelect, AssemblyFeatureScope,
    #   T0, StartOffset, FlipStartOffset
    # = 24 args.
    SW_END_COND_BLIND = 0
    SW_END_COND_THROUGH_ALL = 4

    variants = {
        "24_args_through_all": [
            True, False, False,
            SW_END_COND_THROUGH_ALL, 0,
            0.001, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            False,
            True, True, True,
            0, 0.0, False,
        ],
        "25_args_through_all": [
            True, False, False,
            SW_END_COND_THROUGH_ALL, 0,
            0.001, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            False, False,
            True, True, True,
            0, 0.0, False,
        ],
        "23_args_through_all": [
            True, False, False,
            SW_END_COND_THROUGH_ALL, 0,
            0.001, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0.0, False,
        ],
    }

    for name, args in variants.items():
        try:
            f = fm.FeatureCut4(*args)
            results.append({"variant": name, "arg_count": len(args), "ok": True,
                            "feature_returned": f is not None})
            if f is not None:
                # Roll back so we can try the next variant cleanly. The undo
                # is a doc method; try it but tolerate failure.
                try:
                    doc.EditUndo2(1)
                except Exception:
                    pass
        except Exception as e:
            results.append({"variant": name, "arg_count": len(args), "ok": False,
                            "error": repr(e)})

    print(json.dumps(results, indent=2))
    # Return 0 if any variant succeeded
    return 0 if any(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
