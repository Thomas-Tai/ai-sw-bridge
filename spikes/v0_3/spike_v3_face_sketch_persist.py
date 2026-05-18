"""Spike V3: deeper look at side-face sketch persistence.

Try several patterns to see what makes a side-face sketch actually appear
as a top-level feature so SelectByID can find it.

Patterns:
  A. InsertSketch / CreateCircle / InsertSketch  (current)
  B. (A) + doc.EditRebuild3
  C. (A) + doc.ClearSelection2(True) before close
  D. Use SelectByID with the face's IFace2 entity instead of by-coord
  E. (A) + read FBPR(0..N) IMMEDIATELY (no other ops)
"""
import pythoncom
import win32com.client

pythoncom.CoInitialize()
sw = win32com.client.Dispatch("SldWorks.Application")
template = sw.GetUserPreferenceStringValue(8)


def make_box(doc):
    doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCenterRectangle(0.0, 0.0, 0.0, 0.015, 0.015, 0.0)
    sm.InsertSketch(True)
    fm = doc.FeatureManager
    fm.FeatureExtrusion2(
        True, False, False, 0, 0, 0.020, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        True, True, True, 0, 0.0, False,
    )


def enum_feats(doc, label):
    print(f"  features {label}:")
    for i in range(12):
        f = doc.FeatureByPositionReverse(i)
        if f is None:
            break
        print(f"    [{i}] name={f.Name!r} type={f.GetTypeName2!r}")


def case_a(doc):
    print("\n--- Case A: plain InsertSketch / Create / InsertSketch ---")
    make_box(doc)
    enum_feats(doc, "after box")
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "FACE", 0.015, 0.0, 0.010)
    print(f"  +x face select: {ok}")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)
    sm.InsertSketch(True)
    enum_feats(doc, "after sketch close")
    # Try SelectByID by name
    doc.ClearSelection2(True)
    ok = doc.SelectByID("Sketch2", "SKETCH", 0.0, 0.0, 0.0)
    print(f"  SelectByID('Sketch2', 'SKETCH', ...) -> {ok}")


def case_b(doc):
    print("\n--- Case B: plain InsertSketch / Create / InsertSketch + EditRebuild ---")
    make_box(doc)
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "FACE", 0.015, 0.0, 0.010)
    print(f"  +x face select: {ok}")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)
    sm.InsertSketch(True)
    doc.EditRebuild3  # property auto-invokes
    enum_feats(doc, "after rebuild")
    doc.ClearSelection2(True)
    ok = doc.SelectByID("Sketch2", "SKETCH", 0.0, 0.0, 0.0)
    print(f"  SelectByID('Sketch2', 'SKETCH', ...) -> {ok}")


def case_c_compare_z(doc):
    """As a control: do the +z face version and check FBPR."""
    print("\n--- Case C control: +z face sketch (known-working) ---")
    make_box(doc)
    doc.ClearSelection2(True)
    ok = doc.SelectByID("", "FACE", 0.0, 0.0, 0.020)
    print(f"  +z face select: {ok}")
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)
    sm.InsertSketch(True)
    enum_feats(doc, "after +z sketch close")
    doc.ClearSelection2(True)
    ok = doc.SelectByID("Sketch2", "SKETCH", 0.0, 0.0, 0.0)
    print(f"  SelectByID('Sketch2', 'SKETCH', ...) -> {ok}")


def main():
    for case in (case_a, case_b, case_c_compare_z):
        doc = sw.NewDocument(template, 0, 0.0, 0.0)
        try:
            case(doc)
        finally:
            try:
                sw.CloseDoc(doc.GetTitle)
            except Exception:
                pass


if __name__ == "__main__":
    main()
