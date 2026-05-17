"""
Spike I - verify that SetUserPreferenceToggle(8, False) actually writes False.

Hypothesis from Reddit: swInputDimValOnCreate is the correct toggle and
should work for AddDimension2 just like it does for AddSpecificDimension.
Our problem may be that the toggle isn't actually being set (value not
persisting in the session).

Test:
1. Read GetUserPreferenceToggle(8). Print.
2. SetUserPreferenceToggle(8, False).
3. Read GetUserPreferenceToggle(8). Print.
4. Try AddDimension2 with the toggle False. Time it (no manual click).
5. Read GetUserPreferenceToggle(8) again. Print.
6. Restore.

If step 4 still blocks, toggle 8 is NOT swInputDimValOnCreate on this build.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"status": "FAIL", "error": "no active doc"}))
        return 1
    if doc.GetFeatureCount > 17:
        print(
            json.dumps(
                {"status": "FAIL", "error": "doc not blank; File>New>Part first"}
            )
        )
        return 1

    # Probe several candidate IDs near 8 (swInputDimValOnCreate is documented
    # as 8, but enum values can shift). Read all.
    candidates = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 95, 96, 97, 98, 99, 100]
    before = {}
    for c in candidates:
        try:
            before[c] = bool(sw.GetUserPreferenceToggle(c))
        except Exception as e:
            before[c] = f"ERR:{e!r}"

    # Now set ID=8 to False
    sw.SetUserPreferenceToggle(8, False)

    after_set = {}
    for c in candidates:
        try:
            after_set[c] = bool(sw.GetUserPreferenceToggle(c))
        except Exception as e:
            after_set[c] = f"ERR:{e!r}"

    # Try AddDimension2 on a fresh sketch and time it. If toggle 8 is correct,
    # this should complete in <1s without manual interaction.
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.005, 0.0, 0.0)
    doc.ClearSelection2(True)
    doc.SelectByID("", "SKETCHSEGMENT", 0.005, 0.0, 0.0)

    t0 = time.time()
    dim = doc.AddDimension2(0.010, 0.005, 0.0)
    elapsed = time.time() - t0
    dim_ok = dim is not None

    # Close sketch
    sm.InsertSketch(True)

    print(
        json.dumps(
            {
                "status": "DONE",
                "before_set": before,
                "after_set_to_False": after_set,
                "id_8_changed_to_False": after_set.get(8) is False
                and before.get(8) is True,
                "AddDimension2_elapsed_s": round(elapsed, 3),
                "AddDimension2_blocked": elapsed > 3.0,
                "interpretation": (
                    "id 8 is swInputDimValOnCreate -- toggle works"
                    if elapsed < 2.0 and after_set.get(8) is False
                    else "id 8 may NOT be swInputDimValOnCreate; popup still blocks"
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
