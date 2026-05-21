"""Spike ZL: revolve-cut with InsertAxis2 + proper append-selection.

Spike ZK X2 created a real IRefAxis but lost the sketch from selection
because SelectByID(name,type,...) is non-appending. Fix: select sketch
first (then mark via SetSelectedObjectMark), then append axis via
IFeature.Select2(True, 16) -- the same pattern used by _build_linear_pattern
in builder.py.

If THIS works: revolve_cut handler builds a transient IRefAxis from a
spec'd reference (face / two planes / sketch line), then does the
marked selection. Centerline embedded in profile sketch is NOT the
v1 axis path for cuts.
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


def build_groove_sketch(doc, sketch_name):
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(0.0375, 0.0115, 0.0, 0.0425, 0.0125, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = sketch_name
    return sk


def describe_selection(doc, label):
    sm = doc.SelectionManager
    n = sm.GetSelectedObjectCount2(-1)
    print(f"    {label} selection count: {n}")
    for i in range(1, n + 1):
        try:
            t = sm.GetSelectedObjectType3(i, -1)
            m = sm.GetSelectedObjectMark(i)
            print(f"      sel[{i}]: type={t}, mark={m}")
        except Exception as e:
            print(f"      sel[{i}]: introspect ERR {e!r}")


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return

    print("Building base cylinder Ø25 x 80mm along Y axis...")
    base = build_base_cylinder(doc)
    bodies = doc.GetBodies2(0, True)
    base_face_count = 0
    if bodies:
        gf = bodies[0].GetFaces
        faces = gf() if callable(gf) else gf
        base_face_count = len(faces) if faces else 0
    print(f"  base: {base.Name!r}, faces={base_face_count}\n")

    # Create reference axis from cyl face
    print("Creating ref axis from cyl face...")
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "FACE", 0.0125, 0.040, 0.0)
    print(f"  cyl-face select: {ok}")
    axis_ok = doc.InsertAxis2(True)
    print(f"  InsertAxis2(True) -> {axis_ok}")
    axis_feat = doc.FeatureByPositionReverse(0)
    axis_feat.Name = "AX_Cyl"
    print(f"  axis: {axis_feat.Name!r}, type={axis_feat.GetTypeName!r}\n")

    # Build groove sketch (no centerline)
    print("Building groove sketch (no embedded centerline)...")
    build_groove_sketch(doc, "SK_Cut")
    print()

    # ===== Selection: sketch mark=0, then axis APPENDED via IFeature.Select2 =====
    sel_mgr = doc.SelectionManager
    print("Building selection set: sketch (mark=0) + axis appended (mark=16)")
    doc.ClearSelection2(True)
    ok = doc.SelectByID("SK_Cut", "SKETCH", 0, 0, 0)
    print(f"  sketch select: {ok}")
    sel_mgr.SetSelectedObjectMark(1, 0, 0)
    # Append axis via IFeature.Select2 -- no Callout, no clobber
    ok_a = axis_feat.Select2(True, 16)
    print(f"  axis.Select2(True, 16): {ok_a}")
    describe_selection(doc, "pre-call")

    # Call FeatureRevolve2 with IsCut=True
    angle_rad = 2.0 * math.pi
    args = (
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
    print("\nCalling FeatureRevolve2(IsCut=True)...")
    try:
        f = doc.FeatureManager.FeatureRevolve2(*args)
        print(f"  result: {f!r}")
        if f is not None:
            print(f"  Name: {f.Name!r}, type: {f.GetTypeName!r}")
            f.Name = "REVCUT_Groove"
    except Exception as e:
        print(f"  raised: {e!r}")
        f = None

    print()
    bodies = doc.GetBodies2(0, True)
    if bodies and len(bodies) > 0:
        bb = bodies[0].GetBodyBox()
        faces_now = bodies[0].GetFaces()
        n_faces = len(faces_now) if faces_now else 0
        print(
            f"final body bbox: "
            f"x=[{bb[0]*1000:.2f},{bb[3]*1000:.2f}] "
            f"y=[{bb[1]*1000:.2f},{bb[4]*1000:.2f}] "
            f"z=[{bb[2]*1000:.2f},{bb[5]*1000:.2f}] "
            f"faces={n_faces} (base was {base_face_count})"
        )
        if n_faces > base_face_count:
            print(
                f"  >>> GREEN: face count increased by {n_faces - base_face_count} <<<"
            )
        else:
            print(f"  RED: face count unchanged")


if __name__ == "__main__":
    main()
