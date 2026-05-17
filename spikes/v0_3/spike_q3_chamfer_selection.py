"""
Spike Q3: diagnose the chamfered_box failure mode.

Observation (from user screenshot): after running the chamfered_box example,
the FeatureManager tree shows Ch_TopEdges as the active/selected feature
with a closed PropertyManager pane tab visible on the left edge of the
viewport. The box geometry shows chamfers on some edges but not obviously
all four. Clicking the tick on the PM pane finalizes the chamfer.

Two hypotheses to distinguish:

  H1: SelectByID with type='EDGE' does NOT accumulate across calls without
      explicit append. Only the LAST edge in the loop was in the selection
      set when InsertFeatureChamfer ran. The visible chamfers on multiple
      edges are due to swFeatureChamferTangentPropagation extending the
      single-edge chamfer to tangent neighbors.

  H2: All 4 edges ARE chamfered but the feature is in an "in edit" state
      with the PM pane parked. Geometry is the live preview; clicking the
      tick just dismisses the pane.

Diagnostic strategy:
  1. Run the SelectByID loop and check SelectionMgr.GetSelectedObjectCount2(-1)
     after each call. If it stays at 1, that confirms H1.
  2. Call InsertFeatureChamfer and check the returned feature's recorded
     edge count via IChamferFeatureData2.GetEdgeCount (need to open via
     IFeature.GetDefinition()).
  3. Also check whether any "PropertyManager open" indicator is queryable.

Usage:
    python spikes/v0_3/spike_q3_chamfer_selection.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0
SW_CHAMFER_EQUAL_DISTANCE = 16
SW_FCO_TANGENT_PROPAGATION = 4


def _create_box(doc):
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, 0.01, 0.01, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True, False, False,
        SW_END_COND_BLIND, 0, 0.01, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True,
        SW_START_SKETCH_PLANE, 0.0, False,
    )
    if feat is None:
        raise RuntimeError("box extrude failed")
    feat.Name = "EX_Box"


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2

    _create_box(doc)
    sel = doc.SelectionManager

    print("== Spike Q3: chamfer selection diagnostic ==")

    # Reproduce the chamfered_box edge selection sequence exactly.
    # spec.json: 4 top edges at z=10mm
    edges = [
        (0.01, 0.0, 0.01),    # +X
        (-0.01, 0.0, 0.01),   # -X
        (0.0, 0.01, 0.01),    # +Y
        (0.0, -0.01, 0.01),   # -Y
    ]

    doc.ClearSelection2(True)
    print(f"after Clear: count={sel.GetSelectedObjectCount2(-1)}")
    for i, (x, y, z) in enumerate(edges):
        ok = doc.SelectByID("", "EDGE", x, y, z)
        n = sel.GetSelectedObjectCount2(-1)
        print(f"  SelectByID #{i} ({x*1000:.0f},{y*1000:.0f},{z*1000:.0f}) -> ok={ok}, count={n}")

    # Now: insert the chamfer
    fm = doc.FeatureManager
    f = fm.InsertFeatureChamfer(
        SW_FCO_TANGENT_PROPAGATION,
        SW_CHAMFER_EQUAL_DISTANCE,
        0.0, 0.0,
        0.001,  # 1mm
        0.0, 0.0, 0.0,
    )
    print(f"\nInsertFeatureChamfer -> {f!r}")
    if f is None:
        print("RED: returned None")
        return 3
    print(f"  Name={f.Name}, GetTypeName={f.GetTypeName}, IsSuppressed={f.IsSuppressed}")

    # Pull GetDefinition to inspect what edges were actually recorded
    try:
        data = f.GetDefinition
        print(f"  GetDefinition -> {data!r}")
        if data is not None:
            # IChamferFeatureData2 has GetEdgeCount, GetEdges, etc.
            try:
                ec = data.GetEdgeCount
                print(f"  data.GetEdgeCount = {ec}")
            except Exception as e:
                print(f"  ! data.GetEdgeCount failed: {e!r}")
            try:
                # AccessSelections might be needed before reading
                ok = data.AccessSelections(doc, None)
                print(f"  data.AccessSelections -> {ok}")
                ec2 = data.GetEdgeCount
                print(f"  data.GetEdgeCount after AccessSelections = {ec2}")
                data.ReleaseSelectionAccess()
            except Exception as e:
                print(f"  ! AccessSelections chain failed: {e!r}")
    except Exception as e:
        print(f"  ! GetDefinition failed: {e!r}")
        traceback.print_exc()

    # Also check what's selected NOW (post-call) -- some APIs leave the
    # affected entities in the selection set for the user to see.
    n_post = sel.GetSelectedObjectCount2(-1)
    print(f"\nPost-call selection count: {n_post}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
