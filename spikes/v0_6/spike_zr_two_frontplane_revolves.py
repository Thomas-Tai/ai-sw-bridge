"""Spike ZR: two revolves on Front Plane (boss then cut) -- mirror of grooved_shaft example.

The grooved_shaft example failed at the revolve_cut step with the
'returned None' error, despite the geometry analysis suggesting the cut
profile sits inside the cylinder body radial-wise. This spike replicates
the example geometry directly to reproduce / isolate the failure.

Geometry (matching examples/grooved_shaft/spec.json):
  Boss profile: Front Plane rect, sketch corners (0, 0) to (80, 12.5),
                centerline (-60, 0) to (140, 0). Revolve 360 about
                x-axis. Expected result: solid cylinder along x from
                0 to 80, radius 12.5.
  Cut profile:  Front Plane rect, sketch corners (37.5, 11.5) to
                (42.5, 12.5), same centerline. Revolve-cut 360.
                Expected: 1mm-deep groove at x=[37.5, 42.5].

Hypothesis 1: the cut succeeds -- failure is in handler code, not geometry.
Hypothesis 2: two revolves on same plane fails for state reasons.
Hypothesis 3: cut profile straddling y=0 isn't the issue here (profile
              is y=11.5..12.5, well above centerline at y=0). Confirmed
              ok by inspection.
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

    # ----- Boss sketch on Front Plane -----
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    # CenterRectangle at (40, 6.25) with half-width 40, half-height 6.25
    # -> corners (0, 0) to (80, 12.5)
    sm.CreateCenterRectangle(0.040, 0.00625, 0.0, 0.080, 0.0125, 0.0)
    sm.CreateCenterLine(-0.060, 0.0, 0.0, 0.140, 0.0, 0.0)
    sm.InsertSketch(True)
    sk_body = doc.FeatureByPositionReverse(0)
    sk_body.Name = "SK_Body"

    doc.ClearSelection2(True)
    doc.SelectByID("SK_Body", "SKETCH", 0, 0, 0)
    angle_rad = 2.0 * math.pi
    boss_args = (
        True,
        True,
        False,
        False,
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
    boss = fm.FeatureRevolve2(*boss_args)
    if boss is None:
        print("! BOSS revolve returned None")
        return
    boss.Name = "REV_Body"
    bodies = doc.GetBodies2(0, True)
    bb = bodies[0].GetBodyBox()
    print(
        f"BOSS body bbox: "
        f"x=[{bb[0]*1000:+.2f},{bb[3]*1000:+.2f}] "
        f"y=[{bb[1]*1000:+.2f},{bb[4]*1000:+.2f}] "
        f"z=[{bb[2]*1000:+.2f},{bb[5]*1000:+.2f}]"
    )
    gf = bodies[0].GetFaces
    fcs = gf() if callable(gf) else gf
    print(f"BOSS face count: {len(fcs) if fcs else 0}")

    # ----- Groove sketch on Front Plane -----
    doc.ClearSelection2(True)
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    # CenterRectangle at (40, 12) with half-width 2.5, half-height 0.5
    # -> corners (37.5, 11.5) to (42.5, 12.5)
    sm.CreateCenterRectangle(0.040, 0.012, 0.0, 0.0425, 0.0125, 0.0)
    sm.CreateCenterLine(-0.060, 0.0, 0.0, 0.140, 0.0, 0.0)
    sm.InsertSketch(True)
    sk_groove = doc.FeatureByPositionReverse(0)
    sk_groove.Name = "SK_Groove"

    doc.ClearSelection2(True)
    doc.SelectByID("SK_Groove", "SKETCH", 0, 0, 0)
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
        print(">>> CUT FAILED. Hypothesis 2 (two-revolves-on-same-plane) likely.")
    else:
        cut.Name = "REVCUT_Groove"
        bodies = doc.GetBodies2(0, True)
        gf = bodies[0].GetFaces
        fcs = gf() if callable(gf) else gf
        print(f"AFTER CUT face count: {len(fcs) if fcs else 0}")
        print(">>> CUT SUCCEEDED. Failure must be in handler code path.")


if __name__ == "__main__":
    main()
