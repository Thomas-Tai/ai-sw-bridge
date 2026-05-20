"""
Spike Q4: find a way to ADD edges to the selection set without losing
prior selections, given that:
  - SelectByID (5-arg) replaces the selection on each call
  - doc.Extension.SelectByID2 (9-arg, append=True) fails on Callout OUT-param
  - We confirmed in Q3 that the chamfered_box bug is exactly this: only
    the last SelectByID survives, GetEdgeCount returns 1 not 4

Strategies to try:

  A. IModelDocExtension.SelectByID2 with Callout=None positional, hoping
     Type mismatch is positional-form specific. (We already know append=False
     calls fail; try the boolean variant explicitly.)

  B. Selection group append via IModelDoc2.AddSelection or similar legacy
     method. Check CHM for accumulator-style APIs.

  C. Walk IBody2.GetEdges(), pick the IEdge whose nearest-point is closest
     to each target, then IEntity.Select4(append, None) -- same Callout
     concern but on Entity not Extension.

  D. After SelectByID #N, capture the IEntity via SelectionMgr.GetSelectedObject6
     and re-select with append before SelectByID #N+1.

Strategy A first (cheapest if it works).

Usage:
    python spikes/v0_3/spike_q4_edge_append.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0


def _create_box(doc):
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, 0.01, 0.01, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        0.01,
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
    feat.Name = "EX_Box"


EDGES = [
    (0.01, 0.0, 0.01),
    (-0.01, 0.0, 0.01),
    (0.0, 0.01, 0.01),
    (0.0, -0.01, 0.01),
]


def _try_strategy_A(doc, sel):
    """SelectByID2 with append=True and Callout=None"""
    print("\n--- Strategy A: SelectByID2 append=True, Callout=None ---")
    doc.ClearSelection2(True)
    ext = doc.Extension
    for i, (x, y, z) in enumerate(EDGES):
        try:
            ok = ext.SelectByID2("", "EDGE", x, y, z, True, 0, None, 0)
            print(
                f"  #{i}: SelectByID2 -> ok={ok}, count={sel.GetSelectedObjectCount2(-1)}"
            )
        except Exception as e:
            print(f"  #{i}: raised {e!r}")
            return False
    return sel.GetSelectedObjectCount2(-1) == 4


def _try_strategy_C(doc, sel):
    """Walk IBody2.GetEdges() and IEntity.Select4(append, None)."""
    print("\n--- Strategy C: IBody2.GetEdges + IEntity.Select4 ---")
    doc.ClearSelection2(True)
    part = doc  # IPartDoc inherits IModelDoc2
    # IPartDoc.GetBodies2(swBodyType_e, bVisibleOnly)
    # swSolidBody = 0
    try:
        bodies = part.GetBodies2(0, True)
        if bodies is None or len(bodies) == 0:
            print("  no bodies returned")
            return False
        body = bodies[0]
        # pywin32 late-binding: zero-arg methods auto-invoke on attribute
        # access, but for GetEdges the auto-invoke seems unreliable. Try
        # both: first as a property, then as a method call.
        edges = body.GetEdges
        if callable(edges):
            edges = edges()
        if edges is None:
            print("  GetEdges returned None")
            return False
        # edges is a SAFEARRAY -> Python tuple of IEdge CDispatch
        n_edges = len(edges)
        print(f"  body has {n_edges} edges")
    except Exception as e:
        print(f"  ! body/edges enumeration failed: {e!r}")
        traceback.print_exc()
        return False

    # For each target point, find the edge whose nearest point is closest
    # to that point. IEdge.GetClosestPointOn(x, y, z) returns 3 doubles.
    def _closest_dist2(edge, p):
        try:
            cp = edge.GetClosestPointOn(p[0], p[1], p[2])
            if cp is None:
                return 1e9
            return (cp[0] - p[0]) ** 2 + (cp[1] - p[1]) ** 2 + (cp[2] - p[2]) ** 2
        except Exception:
            return 1e9

    for i, p in enumerate(EDGES):
        best_idx, best_d2 = -1, 1e18
        for k, e in enumerate(edges):
            d2 = _closest_dist2(e, p)
            if d2 < best_d2:
                best_idx, best_d2 = k, d2
        if best_idx < 0:
            print(f"  #{i}: no matching edge")
            return False
        target = edges[best_idx]
        try:
            # IEntity.Select2(Append, Mark) -- 2-arg, NO Callout. The
            # newer Select4(Append, Callout) added the Callout OUT-IDispatch
            # which breaks under late-binding. Select2 has no Callout, so
            # this should work.
            ok = target.Select2(True, 0)  # append=True, mark=0
            n = sel.GetSelectedObjectCount2(-1)
            print(
                f"  #{i}: edge idx {best_idx}, d2={best_d2:.3e} -> Select2 ok={ok}, count={n}"
            )
        except Exception as e:
            print(f"  #{i}: Select2 raised {e!r}")
            return False
    return sel.GetSelectedObjectCount2(-1) == 4


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2

    _create_box(doc)
    sel = doc.SelectionManager

    print("== Spike Q4: find a way to APPEND edges to selection ==")

    results = {}
    try:
        results["A"] = _try_strategy_A(doc, sel)
    except Exception as e:
        print(f"strategy A crashed: {e!r}")
        results["A"] = False

    try:
        results["C"] = _try_strategy_C(doc, sel)
    except Exception as e:
        print(f"strategy C crashed: {e!r}")
        results["C"] = False

    print("\n== Summary ==")
    for k, v in results.items():
        print(f"  Strategy {k}: {'GREEN' if v else 'RED'}")

    # If C worked, do the full chamfer + check feature edge count
    if results.get("C"):
        print("\n--- End-to-end: Strategy C + InsertFeatureChamfer ---")
        fm = doc.FeatureManager
        f = fm.InsertFeatureChamfer(
            4,  # tangent propagation
            16,  # equal distance
            0.0,
            0.0,
            0.001,  # 1mm
            0.0,
            0.0,
            0.0,
        )
        if f is None:
            print("  ! InsertFeatureChamfer returned None")
            return 3
        f.Name = "Ch_AllFour"
        data = f.GetDefinition  # auto-invoked property under late-binding
        try:
            ec = data.GetEdgeCount  # also auto-invoked
            print(f"  Ch_AllFour.GetEdgeCount = {ec}")
        except Exception as e:
            print(f"  ! GetEdgeCount failed: {e!r}")
        print(f"  Ch_AllFour.IsSuppressed = {f.IsSuppressed}")
        return 0
    return 3


if __name__ == "__main__":
    sys.exit(main())
