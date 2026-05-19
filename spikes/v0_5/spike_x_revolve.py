"""Spike X: probe IFeatureManager.FeatureRevolve2 via pywin32 late-binding.

CHM-verified 20-arg signature (extracted 2026-05-19):
  1.  SingleDir                  bool
  2.  IsSolid                    bool
  3.  IsThin                     bool
  4.  IsCut                      bool
  5.  ReverseDir                 bool
  6.  BothDirectionUpToSameEntity bool
  7.  Dir1Type                   int (swEndConditions_e)
  8.  Dir2Type                   int
  9.  Dir1Angle                  double (radians)
  10. Dir2Angle                  double
  11. OffsetReverse1             bool
  12. OffsetReverse2             bool
  13. OffsetDistance1            double
  14. OffsetDistance2            double
  15. ThinType                   int (swThinWallType_e; 0=OneDirection)
  16. ThinThickness1             double
  17. ThinThickness2             double
  18. Merge                      bool
  19. UseFeatScope               bool
  20. UseAutoSelect              bool

Goal: verify that a sketch containing
  (1) a closed profile (rectangle) offset from the y-axis, AND
  (2) a centerline (construction line) along the x-axis
can be revolved 360 degrees to produce a hollow tube, with only the
sketch pre-selected (i.e. SW auto-picks the embedded centerline as
the axis of revolution).

If this works, the v0.5 `revolve_boss` spec primitive can just embed
a `centerline` field in existing rectangle/circle plane-sketch types,
keeping the spec atomic.

Test geometry:
  Profile rectangle on Front Plane: x=[20,50] mm, y=[2,8] mm.
  Centerline along x-axis: from (-60,0) to (+60,0).
  Revolve 360 deg.
Expected result: tube outer radius 8 mm, inner radius 2 mm, axis
along x from x=20 to x=50.
  body bbox (mm): x=[20,50], y=[-8,8], z=[-8,8]
  face count: ~4 (outer cyl + inner cyl + 2 annular caps)

Run from venv-freshtest. Standalone -- prints diagnostics and leaves
the part open for inspection.
"""
import math
import pythoncom
import win32com.client

SW_END_COND_BLIND = 0
SW_THIN_WALL_ONE_DIRECTION = 0


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("! NewDocument returned None")
        return

    sm = doc.SketchManager
    fm = doc.FeatureManager

    # ----- Step 1: open Front-plane sketch -----
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    print("opened Front-plane sketch")

    # ----- Step 2: draw profile rectangle: x=[20,50], y=[2,8] (mm) -----
    rect = sm.CreateCornerRectangle(0.020, 0.002, 0.0, 0.050, 0.008, 0.0)
    print(f"profile rectangle: {rect!r}")

    # ----- Step 3: draw centerline along x-axis -----
    # Try CreateCenterLine first; if missing, fall back to CreateLine +
    # set ConstructionGeometry on the returned segment.
    centerline = None
    construction_method = "unknown"
    try:
        centerline = sm.CreateCenterLine(-0.060, 0.0, 0.0, 0.060, 0.0, 0.0)
        construction_method = "CreateCenterLine"
        print(f"CreateCenterLine result: {centerline!r}")
    except Exception as e_cl:
        print(f"CreateCenterLine ERR: {e_cl!r} -- falling back to CreateLine")
        try:
            line = sm.CreateLine(-0.060, 0.0, 0.0, 0.060, 0.0, 0.0)
            print(f"CreateLine result: {line!r}")
            if line is not None:
                try:
                    line.ConstructionGeometry = True
                    construction_method = "CreateLine+CG"
                    print(f"  ConstructionGeometry=True set; readback: "
                          f"{line.ConstructionGeometry}")
                except Exception as e_cg:
                    print(f"  ConstructionGeometry set ERR: {e_cg!r}")
                    construction_method = "CreateLine_noCG"
            centerline = line
        except Exception as e_l:
            print(f"CreateLine ERR: {e_l!r}")
    print(f"centerline made via: {construction_method}")

    # ----- Step 4: close sketch, rename -----
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Profile"
    print(f"sketch closed: name={sk.Name!r}, type={sk.GetTypeName!r}")

    # ----- Step 5: pre-select sketch and call FeatureRevolve2 -----
    doc.ClearSelection2(True)
    ok = doc.SelectByID("SK_Profile", "SKETCH", 0, 0, 0)
    print(f"sketch pre-select: {ok}")

    angle_rad = 2.0 * math.pi  # 360 degrees

    print()
    print("=== Calling FeatureRevolve2 (20 args, CHM-verified) ===")
    try:
        rev = fm.FeatureRevolve2(
            True,                       # 1  SingleDir
            True,                       # 2  IsSolid
            False,                      # 3  IsThin
            False,                      # 4  IsCut
            False,                      # 5  ReverseDir
            False,                      # 6  BothDirectionUpToSameEntity
            SW_END_COND_BLIND,          # 7  Dir1Type
            0,                          # 8  Dir2Type (ignored)
            angle_rad,                  # 9  Dir1Angle (radians)
            0.0,                        # 10 Dir2Angle
            False,                      # 11 OffsetReverse1
            False,                      # 12 OffsetReverse2
            0.0,                        # 13 OffsetDistance1
            0.0,                        # 14 OffsetDistance2
            SW_THIN_WALL_ONE_DIRECTION, # 15 ThinType
            0.0,                        # 16 ThinThickness1
            0.0,                        # 17 ThinThickness2
            True,                       # 18 Merge
            True,                       # 19 UseFeatScope
            True,                       # 20 UseAutoSelect
        )
        print(f"  result: {rev!r}")
        if rev is not None:
            print(f"  Name: {rev.Name!r}, type: {rev.GetTypeName!r}")
            rev.Name = "REV_Test"
    except Exception as e:
        print(f"  FeatureRevolve2 ERR: {e!r}")
        rev = None

    # ----- Step 6: verify body geometry -----
    print()
    bodies = doc.GetBodies2(0, True)
    if bodies and len(bodies) > 0:
        bb = bodies[0].GetBodyBox()
        print(f"body bbox (mm): "
              f"x=[{bb[0]*1000:.2f},{bb[3]*1000:.2f}] "
              f"y=[{bb[1]*1000:.2f},{bb[4]*1000:.2f}] "
              f"z=[{bb[2]*1000:.2f},{bb[5]*1000:.2f}]")
        print("expected:        x=[20.00,50.00] y=[-8.00,8.00] z=[-8.00,8.00]")
        faces = bodies[0].GetFaces()
        n_faces = len(faces) if faces else 0
        print(f"face count: {n_faces} (expected ~4: outer cyl + inner cyl + 2 caps)")
    else:
        print("!! no body produced -- revolve failed")

    print()
    print(">>> Probe summary:")
    print(f"    centerline_method  = {construction_method}")
    print(f"    revolve2_args      = 20")
    print(f"    revolve2_success   = {rev is not None}")


if __name__ == "__main__":
    main()
