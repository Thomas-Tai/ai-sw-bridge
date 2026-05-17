"""
Spike Q: chamfer via InsertFeatureChamfer (single-call) vs CreateDefinition.

Adds a constant-equal-distance chamfer to one edge of a 20x20x10 box. Tests
both possible API paths so we can pick the more reliable one for the bridge:

  Path 1 (single-call, oldest, simplest):
      f = fm.InsertFeatureChamfer(Options, ChamferType, Width, Angle,
                                  OtherDist, V1, V2, V3)
      -- 8 args. Pre-select edge(s) via SelectByID("EDGE", x, y, z).
      -- swChamferType_e.swChamferEqualDistance = 16 (per CHM)
      -- swChamferType_e.swChamferAngleDistance = 1
      -- swChamferType_e.swChamferDistanceDistance = 2
      -- Available since SW 2005 FCS. No 'Obsolete' marker on the doc page,
         but for fillet the obsolete-since-2020 advice is to use
         CreateDefinition. Chamfer's page doesn't say obsolete - test it.

  Path 2 (SW 2020+ canonical, parallels Spike P fillet path):
      data = fm.CreateDefinition(swFmChamfer)
      data.Initialize(...) ? -- IChamferFeatureData2 doesn't have a published
                               Initialize method like ISimpleFilletFeatureData2;
                               check by trying.
      data.<set props>
      fm.CreateFeature(data)
      -- swFmChamfer numeric value is not in the decompiled CHM enum table
         (text-only, same situation as swFmFillet). Probe 0..40 same way.

Why both: if Path 1 works, the bridge handler is dead simple (no probe at
build time, no data-object marshalling risk). Path 2 is needed if Path 1
fails or behaves weirdly under late binding -- this happened with FeatureCut4
(arg count was wrong) and the AddSpecificDimension OUT-param issue.

Output: prints the result of each path attempt. If both fail, the spike
points at the deepest failure for follow-up.

Usage (from venv with pywin32, with SW running and a doc-free instance):
    python spikes/v0_3/spike_q_chamfer.py
"""

from __future__ import annotations

import sys
import traceback

import pythoncom
import win32com.client


SW_END_COND_BLIND = 0
SW_START_SKETCH_PLANE = 0

# swChamferType_e (numeric values explicit in decompiled CHM swconst, unlike
# the swFm* family). Source: swChamferType_e.html.
SW_CHAMFER_ANGLE_DISTANCE = 1
SW_CHAMFER_DISTANCE_DISTANCE = 2
SW_CHAMFER_VERTEX = 3
SW_CHAMFER_EQUAL_DISTANCE = 16

# swFeatureChamferOption_e flags (Options bitfield). Source:
# swFeatureChamferOption_e.html.
SW_FCO_FLIP_DIR = 1
SW_FCO_KEEP_FEATURE = 2
SW_FCO_TANGENT_PROPAGATION = 4
SW_FCO_PROPAGATE_FEAT_TO_PARTS = 8


def _create_box(doc, side_mm: float, thick_mm: float) -> None:
    """Sketch a center rectangle on Front Plane and extrude it.

    Same scaffolding Spike P uses; copied so the spike file is self-contained
    and doesn't need to import from another spike.
    """
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


def _select_top_edge(doc) -> bool:
    """Select the +X edge of the box's top face. Box is 20mm side on Front
    Plane (XY), extruded 10mm in +Z. Top face is at z=0.01m. The +X edge
    runs along (x=0.01, y in [-0.01, 0.01], z=0.01). Midpoint: (0.01, 0, 0.01).
    """
    doc.ClearSelection2(True)
    return bool(doc.SelectByID("", "EDGE", 0.01, 0.0, 0.01))


def _try_path_1(doc, fm) -> int:
    """InsertFeatureChamfer single-call. Returns 0 on success, nonzero on
    failure with a diagnostic printed."""
    print("-- Path 1: InsertFeatureChamfer (8 args, single call) --")
    if not _select_top_edge(doc):
        print("  ! could not select top +X edge of box")
        return 11

    distance_m = 0.001  # 1 mm chamfer
    try:
        f = fm.InsertFeatureChamfer(
            SW_FCO_TANGENT_PROPAGATION,  # Options bitfield (try tangent prop)
            SW_CHAMFER_EQUAL_DISTANCE,  # ChamferType: equal-distance
            0.0,  # Width (used only for AngleDist)
            0.0,  # Angle (used only for AngleDist)
            distance_m,  # OtherDist (equal-distance value)
            0.0,
            0.0,
            0.0,  # Vertex distances (only for Vertex)
        )
        print(f"  InsertFeatureChamfer -> {f!r}")
        if f is None:
            print("  ! returned None -- edge selection probably wrong type")
            return 12
        f.Name = "Chamfer_PathOne"
        print(f"  Chamfer feature: {f.Name}")
        print(f"  feature count: {doc.GetFeatureCount}")
        return 0
    except Exception as e:
        print(f"  ! InsertFeatureChamfer raised: {e!r}")
        traceback.print_exc()
        return 13


def _probe_swFmChamfer(fm) -> int | None:
    """The swFm* enum int values are not in the decompiled CHM for our build
    (same as swFmFillet). Probe a small window of values, looking for one
    whose returned data object has an Initialize-shape method or accepts a
    property set without raising. Returns the int or None.

    Heuristic from Spike P: swFmFillet=1 was found in 0..59. swFmChamfer
    is alphabetically close so probably in the same range. We check for
    EdgeChamferAngle/EqualDistance property settability as a positive
    signal (these are unique to IChamferFeatureData2 per the CHM).
    """
    print("-- Probing swFmChamfer in CreateDefinition(0..49) --")
    for v in range(0, 50):
        try:
            data = fm.CreateDefinition(v)
            if data is None:
                continue
            # Try a chamfer-specific property -- if this CDispatch is actually
            # IChamferFeatureData2, this assignment won't raise. If it's some
            # other feature-data type, it WILL raise (or silently no-op,
            # which we can't detect, but the next step's CreateFeature will
            # surface the error).
            try:
                data.EqualDistance = True
                # If we got here without an exception, this is likely chamfer-shape.
                print(f"  candidate v={v}: EqualDistance set OK")
                return v
            except Exception:
                # Not chamfer; skip.
                continue
        except Exception:
            continue
    return None


def _try_path_2(doc, fm) -> int:
    """CreateDefinition(swFmChamfer) + IChamferFeatureData2 + CreateFeature.
    Returns 0 on success, nonzero on failure with a diagnostic printed.
    """
    print("-- Path 2: CreateDefinition + IChamferFeatureData2 + CreateFeature --")

    fm_chamfer = _probe_swFmChamfer(fm)
    if fm_chamfer is None:
        print("  ! could not find swFmChamfer in 0..49. Path 2 NOT VIABLE.")
        return 21
    print(f"  swFmChamfer candidate = {fm_chamfer}")

    data = fm.CreateDefinition(fm_chamfer)
    if data is None:
        print("  ! CreateDefinition returned None on second call")
        return 22

    # Set the chamfer to equal-distance, 1mm. Property names from CHM:
    # EqualDistance (bool), DefaultDistance (m). For Edge chamfers Type
    # property exists too; default is edge chamfer.
    try:
        data.EqualDistance = True
        data.DefaultDistance = 0.001  # 1 mm
        # Verify
        eq = data.EqualDistance
        dd = data.DefaultDistance
        print(f"  EqualDistance={eq}, DefaultDistance={dd}")
    except Exception as e:
        print(f"  ! property set failed: {e!r}")
        return 23

    # Select an edge before CreateFeature (selection set is the chamfer target)
    if not _select_top_edge(doc):
        print("  ! could not select top +X edge of box for Path 2")
        return 24

    try:
        f = fm.CreateFeature(data)
        print(f"  CreateFeature -> {f!r}")
        if f is None:
            print("  ! returned None")
            return 25
        f.Name = "Chamfer_PathTwo"
        print(f"  feature count: {doc.GetFeatureCount}")
        return 0
    except Exception as e:
        print(f"  ! CreateFeature raised: {e!r}")
        traceback.print_exc()
        return 26


def main() -> int:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("could not create blank doc")
        return 2

    print("== Spike Q: chamfer via two API paths ==")

    try:
        _create_box(doc, side_mm=20.0, thick_mm=10.0)
        print(f"  box built; feature count = {doc.GetFeatureCount}")

        fm = doc.FeatureManager

        rc1 = _try_path_1(doc, fm)
        print(f"  PATH 1 result: {'GREEN' if rc1 == 0 else f'RED (rc={rc1})'}")

        rc2 = _try_path_2(doc, fm)
        print(f"  PATH 2 result: {'GREEN' if rc2 == 0 else f'RED (rc={rc2})'}")

        if rc1 == 0:
            print("== Spike Q: Path 1 viable. Bridge can use InsertFeatureChamfer. ==")
            return 0
        if rc2 == 0:
            print("== Spike Q: Path 2 viable. Bridge needs CreateDefinition path. ==")
            return 0
        print("== Spike Q: NEITHER path worked. See diagnostics above. ==")
        return 3

    except Exception as e:
        print(f"! spike Q exception: {e!r}")
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
