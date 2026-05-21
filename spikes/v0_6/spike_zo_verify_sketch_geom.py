"""Spike ZO: programmatically verify where the groove sketch's rectangle lands.

Hypothesis (per professional review): all 8 prior spikes returned None
because the rectangle on Right Plane was floating in empty space, missing
the cylinder. FeatureRevolve2 silently returns None when the cut doesn't
intersect the body.

This spike:
  1. Builds the same Ø25 x 80mm cylinder along Y axis (Top-plane circle).
  2. Builds the same groove sketch on Right Plane (rect + centerline).
  3. Reads back the rectangle vertices' WORLD coordinates via
     ISketchSegment.GetStartPoint2/GetEndPoint2 (which return part-frame
     coordinates, not sketch-local).
  4. Reads back the cylinder body bbox.
  5. Computes whether the rectangle's 4 corners land in/near/far from the
     cylinder material.

If the rectangle is in the wrong place, we'll see it in the printed
coords -- no need to open SW UI manually.

Expected if my (sketch_x=part_y, sketch_y=part_z) assumption was RIGHT:
  Rectangle corners at part-frame approx:
    (0, 37.5, 11.5), (0, 42.5, 11.5), (0, 42.5, 12.5), (0, 37.5, 12.5)
  Cylinder bbox: y=[0,80], radial radius 12.5.
  Rectangle sits on the +Z surface of cylinder at y=37.5..42.5. Good.

Expected if the mapping is WRONG (e.g. SW puts sketch_y along part_y not _z):
  Rectangle corners at, say:
    (0, 11.5, 37.5), (0, 12.5, 37.5), ...
  These are at z=37.5..42.5, far from cylinder surface (which is at
  radial dist 12.5). The cut would float in empty space at z=37.5+ --
  exactly the failure mode.
"""

import pythoncom
import win32com.client

SW_END_COND_BLIND = 0


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


def build_groove_sketch_rightplane(doc, sketch_name):
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    # Corner rect: same call as in all prior spikes
    sm.CreateCornerRectangle(0.0375, 0.0115, 0.0, 0.0425, 0.0125, 0.0)
    sm.CreateCenterLine(-0.060, 0.0, 0.0, 0.060, 0.0, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = sketch_name
    return sk


def get_sketch_obj(doc, sketch_name):
    for i in range(20):
        f = doc.FeatureByPositionReverse(i)
        if f is None:
            break
        if f.Name == sketch_name:
            return f.GetSpecificFeature2
    return None


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return

    print("Building base cylinder Ø25 x 80mm along Y axis...")
    build_base_cylinder(doc)
    bodies = doc.GetBodies2(0, True)
    if bodies and len(bodies) > 0:
        bb = bodies[0].GetBodyBox()
        print(
            f"  cylinder bbox (mm): "
            f"x=[{bb[0]*1000:.2f},{bb[3]*1000:.2f}] "
            f"y=[{bb[1]*1000:.2f},{bb[4]*1000:.2f}] "
            f"z=[{bb[2]*1000:.2f},{bb[5]*1000:.2f}]"
        )
        print("  expected:           x=[-12.50,12.50] y=[0.00,80.00] z=[-12.50,12.50]")

    print("\nBuilding groove sketch on Right Plane...")
    build_groove_sketch_rightplane(doc, "SK_Cut")

    ske = get_sketch_obj(doc, "SK_Cut")
    if ske is None:
        print("! could not get ISketch for SK_Cut")
        return

    segs = ske.GetSketchSegments
    print(f"\nSK_Cut has {len(segs)} segments")
    print(
        "Reading each segment's WORLD-frame endpoints via GetStartPoint2/GetEndPoint2:"
    )
    print("(These return part-frame mm coords, not sketch-local.)\n")

    # ISketchSegment.GetType returns swSketchSegments_e:
    #   swSketchLINE = 0, swSketchARC = 1, swSketchELLIPSE = 2,
    #   swSketchSPLINE = 3, swSketchPARABOLA = 4, swSketchTEXT = 5
    # All four rect edges + the centerline should be LINE (type 0).
    # ISketchLine has IStartPoint and IEndPoint -> ISketchPoint with X/Y/Z (meters).
    for i, seg in enumerate(segs):
        try:
            is_cl = seg.ConstructionGeometry
        except Exception:
            is_cl = "?"
        try:
            seg_type = seg.GetType
        except Exception:
            seg_type = "?"

        def read_pt(line, accessor_name):
            try:
                pt = getattr(line, accessor_name)
                if callable(pt):
                    pt = pt()
                if pt is None:
                    return "None"
                return f"({pt.X*1000:+.2f}, {pt.Y*1000:+.2f}, {pt.Z*1000:+.2f}) mm"
            except Exception as e:
                return f"ERR({e!r})"

        label = "CENTERLINE" if is_cl is True else "rect-edge"
        # Try IStartPoint/IEndPoint (ISketchLine canonical pre-2019)
        start_s = read_pt(seg, "IStartPoint")
        end_s = read_pt(seg, "IEndPoint")
        # Fallback: StartPoint/EndPoint properties (some versions)
        if start_s.startswith("ERR") or start_s == "None":
            start_s = read_pt(seg, "StartPoint")
        if end_s.startswith("ERR") or end_s == "None":
            end_s = read_pt(seg, "EndPoint")
        print(f"  seg[{i}] ({label}, type={seg_type}):")
        print(f"    start = {start_s}")
        print(f"    end   = {end_s}")

    print("\nDiagnostic interpretation:")
    print("  If rect-edge endpoints have part-y in [37.5, 42.5] and")
    print("  part-z in [11.5, 12.5], the (sketch_x=y, sketch_y=z) mapping")
    print("  was correct -- rectangle sits on cylinder surface at y=mid.")
    print("  If rect-edge endpoints have part-z in [37.5, 42.5] instead,")
    print("  the mapping was WRONG -- rectangle floats out at z=37+, far")
    print("  from cylinder (radial radius 12.5). That's the silent-None cause.")


if __name__ == "__main__":
    main()
