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

    # Use FeatureCut4 (27 args -- verified by Spike E7).
    cut = fm.FeatureCut4(
        True,
        False,
        False,  # Sd, Flip, Dir
        SW_END_COND_THROUGH_ALL,
        0,  # EndCondition, EndCondition2
        0.0,
        0.0,  # Depth, Depth2
        False,
        False,
        False,
        False,  # Dchk, Dchk2, Ddir, Ddir2
        0.0,
        0.0,  # Dang, Dang2
        False,
        False,
        False,
        False,  # OffsetReverse, OffsetReverse2, TranslateSurface, TranslateSurface2
        True,
        True,
        True,  # NormalCut, UseFeatScope, UseAutoSelect
        0,  # T0
        0,  # StartCondition
        0.0,  # StartOffset
        False,  # FlipStartOffset
        False,  # AssemblyFeatureScope
        False,  # AutoSelectComponents
        False,  # PropagateFeatureToParts
        False,  # OptimizeGeometry (sheet metal)
    )
    if cut is None:
        raise RuntimeError("FeatureCut4 returned None for seed hole")
    cut.Name = "Hole_Seed"
    return "Hole_Seed"


def _select_seed_and_direction(doc, seed_feat_name: str) -> bool:
    """Mark seed feature with mark=4, and a top edge with mark=1 as direction.

    Uses doc.Extension.SelectByID2 because SelectByID(name=..., type=BODYFEATURE)
    doesn't accept a mark parameter (5-arg form). SelectByID2 may fail under
    late binding due to Callout OUT-param marshalling -- we will see.

    Returns True if both selections appear to have succeeded.
    """
    doc.ClearSelection2(True)
    ext = doc.Extension

    # SelectByID2 args (per CHM):
    #   Name, Type, X, Y, Z, Append, Mark, Callout, SelectOption
    # 9 args total. The Callout (CDispatch) is the OUT-param risk.
    # In Python late-binding, passing None for OUT params usually marshals
    # fine for *IN* args but Callout is mixed.

    # 1. Select seed feature by name (mark = 4)
    try:
        ok_seed = ext.SelectByID2(
            seed_feat_name,
            "BODYFEATURE",
            0.0,
            0.0,
            0.0,
            False,  # Append
            4,  # Mark = swSelPatternBody / pattern seed
            None,  # Callout
            0,  # SelectOption (default)
        )
        print(f"  SelectByID2(seed) -> {ok_seed}")
    except Exception as e:
        print(f"  ! SelectByID2(seed) raised: {e!r}")
        return False

    # 2. Select direction edge (top +X edge midpoint), mark = 1
    try:
        ok_dir = ext.SelectByID2(
            "",
            "EDGE",
            0.01,
            0.0,
            0.01,
            True,  # Append
            1,  # Mark = direction reference
            None,
            0,
        )
        print(f"  SelectByID2(direction edge) -> {ok_dir}")
    except Exception as e:
        print(f"  ! SelectByID2(direction edge) raised: {e!r}")
        return False

    return bool(ok_seed) and bool(ok_dir)


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

        seed_name = _create_seed_hole(doc)
        print(f"  seed hole built; feature count = {doc.GetFeatureCount}")

        fm = doc.FeatureManager

        if not _select_seed_and_direction(doc, seed_name):
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
