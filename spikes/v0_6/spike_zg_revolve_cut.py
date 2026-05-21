"""Spike ZG: probe FeatureRevolve2 with IsCut=True via pywin32 late-binding.

Context: v0.5 shipped `revolve_boss` (Spike X, 2026-05-19). The DriveRoller
part (S1b-004, design guide §13.2 Step 2) needs an O-ring groove cut around
its cylindrical axis -- a revolved cut. The 20-arg FeatureRevolve2 takes
`IsCut` as arg 4; flipping it from the boss case is the only structural
difference we expect. But we have never tested this on SW 2024 SP1.

Risky questions this spike answers:
  Q1. Does FeatureRevolve2(IsCut=True, ...) succeed at all via pywin32
      late-binding, or does it fail like FeatureCut4 used to (PARAMNOTOPTIONAL
      / 27-vs-25 arg drift)?
  Q2. Does the "sketch-only pre-select; SW auto-detects the embedded
      centerline" workflow also work for cuts? (For boss it does -- Spike X.)
  Q3. Does the cut produce the expected subtractive geometry, or does SW
      reject it because the profile doesn't intersect the existing body
      tangentially-enough?

Test geometry: mirror the S1b DriveRoller's O-ring groove without being
the actual part (Sonnet builds the part later in a fresh session).

  Step 1: Build base cylinder: Ø25 x 80 mm along the Y axis.
          Front-plane circle profile centered at origin, extruded +Z 80 mm
          gives a Z-axis cylinder. Easier to mirror DriveRoller's Y-axis
          orientation: Top-plane circle profile centered at origin,
          extruded +Y 80 mm gives a Y-axis cylinder. Use Top plane.

  Step 2: Right-plane sketch: 5 x 1 mm rectangle representing the groove
          cross-section. Positioned so top edge is on the outer cylinder
          surface (at radial distance 12.5 mm = roller_dia/2) and 5mm
          axial width centered at the cylinder mid-length (y = 40).

          Top edge (further from axis): z = 12.5 (= cylinder outer radius)
          Bottom edge (toward axis):    z = 11.5 (= outer radius - 1mm)
          -- profile sits in the wall of the cylinder, 1mm deep.

          On Right Plane (YZ plane, x=0), sketch local coords are
          (sketch_x = part_y, sketch_y = part_z). So a 5x1 mm rectangle
          with sketch corners at (37.5, 11.5) to (42.5, 12.5) puts the
          profile correctly in place.

          Plus a centerline along the y-axis -- in Right-Plane sketch
          coords that's (sketch_x, sketch_y) = (-60, 0) to (60, 0).

  Step 3: Pre-select sketch, call FeatureRevolve2 with IsCut=True, 360 deg.

Expected: cylinder with a circumferential groove at y=[37.5, 42.5],
outer radius drops from 12.5 to 11.5 in that band. Body bbox unchanged
in x/z extent (still +-12.5). Face count grows from 3 (cyl + 2 caps) to
5 (cyl-before-groove + groove-floor + cyl-after-groove + 2 caps) plus
possibly two annular shoulder faces -> ~5-7 faces.

Run from venv-freshtest. Standalone -- prints diagnostics and leaves the
part open for inspection.
"""

import math
import pythoncom
import win32com.client

SW_END_COND_BLIND = 0
SW_THIN_WALL_ONE_DIRECTION = 0


def main() -> None:
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("! NewDocument returned None")
        return

    sm = doc.SketchManager
    fm = doc.FeatureManager

    # ============================================================
    # Step 1: base cylinder Ø25 x 80mm along Y axis (Top-plane circle)
    # ============================================================
    doc.SelectByID("Top Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    # CreateCircle(xc,yc,zc, xp,yp,zp) -- center at sketch origin, perimeter
    # at radius 12.5mm. On Top Plane the sketch is XZ so use the third coord
    # for the perimeter point (sketch local Y=0 in 3D = part Y=0).
    sm.CreateCircle(0.0, 0.0, 0.0, 0.0125, 0.0, 0.0)
    sm.InsertSketch(True)
    sk_base = doc.FeatureByPositionReverse(0)
    sk_base.Name = "SK_Base"
    print(f"base sketch: {sk_base.Name!r}")

    # Extrude +Y 80mm
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Base", "SKETCH", 0, 0, 0)
    extrude_args = (
        True,  # 1  Sd
        False,  # 2  Flip
        False,  # 3  Dir
        SW_END_COND_BLIND,  # 4  T1
        0,  # 5  T2
        0.080,  # 6  D1 (80mm)
        0.0,  # 7  D2
        False,  # 8  Dchk1
        False,  # 9  Dchk2
        False,  # 10 Ddir1
        False,  # 11 Ddir2
        0.0,  # 12 Dang1
        0.0,  # 13 Dang2
        False,  # 14 OffsetReverse1
        False,  # 15 OffsetReverse2
        False,  # 16 TranslateSurface1
        False,  # 17 TranslateSurface2
        True,  # 18 Merge
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
        0,  # 21 T0 (swStartSketchPlane)
        0.0,  # 22 StartOffset
        False,  # 23 FlipStartOffset
    )
    base = fm.FeatureExtrusion2(*extrude_args)
    if base is None:
        print("! FeatureExtrusion2 returned None for base cylinder")
        return
    base.Name = "EX_Base"
    print(f"base cylinder built: {base.Name!r}")

    bodies = doc.GetBodies2(0, True)
    if bodies and len(bodies) > 0:
        bb = bodies[0].GetBodyBox()
        print(
            f"  base bbox (mm): "
            f"x=[{bb[0]*1000:.2f},{bb[3]*1000:.2f}] "
            f"y=[{bb[1]*1000:.2f},{bb[4]*1000:.2f}] "
            f"z=[{bb[2]*1000:.2f},{bb[5]*1000:.2f}]"
        )
        print("  expected:       x=[-12.50,12.50] y=[0.00,80.00] z=[-12.50,12.50]")

    # ============================================================
    # Step 2: groove profile sketch on Right Plane (YZ) + centerline
    # ============================================================
    doc.ClearSelection2(True)
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)

    # Rectangle: sketch corners (in Right-Plane local: sketch_x=part_y,
    # sketch_y=part_z). Place at (37.5, 11.5) to (42.5, 12.5).
    # Top edge at z=12.5 = cylinder outer radius. Bottom at z=11.5.
    rect = sm.CreateCornerRectangle(
        0.0375,
        0.0115,
        0.0,  # corner 1: y=37.5, z=11.5
        0.0425,
        0.0125,
        0.0,  # corner 2: y=42.5, z=12.5
    )
    print(f"groove profile rectangle: {rect!r}")

    # Centerline along y-axis: sketch_x = part_y from -60 to +60, sketch_y=0.
    centerline = sm.CreateCenterLine(-0.060, 0.0, 0.0, 0.060, 0.0, 0.0)
    print(f"groove centerline: {centerline!r}")

    sm.InsertSketch(True)
    sk_groove = doc.FeatureByPositionReverse(0)
    sk_groove.Name = "SK_Groove"
    print(f"groove sketch: {sk_groove.Name!r}")

    # ============================================================
    # Step 3: pre-select sketch and call FeatureRevolve2 with IsCut=True
    # ============================================================
    doc.ClearSelection2(True)
    ok = doc.SelectByID("SK_Groove", "SKETCH", 0, 0, 0)
    print(f"sketch pre-select: {ok}")

    angle_rad = 2.0 * math.pi  # 360 deg

    print()
    print("=== Calling FeatureRevolve2 with IsCut=True ===")
    cut_args = (
        True,  # 1  SingleDir
        True,  # 2  IsSolid
        False,  # 3  IsThin
        True,  # 4  IsCut    <-- the only diff from Spike X
        False,  # 5  ReverseDir
        False,  # 6  BothDirectionUpToSameEntity
        SW_END_COND_BLIND,  # 7  Dir1Type
        0,  # 8  Dir2Type
        angle_rad,  # 9  Dir1Angle (radians)
        0.0,  # 10 Dir2Angle
        False,  # 11 OffsetReverse1
        False,  # 12 OffsetReverse2
        0.0,  # 13 OffsetDistance1
        0.0,  # 14 OffsetDistance2
        SW_THIN_WALL_ONE_DIRECTION,  # 15 ThinType
        0.0,  # 16 ThinThickness1
        0.0,  # 17 ThinThickness2
        True,  # 18 Merge
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
    )
    try:
        cut = fm.FeatureRevolve2(*cut_args)
        print(f"  result: {cut!r}")
        if cut is not None:
            print(f"  Name: {cut.Name!r}, type: {cut.GetTypeName!r}")
            cut.Name = "REVCUT_Groove"
    except Exception as e:
        print(f"  FeatureRevolve2(IsCut=True) ERR: {e!r}")
        cut = None

    # ============================================================
    # Step 4: verify body shape changed
    # ============================================================
    print()
    bodies = doc.GetBodies2(0, True)
    if bodies and len(bodies) > 0:
        bb = bodies[0].GetBodyBox()
        print(
            f"after-cut body bbox (mm): "
            f"x=[{bb[0]*1000:.2f},{bb[3]*1000:.2f}] "
            f"y=[{bb[1]*1000:.2f},{bb[4]*1000:.2f}] "
            f"z=[{bb[2]*1000:.2f},{bb[5]*1000:.2f}]"
        )
        print(
            "expected (unchanged):     x=[-12.50,12.50] y=[0.00,80.00] z=[-12.50,12.50]"
        )
        faces = bodies[0].GetFaces()
        n_faces = len(faces) if faces else 0
        print(f"face count: {n_faces} (base was 3 cyl+2caps; expect ~5-7 after groove)")
    else:
        print("!! no body produced -- something went very wrong")

    print()
    print(">>> Probe summary:")
    print(f"    revolve_cut_args   = 20 (IsCut=True at arg 4)")
    print(f"    revolve_cut_success= {cut is not None}")


if __name__ == "__main__":
    main()
