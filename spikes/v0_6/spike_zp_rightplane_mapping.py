"""Spike ZP: empirically test Right Plane sketch-to-part coordinate mapping.

Per professional review, the silent-None failures across spikes ZG-ZN may
have a single root cause: the rectangle on Right Plane was floating in
empty space because we got the sketch-local-to-part mapping wrong.

This spike builds 4 separate Right-Plane sketches, each with a single
small horizontal LINE at known sketch-local coords. By reading back the
sketch's part-frame extent (via GetSketchExtent or by extruding it
0.01mm and reading the bbox), we can deduce the mapping unambiguously.

Strategy:
  Make ONE sketch with one small distinguishing line per quadrant:
    Line A: from (0.04, 0.02, 0) to (0.045, 0.02, 0) in sketch-local m
      (5mm long, at sketch coords (40..45, 20))
  Then extrude the closed contour... no, single line won't extrude.

Better: do 4 different recognizable sketch-local placements and
extrude each. Read each extrude's body bbox. The bbox tells us which
part axes the sketch axes mapped to.

Even simpler: use IGetSketchBlockInstancePosition or read the
SketchManager.AddToDB then ASketch's Transform.

Simplest of all: just put the rectangle exactly where Spike ZG put it
(0.0375..0.0425, 0.0115..0.0125) and **extrude it 0.001mm** (1um sliver,
basically invisible) and read the slug's bbox. The slug's part-frame
bbox is the ground truth of where the rectangle lives.
"""

import pythoncom
import win32com.client

SW_END_COND_BLIND = 0


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return

    sm = doc.SketchManager
    fm = doc.FeatureManager

    # Build the same rectangle that all prior spikes used, on Right Plane.
    print("Building Right Plane sketch with rectangle at sketch-local")
    print("  (0.0375, 0.0115) -> (0.0425, 0.0125) m  (= 37.5..42.5, 11.5..12.5 mm)")
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(0.0375, 0.0115, 0.0, 0.0425, 0.0125, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = "SK_Probe"
    print(f"  sketch: {sk.Name!r}")

    # Extrude the rectangle 1mm to make a small slug. Read its bbox.
    # That bbox tells us where the rectangle actually lives in part frame.
    doc.ClearSelection2(True)
    doc.SelectByID("SK_Probe", "SKETCH", 0, 0, 0)
    slug = fm.FeatureExtrusion2(
        True,
        False,
        False,
        SW_END_COND_BLIND,
        0,
        0.001,
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
    if slug is None:
        print("! could not extrude slug")
        return
    slug.Name = "EX_Probe"

    bodies = doc.GetBodies2(0, True)
    if bodies and len(bodies) > 0:
        bb = bodies[0].GetBodyBox()
        print()
        print(f"Slug bbox (mm):")
        print(
            f"  x=[{bb[0]*1000:+.2f}, {bb[3]*1000:+.2f}] "
            f"y=[{bb[1]*1000:+.2f}, {bb[4]*1000:+.2f}] "
            f"z=[{bb[2]*1000:+.2f}, {bb[5]*1000:+.2f}]"
        )
        print()
        print("Interpretation:")
        print("  My assumption was sketch_x=part_y, sketch_y=part_z, so")
        print("  rect at sketch-local (37.5..42.5, 11.5..12.5) should land at")
        print("    part y=[37.5,42.5], z=[11.5,12.5]")
        print("    plus 1mm extrusion in +part_x (Right Plane normal = +X)")
        print("  Expected bbox: x=[0,1], y=[37.5,42.5], z=[11.5,12.5]")
        print()
        x_match = abs(bb[0]) < 0.0005 and abs(bb[3] - 0.001) < 0.0005
        y_match = abs(bb[1] - 0.0375) < 0.0005 and abs(bb[4] - 0.0425) < 0.0005
        z_match = abs(bb[2] - 0.0115) < 0.0005 and abs(bb[5] - 0.0125) < 0.0005
        if x_match and y_match and z_match:
            print(
                "  >>> MAPPING CORRECT. The (sketch_x=y, sketch_y=z) assumption holds."
            )
            print("      Silent-None must have a different root cause.")
        else:
            print("  >>> MAPPING WRONG. The rectangle is NOT where I thought.")
            print("      Compute the actual mapping from the printed bbox above:")
            xs = (bb[0] * 1000, bb[3] * 1000)
            ys = (bb[1] * 1000, bb[4] * 1000)
            zs = (bb[2] * 1000, bb[5] * 1000)
            for axis_name, ext in (("x", xs), ("y", ys), ("z", zs)):
                if abs(ext[0]) < 0.5 and abs(ext[1] - 1) < 0.5:
                    print(f"      Right Plane normal axis = part_{axis_name}")
                elif abs(ext[0] - 37.5) < 0.5 and abs(ext[1] - 42.5) < 0.5:
                    print(f"      sketch_x mapped to part_{axis_name}")
                elif abs(ext[0] - 11.5) < 0.5 and abs(ext[1] - 12.5) < 0.5:
                    print(f"      sketch_y mapped to part_{axis_name}")


if __name__ == "__main__":
    main()
