"""Spike V2: enumerate the feature tree before and after sketch_circle_on_face('+x')."""
import pythoncom
import win32com.client

pythoncom.CoInitialize()
sw = win32com.client.Dispatch("SldWorks.Application")
template = sw.GetUserPreferenceStringValue(8)
doc = sw.NewDocument(template, 0, 0.0, 0.0)

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

print("=== after box build, top features (FBPR) ===")
for i in range(6):
    f = doc.FeatureByPositionReverse(i)
    if f is None:
        break
    print(f"  [{i}] name={f.Name!r} type={f.GetTypeName2!r}")

doc.ClearSelection2(True)
ok = doc.SelectByID("", "FACE", 0.015, 0.0, 0.010)
print(f"\nselect +x face: {ok}")
sm.InsertSketch(True)
sm.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)
sm.InsertSketch(True)
print("\n=== after +x face sketch close, top features (FBPR) ===")
for i in range(8):
    f = doc.FeatureByPositionReverse(i)
    if f is None:
        break
    print(f"  [{i}] name={f.Name!r} type={f.GetTypeName2!r}")

# Now try sketching on +z face for comparison
doc.ClearSelection2(True)
ok = doc.SelectByID("", "FACE", 0.0, 0.0, 0.020)
print(f"\nselect +z face: {ok}")
sm.InsertSketch(True)
sm.CreateCircle(0.0, 0.0, 0.0, 0.003, 0.0, 0.0)
sm.InsertSketch(True)
print("\n=== after +z face sketch close, top features (FBPR) ===")
for i in range(10):
    f = doc.FeatureByPositionReverse(i)
    if f is None:
        break
    print(f"  [{i}] name={f.Name!r} type={f.GetTypeName2!r}")
