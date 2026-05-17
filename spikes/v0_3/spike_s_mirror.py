"""
Spike S: mirror via InsertMirrorFeature2 (5 args).

Builds a box, adds an off-center hole, mirrors the hole feature about the
Right Plane (YZ plane, x=0).

API: IFeatureManager::InsertMirrorFeature2
  (BMirrorBody, BGeometryPattern, BMerge, BKnit, ScopeOptions) -> Feature
  5 args, much simpler than linear pattern.

Selection protocol:
  1. Select the MIRROR PLANE -- mark = 2 (swSelectionMarkMirrorPlane).
     For a reference plane, use doc.Extension.SelectByID2("Right Plane",
     "PLANE", 0,0,0, False, 2, None, 0).
  2. Select the SEED FEATURE(s) to mirror -- mark = 1 (swSelPatternSeedFeature).
     For a feature node, use SelectByID2("Hole_Seed", "BODYFEATURE", 0,0,0,
     True, 1, None, 0).

Same SelectByID2 OUT-param marshalling risk as Spike R. If it works there
it should work here.

Usage:
    python spikes/v0_3/spike_s_mirror.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_END_COND_THROUGH_ALL = 1
SW_START_SKETCH_PLANE = 0


def _create_box(doc, side_mm: float, thick_mm: float) -> None:
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    half = side_mm / 2 / 1000
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, half, half, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    feat = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        thick_mm / 1000,
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
        raise RuntimeError("box extrude returned None")
    feat.Name = "SK_Box_Extrude"


def _create_seed_hole(doc) -> str:
    """3mm hole at (-7, 0). Mirror about Right Plane (x=0) should produce
    a matching hole at (+7, 0)."""
    fm = doc.FeatureManager
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.0, 0.0, 0.01):
        raise RuntimeError("could not select +z face for seed sketch")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    cx, cy = -0.007, 0.0
    r = 0.0015
    sm.CreateCircle(cx, cy, 0.0, cx + r, cy, 0.0)
    sm.InsertSketch(True)

    doc.ClearSelection2(True)
    sketch_feat = doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no sketch produced for seed hole")
    sketch_feat.Name = "SK_Hole_Seed"
    sketch_feat.Select2(False, 0)

    cut = fm.FeatureCut4(
        True,  # Sd
        False,  # Flip
        False,  # Dir
        SW_END_COND_THROUGH_ALL,  # T1
        0,  # T2
        0.0,  # D1
        0.0,  # D2
        False,  # Dchk1
        False,  # Dchk2
        False,  # Ddir1
        False,  # Ddir2
        0.0,  # Dang1
        0.0,  # Dang2
        False,  # OffsetReverse1
        False,  # OffsetReverse2
        False,  # TranslateSurface1
        False,  # TranslateSurface2
        False,  # NormalCut
        True,  # UseFeatScope
        True,  # UseAutoSelect
        True,  # AssemblyFeatureScope
        True,  # AutoSelectComponents
        False,  # PropagateFeatureToParts
        0,  # T0
        0.0,  # StartOffset
        False,  # FlipStartOffset
        False,  # OptimizeGeometry
    )
    if cut is None:
        raise RuntimeError("FeatureCut4 returned None for seed hole")
    cut.Name = "Hole_Seed"
    return cut  # return the IFeature so caller can Select2 on it


def _select_plane_and_seed(doc, seed_feat) -> bool:
    """Mark=2 for the mirror plane, Mark=1 for the seed feature.

    UPDATED 2026-05-17 (same fix as Spike R): doc.Extension.SelectByID2
    raises Type mismatch on the Callout OUT-param. Pivot to:
      1. Plane via 5-arg SelectByID(name, "PLANE", 0,0,0) then
         SetSelectedObjectMark(1, mark=2, action=Set).
      2. Seed via IFeature.Select2(append=True, mark=1).
    """
    doc.ClearSelection2(True)
    sel_mgr = doc.SelectionManager

    # 1. Plane via SelectByID (non-appending)
    try:
        ok_plane = doc.SelectByID("Right Plane", "PLANE", 0.0, 0.0, 0.0)
        print(f"  SelectByID('Right Plane', 'PLANE') -> {ok_plane}")
        if not ok_plane:
            return False
        ok_mark = sel_mgr.SetSelectedObjectMark(1, 2, 0)
        print(f"  SetSelectedObjectMark(1, mark=2, set) -> {ok_mark}")
    except Exception as e:
        print(f"  ! plane selection raised: {e!r}")
        traceback.print_exc()
        return False

    # 2. Seed via IFeature.Select2 with append=True
    try:
        ok_seed = seed_feat.Select2(True, 1)  # append=True, mark=1
        print(f"  IFeature.Select2(append=True, mark=1) -> {ok_seed}")
    except Exception as e:
        print(f"  ! IFeature.Select2 raised: {e!r}")
        traceback.print_exc()
        return False

    n = sel_mgr.GetSelectedObjectCount2(-1)
    print(f"  total selected count: {n}")
    for idx in range(1, n + 1):
        m = sel_mgr.GetSelectedObjectMark(idx)
        print(f"    selection[{idx}] mark = {m}")

    return True


def _try_insert_mirror_feature2(fm) -> int:
    """5-arg call."""
    print("-- InsertMirrorFeature2 (5 args) --")
    try:
        f = fm.InsertMirrorFeature2(
            False,  # BMirrorBody (false = mirror features, not bodies)
            False,  # BGeometryPattern
            False,  # BMerge (irrelevant for non-body)
            False,  # BKnit (irrelevant for non-body)
            0,  # ScopeOptions: 0 = swFeatureScope_AllBodies (per CHM)
        )
        print(f"  InsertMirrorFeature2 -> {f!r}")
        if f is None:
            print("  ! returned None -- selection probably wrong shape")
            return 11
        f.Name = "Mirror_Test"
        print(f"  mirror feature: {f.Name}")
        return 0
    except Exception as e:
        print(f"  ! InsertMirrorFeature2 raised: {e!r}")
        traceback.print_exc()
        return 12


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("could not create blank doc")
        return 2

    print("== Spike S: mirror via InsertMirrorFeature2 ==")

    try:
        _create_box(doc, side_mm=20.0, thick_mm=10.0)
        print(f"  box built; feature count = {doc.GetFeatureCount}")

        seed_feat = _create_seed_hole(doc)
        print(f"  seed hole built; feature count = {doc.GetFeatureCount}")

        fm = doc.FeatureManager

        if not _select_plane_and_seed(doc, seed_feat):
            print("== Spike S RED -- SelectByID2 selection failed ==")
            return 3

        rc = _try_insert_mirror_feature2(fm)
        print(f"  result: {'GREEN' if rc == 0 else f'RED (rc={rc})'}")
        print(f"  final feature count: {doc.GetFeatureCount}")

        if rc == 0:
            print("== Spike S: mirror viable via single-call API. ==")
            return 0
        print("== Spike S: mirror NOT viable via single-call. ==")
        return 3

    except Exception as e:
        print(f"! spike S exception: {e!r}")
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
