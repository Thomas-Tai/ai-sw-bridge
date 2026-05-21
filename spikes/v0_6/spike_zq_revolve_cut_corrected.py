"""Spike ZQ: revolve-cut with CORRECTED Right Plane sketch coordinates.

Per Spike ZP, the Right Plane sketch-to-part mapping is:
  sketch_x -> -part_z  (i.e. sketch +x is part -z; axis flipped)
  sketch_y ->  part_y
  Right Plane normal = +part_x

All prior spikes (ZG-ZN) put the groove rectangle at sketch-local
(0.0375..0.0425, 0.0115..0.0125), which lands at part
(y=11.5..12.5, z=-42.5..-37.5) -- floating 37mm below the cylinder
origin, NOT on the cylinder surface. FeatureRevolve2 silently returned
None because the cut profile didn't intersect any material.

Corrected coordinates for groove at part-y=[37.5, 42.5] (axial mid-roller)
and part-z=[11.5, 12.5] (1mm-deep groove from cylinder surface):
  sketch_y = 37.5..42.5  (axial position on cylinder)
  sketch_x = -12.5..-11.5  (sketch_x = -part_z, so -12.5 -> +12.5 in z)

Centerline along the Y axis of revolution (= part_y direction):
  In sketch coords that's sketch_y axis -> centerline at sketch_x=0,
  spanning sketch_y from -60 to +60.

This spike:
  1. Builds the same Ø25 x 80mm cylinder along Y axis.
  2. Builds the groove sketch on Right Plane with CORRECTED coords.
  3. Pre-selects only the sketch (per Spike X boss-case pattern; the
     embedded centerline auto-disambiguates as axis).
  4. Calls FeatureRevolve2(IsCut=True, ...).

If GREEN: the silent-None across ZG-ZN was 100% the mapping bug. The
v0.5 boss-case "embedded centerline + sketch-only pre-select" pattern
works for cuts too, and the workflow's "30-min trivially adjacent
variant" assumption was correct.
"""

import math
import pythoncom
import win32com.client

SW_END_COND_BLIND = 0
SW_THIN_WALL_ONE_DIRECTION = 0


def build_base_cylinder(doc):
    sm = doc.SketchManager
    fm = doc.FeatureManager
    doc.SelectByID("Top Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.0125, 0.0, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Base"
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Base", "SKETCH", 0, 0, 0)
    base = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        0.080,
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
        0,
        0.0,
        False,
    )
    base.Name = "EX_Base"
    return base


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return

    print("Step 1: Build base cylinder Ø25 x 80mm along Y axis...")
    build_base_cylinder(doc)
    bodies = doc.GetBodies2(0, True)
    if bodies:
        bb = bodies[0].GetBodyBox()
        print(
            f"  cylinder bbox: "
            f"x=[{bb[0]*1000:+.2f},{bb[3]*1000:+.2f}] "
            f"y=[{bb[1]*1000:+.2f},{bb[4]*1000:+.2f}] "
            f"z=[{bb[2]*1000:+.2f},{bb[5]*1000:+.2f}]"
        )
        gf = bodies[0].GetFaces
        faces = gf() if callable(gf) else gf
        base_face_count = len(faces) if faces else 0
        print(f"  base face count: {base_face_count}")

    print("\nStep 2: Build groove sketch on Right Plane with CORRECTED coords")
    print("  Want part-y=[37.5,42.5], part-z=[11.5,12.5]")
    print("  Mapping: sketch_x=-part_z, sketch_y=part_y")
    print("  So sketch_x in [-12.5,-11.5], sketch_y in [37.5, 42.5]")
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(
        -0.0125,
        0.0375,
        0.0,  # corner 1: sketch_x=-12.5 (->part_z=12.5), sketch_y=37.5 (->part_y=37.5)
        -0.0115,
        0.0425,
        0.0,  # corner 2: sketch_x=-11.5 (->part_z=11.5), sketch_y=42.5 (->part_y=42.5)
    )
    # Centerline along Y axis of revolution. Y axis in part is part_y,
    # which maps to sketch_y. So centerline from sketch_y=-60 to +60 at sketch_x=0.
    sm.CreateCenterLine(0.0, -0.060, 0.0, 0.0, 0.060, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Groove"
    print(f"  sketch: {sk.Name!r}")

    print("\nStep 3: Pre-select sketch and call FeatureRevolve2(IsCut=True)")
    doc.ClearSelection2(True)
    ok = doc.SelectByID("SK_Groove", "SKETCH", 0, 0, 0)
    print(f"  sketch select: {ok}")

    angle_rad = 2.0 * math.pi
    args = (
        True,  # 1  SingleDir
        True,  # 2  IsSolid
        False,  # 3  IsThin
        True,  # 4  IsCut    <-- THE flag
        False,  # 5  ReverseDir
        False,  # 6  BothDirectionUpToSameEntity
        SW_END_COND_BLIND,  # 7  Dir1Type
        0,  # 8  Dir2Type
        angle_rad,  # 9  Dir1Angle
        0.0,  # 10 Dir2Angle
        False,
        False,
        0.0,
        0.0,  # 11-14 offsets (n/a)
        SW_THIN_WALL_ONE_DIRECTION,
        0.0,
        0.0,  # 15-17 thin (n/a)
        True,  # 18 Merge
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
    )
    cut = doc.FeatureManager.FeatureRevolve2(*args)
    print(f"  result: {cut!r}")
    if cut is not None:
        print(f"  Name: {cut.Name!r}, type: {cut.GetTypeName!r}")
        cut.Name = "REVCUT_Groove"

    print()
    bodies = doc.GetBodies2(0, True)
    if bodies and len(bodies) > 0:
        bb = bodies[0].GetBodyBox()
        gf = bodies[0].GetFaces
        faces = gf() if callable(gf) else gf
        n_faces = len(faces) if faces else 0
        print(
            f"final body bbox: "
            f"x=[{bb[0]*1000:+.2f},{bb[3]*1000:+.2f}] "
            f"y=[{bb[1]*1000:+.2f},{bb[4]*1000:+.2f}] "
            f"z=[{bb[2]*1000:+.2f},{bb[5]*1000:+.2f}] "
            f"faces={n_faces} (base was {base_face_count})"
        )
        if n_faces > base_face_count:
            print(f"\n>>> GREEN: face count increased by {n_faces - base_face_count}.")
            print(f"    revolve_cut works via FeatureRevolve2(IsCut=True).")
            print(f"    All ZG-ZN failures were the Right Plane mapping bug.")
        else:
            print(
                f"\n>>> Still RED: face count unchanged. Mapping wasn't the only issue."
            )


if __name__ == "__main__":
    main()
