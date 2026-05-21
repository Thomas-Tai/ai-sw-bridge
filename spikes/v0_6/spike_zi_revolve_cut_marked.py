"""Spike ZI: revolve-cut with explicit marked-selection per CHM Remarks.

Spike ZG/ZH established that FeatureRevolve2(IsCut=True) returns None silently
on every profile/AutoSelect variant when only the sketch is pre-selected.

The CHM Remarks for FeatureRevolve2 require:
  - sketch to revolve, using Mark = 0
  - axis of revolution, using Mark = 4 or 16

Spike X (boss case) succeeded with only the sketch pre-selected because SW
auto-detected the embedded centerline in an otherwise-empty doc. For cuts on
existing bodies, SW apparently cannot auto-disambiguate and we must mark
the axis explicitly.

Challenge: our axis is an embedded sketch centerline (ISketchSegment), not
a top-level reference axis (IRefAxis). SelectByID("", "SKETCHSEGMENT",
midpoint) from outside the sketch was tried in Spike ZH-V3 and returned
False. This spike uses the IFeature -> ISketch -> GetSketchSegments path
to get the centerline object directly and Select2 it.

Same selection idiom already shipped for pattern/mirror handlers in
builder.py:_mark_first_selection (Callout OUT-param fails, so we use
5-arg SelectByID + SelectionMgr.SetSelectedObjectMark, or call .Select2
on an IFeature/IEntity directly without Callout).

Variants tried, in order:
  W1: sketch_segments[i].Select4(append=False, callout=None) for centerline
      with mark via Select4's mark param -- but Select4 takes Append+Callout
      not (Append, Mark). Wrong API. Try IEntity.Select2(append, mark).
      Actually ISketchSegment inherits from IEntity, so Select2 works.

  W1 (real): get centerline from SK_Cut via GetSketchSegments; identify
      construction (centerline) via .ConstructionGeometry==True;
      centerline.Select2(append=False, mark=4); then SelectByID(SK_Cut,
      'SKETCH', mark via SetSelectedObjectMark... no wait, sketch needs
      to also be in selection set with mark=0).

      Simpler: select sketch first (mark 0 via SelectByID then
      SetSelectedObjectMark(1, 0, 0)), then centerline appended with mark 4.

  W2: same as W1 but with UseAutoSelect=False (we explicitly scope the body).

Run from venv-freshtest. Standalone. Tries variants on the same base cylinder.
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
    """Right-plane groove: rect (37.5..42.5, 11.5..12.5) + y-axis centerline."""
    sm = doc.SketchManager
    doc.ClearSelection2(True)
    doc.SelectByID("Right Plane", "PLANE", 0, 0, 0)
    sm.InsertSketch(True)
    sm.CreateCornerRectangle(0.0375, 0.0115, 0.0, 0.0425, 0.0125, 0.0)
    sm.CreateCenterLine(-0.060, 0.0, 0.0, 0.060, 0.0, 0.0)
    sm.InsertSketch(True)
    sk = doc.FeatureByPositionReverse(0)
    sk.Name = sketch_name
    return sk


def get_centerline_from_sketch(sketch_feature):
    """Walk ISketch.GetSketchSegments to find the construction line.

    sketch_feature is the IFeature; GetSpecificFeature2 returns the ISketch.
    """
    ske = sketch_feature.GetSpecificFeature2
    if ske is None:
        return None, "GetSpecificFeature2 returned None"
    segs = ske.GetSketchSegments
    if segs is None:
        return None, "GetSketchSegments returned None"
    print(f"    sketch has {len(segs)} segments")
    for i, seg in enumerate(segs):
        try:
            is_construction = seg.ConstructionGeometry
        except Exception as e:
            is_construction = f"ERR({e!r})"
        try:
            seg_type = seg.GetType  # int per swSketchSegments_e
        except Exception:
            seg_type = "?"
        print(f"      seg[{i}]: type={seg_type}, construction={is_construction}")
        if is_construction is True:
            return seg, None
    return None, "no segment with ConstructionGeometry=True found"


def try_revolve_cut(doc, sketch_name, mark_sketch_first, use_auto_select):
    """Mark selection and call FeatureRevolve2 with IsCut=True.

    mark_sketch_first: if True, select sketch (mark 0) then centerline (mark 4).
                       if False, select centerline (mark 4) then sketch (mark 0).
    """
    fm = doc.FeatureManager
    sel_mgr = doc.SelectionManager
    doc.ClearSelection2(True)

    # Find the sketch IFeature first.
    # We renamed it; walk back from FeatureByPositionReverse(0) since we
    # just made it the latest feature.
    sketch_feat = None
    for i in range(20):  # bounded walk
        f = doc.FeatureByPositionReverse(i)
        if f is None:
            break
        if f.Name == sketch_name:
            sketch_feat = f
            break
    if sketch_feat is None:
        print(f"    could not find sketch '{sketch_name}' in feature tree")
        return None

    centerline, err = get_centerline_from_sketch(sketch_feat)
    if centerline is None:
        print(f"    centerline lookup failed: {err}")
        return None
    print(f"    centerline object: {centerline!r}")

    if mark_sketch_first:
        # 1. Sketch with mark=0
        ok = doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
        if not ok:
            print(f"    sketch select FAIL")
            return None
        if not sel_mgr.SetSelectedObjectMark(1, 0, 0):
            print(f"    sketch mark set FAIL")
        # 2. Centerline appended with mark=4
        ok = centerline.Select2(True, 4)
        print(f"    centerline.Select2(True, 4) -> {ok}")
    else:
        # 1. Centerline with mark=4 (non-append)
        ok = centerline.Select2(False, 4)
        print(f"    centerline.Select2(False, 4) -> {ok}")
        # 2. Sketch appended... but SelectByID is non-appending in 5-arg form
        ok = doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
        # That just cleared and selected the sketch; centerline is lost.
        # Re-append centerline:
        centerline.Select2(True, 4)
        sel_mgr.SetSelectedObjectMark(2, 0, 0)  # mark sketch (now at idx 2)

    # Sanity: print current selection set
    n = sel_mgr.GetSelectedObjectCount2(-1)
    print(f"    selection count: {n}")
    for i in range(1, n + 1):
        try:
            t = sel_mgr.GetSelectedObjectType3(i, -1)
            m = sel_mgr.GetSelectedObjectMark(i)
            print(f"      sel[{i}]: type={t}, mark={m}")
        except Exception as e:
            print(f"      sel[{i}]: introspect ERR {e!r}")

    angle_rad = 2.0 * math.pi
    args = (
        True,  # SingleDir
        True,  # IsSolid
        False,  # IsThin
        True,  # IsCut
        False,  # ReverseDir
        False,  # BothDirectionUpToSameEntity
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
        use_auto_select,
    )
    try:
        f = fm.FeatureRevolve2(*args)
        return f
    except Exception as e:
        print(f"    FeatureRevolve2 raised: {e!r}")
        return None


def report(label, feat):
    if feat is None:
        print(f"  {label}: FAIL (None)")
        return False
    print(f"  {label}: PASS -- {feat.Name!r}")
    return True


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        print("! NewDocument returned None")
        return

    print("Building base cylinder Ø25 x 80mm along Y axis...")
    base = build_base_cylinder(doc)
    print(f"  base: {base.Name!r}\n")

    results = {}

    print("W1: sketch first (mark=0), centerline appended (mark=4), AutoSelect=True")
    build_groove_sketch(doc, "SK_W1")
    f = try_revolve_cut(doc, "SK_W1", mark_sketch_first=True, use_auto_select=True)
    results["W1_sketch_first_AS"] = report("W1", f)
    if f is None:
        try:
            doc.EditUndo2(1)
        except Exception:
            pass
    if f is not None:
        f.Name = "REVCUT_W1"
    print()

    print("W2: sketch first, AutoSelect=False")
    build_groove_sketch(doc, "SK_W2")
    f = try_revolve_cut(doc, "SK_W2", mark_sketch_first=True, use_auto_select=False)
    results["W2_sketch_first_noAS"] = report("W2", f)
    if f is None:
        try:
            doc.EditUndo2(1)
        except Exception:
            pass
    if f is not None:
        f.Name = "REVCUT_W2"
    print()

    print("=== Summary ===")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")

    print()
    bodies = doc.GetBodies2(0, True)
    if bodies and len(bodies) > 0:
        bb = bodies[0].GetBodyBox()
        faces = bodies[0].GetFaces()
        n_faces = len(faces) if faces else 0
        print(
            f"final body bbox (mm): "
            f"x=[{bb[0]*1000:.2f},{bb[3]*1000:.2f}] "
            f"y=[{bb[1]*1000:.2f},{bb[4]*1000:.2f}] "
            f"z=[{bb[2]*1000:.2f},{bb[5]*1000:.2f}] "
            f"faces={n_faces}"
        )


if __name__ == "__main__":
    main()
