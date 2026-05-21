"""Spike ZM: revolve-cut flag-grid on the now-correct selection state.

Spike ZL had textbook-correct selection (sketch mark=0 + RefAxis mark=16)
per CHM Remarks, and FeatureRevolve2(IsCut=True) still returned None.

Grid over UseFeatScope / UseAutoSelect / Merge to see if any combination
commits. Each variant rebuilds the selection state from scratch (since a
failed call may have side-effected the selection).
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


def create_ref_axis(doc, name):
    doc.ClearSelection2(True)
    doc.SelectByID("", "FACE", 0.0125, 0.040, 0.0)
    doc.InsertAxis2(True)
    ax = doc.FeatureByPositionReverse(0)
    ax.Name = name
    return ax


def setup_selection(doc, sketch_name, axis_feat):
    sel_mgr = doc.SelectionManager
    doc.ClearSelection2(True)
    doc.SelectByID(sketch_name, "SKETCH", 0, 0, 0)
    sel_mgr.SetSelectedObjectMark(1, 0, 0)
    axis_feat.Select2(True, 16)


def try_revolve(doc, *, use_feat_scope, use_auto_select, merge):
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
        merge,
        use_feat_scope,
        use_auto_select,
    )
    try:
        return doc.FeatureManager.FeatureRevolve2(*args)
    except Exception as e:
        print(f"      raised: {e!r}")
        return None


def main():
    pythoncom.CoInitialize()
    sw = win32com.client.Dispatch("SldWorks.Application")
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return

    print("Building base + ref axis...")
    base = build_base_cylinder(doc)
    ax = create_ref_axis(doc, "AX_Cyl")
    bodies = doc.GetBodies2(0, True)
    gf = bodies[0].GetFaces
    faces = gf() if callable(gf) else gf
    base_face_count = len(faces) if faces else 0
    print(f"  base faces: {base_face_count}\n")

    grid = []
    for ufs in (True, False):
        for uas in (True, False):
            for merge in (True, False):
                grid.append((ufs, uas, merge))

    for ufs, uas, merge in grid:
        sk_name = f"SK_{int(ufs)}{int(uas)}{int(merge)}"
        build_groove_sketch(doc, sk_name)
        setup_selection(doc, sk_name, ax)
        print(f"  UseFeatScope={ufs} UseAutoSelect={uas} Merge={merge}")
        f = try_revolve(doc, use_feat_scope=ufs, use_auto_select=uas, merge=merge)
        if f is None:
            print(f"    FAIL")
            try:
                doc.EditUndo2(1)
            except Exception:
                pass
        else:
            print(f"    PASS -- {f.Name!r}")
            bodies_now = doc.GetBodies2(0, True)
            gf = bodies_now[0].GetFaces
            faces = gf() if callable(gf) else gf
            print(f"    body faces now: {len(faces) if faces else 0}")
            f.Name = f"REVCUT_{sk_name}"
            # Stop on first GREEN -- we have our answer
            print(
                f"\n>>> GREEN with UseFeatScope={ufs} UseAutoSelect={uas} Merge={merge}"
            )
            return

    print("\nAll 8 flag combinations FAILED.")


if __name__ == "__main__":
    main()
