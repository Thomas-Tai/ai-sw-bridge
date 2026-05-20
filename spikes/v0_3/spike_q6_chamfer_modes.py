"""
Spike Q6: chamfer CreateDefinition pipeline with both modes.

Q5 verified that CreateDefinition(1) + CreateFeature(data) auto-commits
the chamfer (no PM-pane lingering). But Q5 only tested equal_distance.
Q6 verifies:
  - equal_distance mode: data.Type = 16 (swChamferEqualDistance),
                         data.DefaultDistance = distance_m
  - distance_angle mode: data.Type = 1 (swChamferAngleDistance),
                         data.DefaultDistance = distance_m,
                         data.EdgeChamferAngle = angle_deg

If both work via CreateFeature(data), the chamfer handler can switch
to this path entirely.

Test geometry:
  Box 1: 20x20x10, equal_distance 1mm chamfer on 4 top edges -> Ch_Eq
  Box 2: 20x20x10, distance_angle 2mm + 30deg on 4 top edges -> Ch_DA

Both built in the same doc for visual comparison.

Usage:
    python spikes/v0_3/spike_q6_chamfer_modes.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0
SW_FM_CHAMFER = 1  # confirmed in Q5: same value as SW_FM_FILLET
SW_CHAMFER_ANGLE_DISTANCE = 1
SW_CHAMFER_EQUAL_DISTANCE = 16


def _create_box(doc, half_mm: float = 10.0, depth_mm: float = 10.0) -> None:
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    h = half_mm / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, h, h, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        depth_mm / 1000,
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
        SW_START_SKETCH_PLANE,
        0.0,
        False,
    )
    if feat is None:
        raise RuntimeError("box extrude failed")


def _select_top_edges(doc, top_z_m: float) -> None:
    """Accumulate the 4 top edges using IEntity.Select2 (Q4 path)."""
    doc.ClearSelection2(True)
    bodies = doc.GetBodies2(0, True)
    edges = bodies[-1].GetEdges
    if callable(edges):
        edges = edges()
    # The 4 top edges of a 20mm box at z=top_z run perimeter at the +z face.
    # Pick midpoints.
    targets = [
        (0.01, 0.0, top_z_m),
        (-0.01, 0.0, top_z_m),
        (0.0, 0.01, top_z_m),
        (0.0, -0.01, top_z_m),
    ]
    sel = doc.SelectionManager
    for i, p in enumerate(targets):
        best_edge, best_d2 = None, 1e18
        for e in edges:
            cp = e.GetClosestPointOn(*p)
            if cp is None:
                continue
            d2 = (cp[0] - p[0]) ** 2 + (cp[1] - p[1]) ** 2 + (cp[2] - p[2]) ** 2
            if d2 < best_d2:
                best_d2, best_edge = d2, e
        if best_edge is None or best_d2 > 1e-12:
            raise RuntimeError(f"edge #{i} point not on any edge of latest body")
        best_edge.Select2(True, 0)
    n = sel.GetSelectedObjectCount2(-1)
    if n != 4:
        raise RuntimeError(f"expected 4 selected, got {n}")


def _build_chamfer_via_pipeline(
    doc, fm, mode: str, distance_m: float, angle_deg: float, name: str
):
    print(f"\n-- Building chamfer '{name}' (mode={mode}) --")
    data = fm.CreateDefinition(SW_FM_CHAMFER)
    if data is None:
        raise RuntimeError("CreateDefinition returned None")
    # Set Type discriminator
    if mode == "equal_distance":
        data.Type = SW_CHAMFER_EQUAL_DISTANCE
        data.DefaultDistance = distance_m
        print(f"   Type={data.Type}, DefaultDistance={data.DefaultDistance}")
    elif mode == "distance_angle":
        data.Type = SW_CHAMFER_ANGLE_DISTANCE
        data.DefaultDistance = distance_m
        try:
            # CHM says EdgeChamferAngle is in radians (despite InsertFeatureChamfer's Angle being degrees)
            import math

            data.EdgeChamferAngle = angle_deg * math.pi / 180
            print(
                f"   Type={data.Type}, DefaultDistance={data.DefaultDistance}, EdgeChamferAngle={data.EdgeChamferAngle:.4f}rad"
            )
        except Exception as e:
            print(f"   ! setting EdgeChamferAngle failed: {e!r}")
    else:
        raise RuntimeError(f"unknown mode {mode!r}")

    f = fm.CreateFeature(data)
    if f is None:
        raise RuntimeError("CreateFeature returned None")
    f.Name = name
    # Verify
    data2 = f.GetDefinition
    print(
        f"   created: GetEdgeCount={data2.GetEdgeCount}, GetIsFlipped={data2.GetIsFlipped if hasattr(data2, 'GetIsFlipped') else 'n/a'}"
    )
    return f


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2

    print("== Spike Q6: chamfer pipeline both modes ==")

    # Box 1
    _create_box(doc, half_mm=10.0, depth_mm=10.0)
    fm = doc.FeatureManager
    _select_top_edges(doc, top_z_m=0.01)
    try:
        _build_chamfer_via_pipeline(doc, fm, "equal_distance", 0.001, 0.0, "Ch_Eq")
    except Exception as e:
        print(f"! equal_distance failed: {e!r}")
        traceback.print_exc()

    # Box 2 -- a SECOND box on Top Plane so we don't stack chamfers
    # Skip for now; just do equal_distance + distance_angle on same box.
    # First clear any selections and re-select edges (the chamfer consumed them).
    # Actually we need different edges. Use the bottom 4 edges this time.
    _select_top_edges(doc, top_z_m=0.0)  # z=0 face = bottom face
    try:
        _build_chamfer_via_pipeline(doc, fm, "distance_angle", 0.002, 30.0, "Ch_DA")
    except Exception as e:
        print(f"! distance_angle failed: {e!r}")
        traceback.print_exc()

    print("\n>>> Check SW. Both Ch_Eq and Ch_DA should be present and the box")
    print("    should be chamfered top AND bottom, all 4 edges each, with NO")
    print("    pending PM pane (no tab on the left edge of the viewport).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
