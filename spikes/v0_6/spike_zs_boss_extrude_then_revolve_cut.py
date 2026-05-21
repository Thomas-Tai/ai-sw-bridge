"""Spike ZS: boss-extrude cylinder + revolve_cut groove on different planes.

Spike ZR confirmed that two revolves on the same plane (Front Plane boss +
Front Plane cut) silently fails the cut. The successful pattern (Spike ZQ)
uses different planes.

This spike validates a SIMPLER and SHIPPABLE example pattern:
  - Base cylinder via boss_extrude_blind from a Top-Plane circle
    -> cylinder along +Y axis, no revolve needed
  - Groove via revolve_cut on Front Plane (which contains the Y axis)
    -> sketch_x = part_x, sketch_y = part_y (trivial mapping)

Geometry:
  Base: Top-Plane circle, R=12.5mm at origin, extruded +Y 80mm.
        Result: cylinder along Y axis, span y=[0, 80], r=12.5.

  Cut:  Front-Plane rectangle. Want to cut a 5mm-axial x 1mm-radial groove
        at axial midpoint y=40, radial r=11.5..12.5.
        Front Plane is XY -> sketch_x=part_x, sketch_y=part_y.
        Groove profile in part-frame is: x in [11.5, 12.5] (radial),
        y in [37.5, 42.5] (axial). So sketch rect from (11.5, 37.5) to
        (12.5, 42.5). Centerline along Y at x=0, from y=-60 to y=140.
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
        return

    sm = doc.SketchManager
    fm = doc.FeatureManager

    # ----- Base cylinder via boss_extrude_blind -----
    doc.SelectByID("Top Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.0125, 0.0, 0.0)
    sm.InsertSketch(True)
    sk_base = doc.FeatureByPositionReverse(0)
    sk_base.Name = "SK_Base"

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
    bodies = doc.GetBodies2(0, True)
    bb = bodies[0].GetBodyBox()
    print(
        f"BASE bbox: "
        f"x=[{bb[0]*1000:+.2f},{bb[3]*1000:+.2f}] "
        f"y=[{bb[1]*1000:+.2f},{bb[4]*1000:+.2f}] "
        f"z=[{bb[2]*1000:+.2f},{bb[5]*1000:+.2f}]"
    )
    gf = bodies[0].GetFaces
    fcs = gf() if callable(gf) else gf
    print(f"BASE face count: {len(fcs) if fcs else 0}")

    # ----- Groove sketch on FRONT Plane with NEGATIVE x rect side -----
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    # Front Plane mapping (trivial): sketch_x=part_x, sketch_y=part_y.
    # Try sketch_x NEGATIVE side: x in [-12.5, -11.5], y in [37.5, 42.5]
    # Maybe Front Plane requires profile on the -x side (mirror of Right
    # Plane's effective -x side) for some unknown reason.
    sm.CreateCornerRectangle(-0.0125, 0.0375, 0.0, -0.0115, 0.0425, 0.0)
    sm.CreateCenterLine(0.0, -0.060, 0.0, 0.0, 0.060, 0.0)
    sm.InsertSketch(True)
    sk_groove = doc.FeatureByPositionReverse(0)
    sk_groove.Name = "SK_Groove"

    doc.ClearSelection2(True)
    doc.SelectByID("SK_Groove", "SKETCH", 0, 0, 0)
    angle_rad = 2.0 * math.pi
    cut_args = (
        True,
        True,
        False,
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        angle_rad,
        0.0,
        False,
        False,
        0.0,
        0.0,
        SW_THIN_WALL_ONE_DIRECTION,
        0.0,
        0.0,
        True,
        True,
        True,
    )
    cut = fm.FeatureRevolve2(*cut_args)
    print(f"CUT result: {cut!r}")
    if cut is None:
        print(">>> CUT FAILED")
    else:
        cut.Name = "REVCUT_Groove"
        bodies = doc.GetBodies2(0, True)
        bb = bodies[0].GetBodyBox()
        print(
            f"AFTER CUT bbox: "
            f"x=[{bb[0]*1000:+.2f},{bb[3]*1000:+.2f}] "
            f"y=[{bb[1]*1000:+.2f},{bb[4]*1000:+.2f}] "
            f"z=[{bb[2]*1000:+.2f},{bb[5]*1000:+.2f}]"
        )
        gf = bodies[0].GetFaces
        fcs = gf() if callable(gf) else gf
        print(f"AFTER CUT face count: {len(fcs) if fcs else 0}")
        print(">>> CUT SUCCEEDED.")


if __name__ == "__main__":
    main()
