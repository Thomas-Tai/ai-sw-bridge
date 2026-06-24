"""
Spike W45-A — MIN-WALL-THICKNESS DFM probe (read-only).

SEAT-RUNNABLE BY W0. NOT run by the offline author (no seat access).

Builds TWO discriminating fixtures from scratch, runs
``observe.sw_min_wall_thickness`` against each, and writes a single
structured JSON verdict to ``_results/min_wall_w45.json``.

Fixtures (the metric MUST discriminate):
  THIN  : a 40x40x40 mm box hollowed by a Shell feature to a 2 mm wall.
          Expected min wall ~ 2 mm.
  THICK : a solid 40x40x40 mm block (no shell).
          Expected min wall ~ 40 mm (the box dimension; closest opposite
          face is the far wall).

GREEN criterion (verify-the-effect, discrimination -- NOT "returns a number"):
  - both probes return ok=True
  - thin.min_wall_mm  is meaningfully smaller than thick.min_wall_mm
  - thin.min_wall_mm  is approximately the 2 mm shell wall (tolerance band)

Honest caveat (see observe.sw_min_wall_thickness docstring + the handback):
  the wall estimate uses IFace2.GetClosestPointOn projection (the PROVEN
  primitive) rather than a body-ray intersection. For the planar box+shell
  fixture the opposite faces are planar and parallel, so the closest-point
  projection equals the true normal-ray wall. If this spike's thin fixture
  does NOT land near 2 mm, that is the signal the projection estimate breaks
  down (and min-wall needs a real ray primitive -- a SEAT-UNKNOWN, flagged).

Usage (on the seat):
    python spikes/v0_2x/min_wall_w45.py
Exit 0 only if the discrimination GREEN criterion holds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.observe import sw_min_wall_thickness  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "_results" / "min_wall_w45.json"

BOX = 0.040  # 40 mm cube
WALL = 0.002  # 2 mm shell wall
SW_END_COND_BLIND = 0

# Discrimination band: the thin wall should read close to 2mm, the thick
# block far above it. Generous tolerance -- we are proving DISCRIMINATION,
# not metrology.
THIN_EXPECT_MM = 2.0
THIN_TOL_MM = 1.0  # accept 1..3 mm for the shell wall
THICK_MIN_MM = 10.0  # thick block min-wall must clear this floor


def _new_part(sw):
    template = sw.GetUserPreferenceStringValue(8)  # swDefaultTemplatePart
    if not template:
        raise RuntimeError("no default Part template configured")
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        raise RuntimeError("NewDocument returned None")
    return doc


def _box_solid(doc) -> None:
    """Extrude a centered BOX cube on the Front plane."""
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError("could not select Front Plane")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    h = BOX / 2.0
    sm.CreateCornerRectangle(-h, -h, 0.0, h, h, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        BOX,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0.0,
        False,
    )
    if feat is None:
        raise RuntimeError("FeatureExtrusion2 returned None")


def _shell(doc) -> None:
    """Hollow the box to a WALL-thick shell by removing one face.

    IModelDoc2.InsertFeatureShell(thickness_m, outward) hollows every body,
    leaving the pre-selected face(s) open. We select the +Z cap (the
    extrude outboard face) first so the box becomes an open thin-wall tub.
    """
    doc.ClearSelection2(True)
    # The outboard cap sits at z = BOX (extrude depth) on the part Z axis.
    if not doc.SelectByID("", "FACE", 0.0, 0.0, BOX):
        # Fall back to enclosed shell (no open face) -- still a thin wall.
        doc.ClearSelection2(True)
    doc.InsertFeatureShell(WALL, False)


def _run_one(sw, *, shelled: bool) -> dict:
    doc = _new_part(sw)
    _box_solid(doc)
    if shelled:
        _shell(doc)
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    probe = sw_min_wall_thickness(samples_per_face=4)
    return probe


def run_com() -> dict:
    sw = get_sw_app()
    thin = _run_one(sw, shelled=True)
    thick = _run_one(sw, shelled=False)

    thin_mm = thin.get("min_wall_mm")
    thick_mm = thick.get("min_wall_mm")

    checks = {
        "thin_ok": bool(thin.get("ok")),
        "thick_ok": bool(thick.get("ok")),
        "thin_lt_thick": (
            thin_mm is not None and thick_mm is not None and thin_mm < thick_mm
        ),
        "thin_near_2mm": (
            thin_mm is not None and abs(thin_mm - THIN_EXPECT_MM) <= THIN_TOL_MM
        ),
        "thick_above_floor": (thick_mm is not None and thick_mm >= THICK_MIN_MM),
    }
    overall = all(checks.values())
    return {
        "overall": "PASS" if overall else "FAIL",
        "checks": checks,
        "thin_min_wall_mm": thin_mm,
        "thick_min_wall_mm": thick_mm,
        "thin_probe": thin,
        "thick_probe": thick,
        "fixture": {
            "box_mm": BOX * 1000.0,
            "shell_wall_mm": WALL * 1000.0,
        },
    }


def main() -> int:
    result = run_com()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
