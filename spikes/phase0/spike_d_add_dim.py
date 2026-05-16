"""
Spike D - AddDimension2 on a freshly-created sketch entity.

Tests whether we can programmatically add a driving dimension to a rectangle
or circle via late-binding pywin32. This is needed for v0.2 Phase 1 builder
because CreateCornerRectangle / CreateCircle produce unconstrained sketches
with no D1/D2 dims, so EquationMgr.Add2 has nothing to bind to.

Test:
1. Open blank part (caller responsibility)
2. Select Front Plane, InsertSketch
3. CreateCornerRectangle 20x10mm centered at origin
4. Select a vertical edge (a side of the rectangle) by clicking near
   midpoint (10, 0, 0) - actually for a sketch we need SelectByID on a
   line entity. SW's sketch lines are auto-named "Line1", "Line2", etc.
5. AddDimension2(x, y, z) at a position offset from the entity to place
   the dim leader
6. Repeat for height
7. Close sketch, verify Sketch1 now has D1 and D2 dims

PASS: Doc has Sketch1, and we can read D1@Sketch1 / D2@Sketch1 via Parameter().
FAIL: AddDimension2 unmarshallable, or dims don't get named D1/D2.

Notes:
- AddDimension2(x, y, z) - signature is just the dim leader position
- Must have entities selected first
- For a rectangle: width is the horizontal length between two vertical lines,
  but SW typically dimensions side-to-side or corner-to-corner.
  Simpler: select the entire horizontal edge, AddDim places horizontal dim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


def run_com() -> dict:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        return {"status": "FAIL", "error": "no active doc; open a blank part first"}

    # Make sure doc is empty (only default features). Heuristic: feature_count <= 17.
    fc = doc.GetFeatureCount
    if fc > 17:
        return {
            "status": "FAIL",
            "error": f"doc not blank: {fc} features. Please File > New > Part first.",
        }

    # CRITICAL: suppress the "Modify Dimension" popup that AddDimension2 fires
    # by default. swUserPreferenceToggle.swInputDimValOnCreate = 8 (per SW API).
    # Save the current value so we can restore it after.
    SW_INPUT_DIM_VAL_ON_CREATE = 8
    prev_input_dim = sw.GetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, False)

    # 1. Select Front Plane, start sketch
    ok = doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    if not ok:
        sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, prev_input_dim)
        return {"status": "FAIL", "error": "could not select Front Plane"}

    sm = doc.SketchManager
    sm.InsertSketch(True)

    # 2. Create a 20x10 mm rectangle centered at origin
    sm.CreateCornerRectangle(-0.010, -0.005, 0.0, 0.010, 0.005, 0.0)

    # 3. Add horizontal dim. Select the top horizontal edge by clicking near
    #    its midpoint: (0, 0.005, 0). The edge is named "Line1"/"Line3" etc.
    #    SW assigns them in creation order: bottom (Line1), right (Line2),
    #    top (Line3), left (Line4) -- but this can vary.
    #    Easier: select via SelectByID with empty name + "SKETCHSEGMENT" + coord.
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", 0.0, 0.005, 0.0)
    if not ok:
        return {"status": "FAIL", "error": "could not select top edge"}

    # AddDimension2 places a dimension at the given dim leader location.
    # Returns IDisplayDimension. Position (0, 0.015, 0) puts it 5mm above top edge.
    dim_w = doc.AddDimension2(0.0, 0.015, 0.0)
    if dim_w is None:
        return {"status": "FAIL", "error": "AddDimension2 returned None for width"}

    # 4. Add vertical dim. Select left edge midpoint (-0.010, 0, 0).
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "SKETCHSEGMENT", -0.010, 0.0, 0.0)
    if not ok:
        return {"status": "FAIL", "error": "could not select left edge"}

    dim_h = doc.AddDimension2(-0.020, 0.0, 0.0)
    if dim_h is None:
        return {"status": "FAIL", "error": "AddDimension2 returned None for height"}

    # 5. Close sketch
    sm.InsertSketch(True)

    # 6. Rename sketch to "SpikeD_Sketch"
    sketch = doc.FeatureByPositionReverse(0)
    sketch.Name = "SpikeD_Sketch"

    # 7. Verify dims exist
    dim1 = doc.Parameter("D1@SpikeD_Sketch")
    dim2 = doc.Parameter("D2@SpikeD_Sketch")

    # Restore the user preference we toggled at the top
    sw.SetUserPreferenceToggle(SW_INPUT_DIM_VAL_ON_CREATE, prev_input_dim)

    return {
        "status": "PASS" if dim1 is not None and dim2 is not None else "FAIL",
        "sketch_name": "SpikeD_Sketch",
        "D1_mm": (dim1.SystemValue * 1000.0) if dim1 else None,
        "D2_mm": (dim2.SystemValue * 1000.0) if dim2 else None,
        "expected": "D1=20 D2=10 (or swapped - order depends on which edge selected first)",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["com"], default="com")
    args = parser.parse_args()

    result = run_com()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
