"""
Spike Q5: probe HARDER for the CreateDefinition + IChamferFeatureData2
pipeline. Earlier Q probe was too strict (assumed `data.EqualDistance` is
settable as the positive signal, which it may not be on a freshly-created
data object before AccessSelections).

We try a wider sweep:
  - For each v in 0..80, call data = fm.CreateDefinition(v)
  - For each non-None return, dir() / try a list of property NAMES the
    CHM mentions for IChamferFeatureData2:
      EqualDistance, DefaultDistance, EdgeChamferAngle, IsFlipped,
      GetEdgeCount, GetFaceCount, AccessSelections
  - Score each candidate by how many properties succeed

If we find one that matches >= 4 of those, that's likely
IChamferFeatureData2.

THEN: try the full pipeline:
  data = fm.CreateDefinition(swFmChamfer)
  data.EqualDistance = True
  data.DefaultDistance = 0.001
  data.AccessSelections(doc, ?)        -- may need a Component arg (or None)
  <select 4 edges via IEntity.Select2 with the same trick from Q4>
  fm.CreateFeature(data)

If CreateFeature returns a non-None IFeature AND the geometry is
visually chamfered (no PM pane lingering), this is the path that
solves the auto-commit problem.

Usage:
    python spikes/v0_3/spike_q5_chamfer_data_object.py
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


# Properties unique-ish to IChamferFeatureData2 per CHM
CHAMFER_PROPS = [
    "EqualDistance",
    "DefaultDistance",
    "EdgeChamferAngle",
    "IsFlipped",
    "GetEdgeCount",
    "GetFaceCount",
]


def _score_data_object(data) -> tuple[int, list[str]]:
    """Return (score, matched_props) by attempting to GET each chamfer
    property. We don't try to SET them (some are read-only on a fresh
    data object; AccessSelections may need to be called first)."""
    score = 0
    matched = []
    for prop in CHAMFER_PROPS:
        try:
            _ = getattr(data, prop)
            score += 1
            matched.append(prop)
        except Exception:
            pass
    return score, matched


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return 2

    _create_box(doc)
    fm = doc.FeatureManager

    print("== Spike Q5: probe CreateDefinition more thoroughly ==")
    candidates: list[tuple[int, int, list[str]]] = []
    for v in range(0, 80):
        try:
            data = fm.CreateDefinition(v)
        except Exception:
            continue
        if data is None:
            continue
        score, matched = _score_data_object(data)
        if score >= 3:
            candidates.append((v, score, matched))
            print(f"  v={v}: score={score}, matched={matched}")
    if not candidates:
        print("RED: no CreateDefinition value yielded an object matching >=3 chamfer props")
        return 3

    # Highest score wins
    candidates.sort(key=lambda t: -t[1])
    best_v, best_score, best_matched = candidates[0]
    print(f"\nBest candidate: v={best_v} (score {best_score}, matched {best_matched})")

    # Try the full pipeline at best_v
    print("\n--- Full pipeline ---")
    data = fm.CreateDefinition(best_v)
    if data is None:
        print("  unexpected: CreateDefinition returned None on second call")
        return 3

    # Set properties (these may require AccessSelections first)
    for prop, val in [("EqualDistance", True), ("DefaultDistance", 0.001)]:
        try:
            setattr(data, prop, val)
            print(f"  set {prop} = {val} OK")
        except Exception as e:
            print(f"  ! set {prop} = {val} failed: {e!r}")

    # Select 4 edges using the proven Q4 path
    sel = doc.SelectionManager
    doc.ClearSelection2(True)
    bodies = doc.GetBodies2(0, True)
    edges = bodies[0].GetEdges
    if callable(edges):
        edges = edges()
    targets = [
        (0.01, 0.0, 0.01),
        (-0.01, 0.0, 0.01),
        (0.0, 0.01, 0.01),
        (0.0, -0.01, 0.01),
    ]
    for i, p in enumerate(targets):
        best_edge, best_d2 = None, 1e18
        for e in edges:
            cp = e.GetClosestPointOn(*p)
            if cp is None:
                continue
            d2 = (cp[0]-p[0])**2 + (cp[1]-p[1])**2 + (cp[2]-p[2])**2
            if d2 < best_d2:
                best_d2, best_edge = d2, e
        ok = best_edge.Select2(True, 0)
        print(f"  select edge #{i} -> ok={ok}, count={sel.GetSelectedObjectCount2(-1)}")

    # CreateFeature(data) -- the auto-commit path
    try:
        f = fm.CreateFeature(data)
        print(f"  CreateFeature -> {f!r}")
        if f is None:
            print("  ! CreateFeature returned None")
            return 3
        f.Name = "Ch_Q5"
        print(f"  feature created: {f.Name}, IsSuppressed={f.IsSuppressed}")
        # Verify the chamfer recorded 4 edges
        data2 = f.GetDefinition
        ec = data2.GetEdgeCount
        print(f"  Ch_Q5.GetEdgeCount = {ec}")
        print(f"\n  >>> Check SW: is the chamfer geometrically applied without")
        print(f"      ticking a PM pane? If yes, this is the auto-commit path.")
        return 0
    except Exception as e:
        print(f"  ! CreateFeature raised: {e!r}")
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
