"""
Spike R: linear pattern via FeatureLinearPattern5 (single-call).

Builds a box, adds a small through-hole near one corner, then linear-patterns
the hole feature 3x along the X direction with 5mm spacing.

API: IFeatureManager::FeatureLinearPattern5 -- 22 args.
Marked obsolete in CHM in favor of CreateFeature(ILinearPatternFeatureData),
BUT the obsolete-since-2020 advice has historically still worked at runtime
(see the swSimpleFilletFeatureData2 case). Test the single-call form first;
if it works, the bridge uses it. If it doesn't, fall back to CreateDefinition.

Selection protocol (per SW API conventions for pattern features):
  1. Select the SEED FEATURE(s) to pattern -- mark = 4 (swSelPatternBody).
     Selecting via the feature node's name: doc.Extension.SelectByID2(
     "Hole_Seed", "BODYFEATURE", 0, 0, 0, True, 4, ...).
     Late-binding-safe alternative: select the feature face/edge with
     SelectByID and mark=4.
  2. Select the DIRECTION 1 reference -- mark = 1 (swSelPatternRefEdge).
     This is an edge or axis whose direction defines the pattern axis.
     For our box, the +X edge of the top face works.
  3. (Optional) Direction 2 reference -- mark = 2.

The Mark values matter -- SW reads selection by mark to disambiguate roles.
SelectByID's 6th-to-last arg is Mark. Our existing code uses 5-arg SelectByID
(works for fillet/extrude because they don't need marked selections), but
for patterns we need the marked variant via doc.Extension.SelectByID2.

Risk: SelectByID2 has historically failed on this build due to the OUT-param
Callout marshalling issue (see MMP_DEBUG_SESSION.md). If marked selection
via SelectByID2 fails, we'd need an alternative -- possibly:
  a) Try selectByID without mark (some pattern APIs default mark=0 OK)
  b) Use IModelDoc2::SelectByMark on existing selection
  c) Pivot to CreateDefinition path

Usage:
    python spikes/v0_3/spike_r_linear_pattern.py
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
    """Cut a 3mm-diameter through-hole at (-7, -7) on the top face.
    Returns the feature name for later seed selection."""
    fm = doc.FeatureManager
    # Select the top face (z = 0.01 for 10mm extrude). The +z face center
    # is at (0, 0, 0.01); any point on the face works.
    doc.ClearSelection2(True)
    if not doc.SelectByID("", "FACE", 0.0, 0.0, 0.01):
        raise RuntimeError("could not select +z face for seed sketch")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    # Circle center at (-7mm, -7mm). The face-sketch origin == part-origin
    # projection for this centered box.
    cx, cy = -0.007, -0.007
    r = 0.0015  # 3mm diameter -> 1.5mm radius
    sm.CreateCircle(cx, cy, 0.0, cx + r, cy, 0.0)
    sm.InsertSketch(True)

    # Cut-extrude through all
    doc.ClearSelection2(True)
    # The sketch we just closed is the most-recent feature; select it via
    # FeatureByPositionReverse and select it in the doc for cut-extrude.
    sketch_feat = doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no sketch produced for seed hole")
    sketch_feat.Name = "SK_Hole_Seed"
    sketch_feat.Select2(False, 0)

    # Use FeatureCut4 (27 args -- canonical layout from
    # src/ai_sw_bridge/spec/builder.py::_call_feature_cut, verified by
    # Spike E7).
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
        False,  # NormalCut (sheet metal only)
        True,  # UseFeatScope
        True,  # UseAutoSelect
        True,  # AssemblyFeatureScope
        True,  # AutoSelectComponents
        False,  # PropagateFeatureToParts
        0,  # T0
        0.0,  # StartOffset
        False,  # FlipStartOffset
        False,  # OptimizeGeometry (sheet metal only)
    )
    if cut is None:
        raise RuntimeError("FeatureCut4 returned None for seed hole")
    cut.Name = "Hole_Seed"
    return cut  # return the IFeature directly so callers can use Select2 on it


def _select_seed_and_direction(doc, seed_feat) -> bool:
    """Mark seed feature with mark=4, and a top edge with mark=1 as direction.

    UPDATED 2026-05-17 after first run: doc.Extension.SelectByID2 raises
    com_error('Type mismatch.', ..., 8) -- the Callout OUT-param at arg 8
    doesn't marshal through pywin32 late binding. Same class of failure
    as the prior SelectByID2 issue documented in MMP_DEBUG_SESSION.md.

    Pivot:
      - For the seed: use IFeature::Select2(append, mark) -- 2-arg
        method on the feature object itself, no name lookup, no Callout.
      - For the direction edge: use plain 5-arg SelectByID (which is
        proven to work elsewhere in the bridge) and *then* apply a mark
        post-hoc via ISelectionMgr.SetSelectionMark2. Same end-state,
        no Callout exposure.

    Returns True if both selections succeed.
    """
    doc.ClearSelection2(True)
    sel_mgr = doc.SelectionManager

    # ORDER MATTERS: SelectByID is non-appending by default, so we do
    # the EDGE first, then apply its mark, then add the SEED with
    # IFeature.Select2(append=True). Reverse order clears the seed.

    # 1. Direction edge via SelectByID
    try:
        ok_dir = doc.SelectByID("", "EDGE", 0.01, 0.0, 0.01)
        print(f"  SelectByID(EDGE) -> {ok_dir}")
        if not ok_dir:
            return False
        # Mark the edge as direction reference (mark=1, action=Set=0)
        ok_dir_mark = sel_mgr.SetSelectedObjectMark(1, 1, 0)
        print(f"  SetSelectedObjectMark(1, mark=1, set) -> {ok_dir_mark}")
    except Exception as e:
        print(f"  ! direction edge selection raised: {e!r}")
        traceback.print_exc()
        return False

    # 2. Seed feature via IFeature.Select2 with APPEND=True
    try:
        ok_seed = seed_feat.Select2(True, 4)  # append=True, mark=4
        print(f"  IFeature.Select2(append=True, mark=4) -> {ok_seed}")
    except Exception as e:
        print(f"  ! IFeature.Select2 raised: {e!r}")
        traceback.print_exc()
        return False

    # Sanity: should have 2 items
    n = sel_mgr.GetSelectedObjectCount2(-1)
    print(f"  total selected count: {n}")
    for idx in range(1, n + 1):
        m = sel_mgr.GetSelectedObjectMark(idx)
        print(f"    selection[{idx}] mark = {m}")

    return True


def _try_feature_linear_pattern5(fm) -> int:
    """22-arg FeatureLinearPattern5 call. 3 copies, 5mm spacing, X-only."""
    print("-- Path 1: FeatureLinearPattern5 (22 args) --")
    try:
        f = fm.FeatureLinearPattern5(
            3,  # Num1: 3 instances along Direction 1
            0.005,  # Spacing1: 5mm
            1,  # Num2: 1 (no second direction)
            0.0,  # Spacing2
            False,
            False,  # FlipDir1, FlipDir2
            "",
            "",  # DName1, DName2 (no driving dim names)
            False,  # GeometryPattern
            False,  # VaryInstance
            False,
            False,  # HasOffset1, HasOffset2
            False,
            False,  # CtrlByNum1, CtrlByNum2
            False,
            False,  # FromCentroid1, FromCentroid2
            False,
            False,  # RevOffset1, RevOffset2
            0.0,
            0.0,  # Offset1, Offset2
            False,  # D2PatternSeedOnly
            False,  # SyncSubAssemblies
        )
        print(f"  FeatureLinearPattern5 -> {f!r}")
        if f is None:
            print("  ! returned None -- selection probably missing seed or direction")
            return 11
        f.Name = "LPattern_PathOne"
        print(f"  pattern feature: {f.Name}")
        return 0
    except Exception as e:
        print(f"  ! FeatureLinearPattern5 raised: {e!r}")
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

    print("== Spike R: linear pattern via FeatureLinearPattern5 ==")

    try:
        _create_box(doc, side_mm=20.0, thick_mm=10.0)
        print(f"  box built; feature count = {doc.GetFeatureCount}")

        seed_feat = _create_seed_hole(doc)
        print(f"  seed hole built; feature count = {doc.GetFeatureCount}")

        fm = doc.FeatureManager

        if not _select_seed_and_direction(doc, seed_feat):
            print("  ! could not establish seed + direction selection")
            print("  PATH 1 NOT ATTEMPTED.")
            print("== Spike R RED -- SelectByID2 marked-selection failed ==")
            return 3

        rc1 = _try_feature_linear_pattern5(fm)
        print(f"  PATH 1 result: {'GREEN' if rc1 == 0 else f'RED (rc={rc1})'}")
        print(f"  final feature count: {doc.GetFeatureCount}")

        if rc1 == 0:
            print("== Spike R: linear-pattern viable via single-call API. ==")
            return 0
        print("== Spike R: linear-pattern NOT viable via single-call. ==")
        print("    Next attempt would be CreateDefinition + ILinearPatternFeatureData")
        return 3

    except Exception as e:
        print(f"! spike R exception: {e!r}")
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
