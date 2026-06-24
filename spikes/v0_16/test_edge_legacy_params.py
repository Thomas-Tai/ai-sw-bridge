"""Test: InsertSheetMetalEdgeFlange with different parameter combinations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "v0_15"))

import pythoncom

pythoncom.CoInitialize()
try:
    from spike_earlybind_persist import connect_running_sw, ensure_sw_module
    from ai_sw_bridge.com.earlybind import typed_qi, typed_extension
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module() or ensure_sw_module()[0]
    sw = connect_running_sw()
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)

    # Build base flange
    doc.SelectByID("Front Plane", "PLANE", 0, 0, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(-0.03, -0.02, 0.0, 0.03, 0.02, 0.0)
    sk.InsertSketch(True)
    doc.EditRebuild3
    fm = doc.FeatureManager
    data = fm.CreateDefinition(34)
    bf = typed_qi(data, "IBaseFlangeFeatureData", module=mod)
    bf.Thickness = 0.002
    bf.BendRadius = 0.002
    doc.ClearSelection2(True)
    doc.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
    feat = fm.CreateFeature(data)
    doc.ForceRebuild3(False)
    print(f"base flange: {feat.Name}")

    # Get live edge
    bodies = doc.GetBodies2(0, True)
    edges_raw = bodies[0].GetEdges()
    ext = typed_extension(doc, module=mod)

    raw_edge = edges_raw[0]
    pid = ext.GetPersistReference3(raw_edge)
    result = ext.GetObjectByPersistReference3(pid)
    live_edge = result[0] if isinstance(result, tuple) else result
    print(f"Live edge type: {type(live_edge).__name__}")

    # Select the edge
    doc.ClearSelection2(True)
    sel_result = live_edge.Select2(False, 0)
    print(f"Selected: {sel_result}")

    # Test different parameter combinations
    tests = [
        ("5 params", (1.5708, False, False, 0.002, False)),
        ("6 params", (1.5708, False, False, 0.002, False, False)),
        ("7 params", (1.5708, False, False, 0.002, False, False, 0)),
        ("8 params v1", (1.5708, False, False, 0.002, False, False, 0, 0)),
        ("8 params v2", (1.5708, False, True, 0.002, False, False, 0, 0)),
    ]

    for name, params in tests:
        print("")
        print(f"=== {name} ===")
        try:
            feat2 = fm.InsertSheetMetalEdgeFlange(*params)
            if feat2:
                print(f"  SUCCESS: {feat2.Name}")
                break
            else:
                print(f"  Returned None")
        except Exception as ex:
            print(f"  FAILED: {type(ex).__name__}: {str(ex)[:80]}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
