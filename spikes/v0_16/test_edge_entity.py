"""Diagnostic: try IEntity and SelectByID2 for edges."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "v0_15"))

import pythoncom

pythoncom.CoInitialize()
try:
    from spike_earlybind_persist import connect_running_sw, ensure_sw_module
    from ai_sw_bridge.com.earlybind import typed, typed_qi, typed_extension
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

    # Get edges - both raw and typed
    bodies = doc.GetBodies2(0, True)
    edges_raw = bodies[0].GetEdges()
    ext = typed_extension(doc, module=mod)

    raw_edge = edges_raw[0]

    # Get live edge via persist
    pid = ext.GetPersistReference3(raw_edge)
    result = ext.GetObjectByPersistReference3(pid)
    live_edge = result[0] if isinstance(result, tuple) else result

    print(f"Raw edge type: {type(raw_edge).__name__}")
    print(f"Live edge type: {type(live_edge).__name__}")

    # Check if live_edge has Select methods
    print("\n=== Live edge methods ===")
    select_methods = [m for m in dir(live_edge) if "select" in m.lower()]
    print(f"Selection-related: {select_methods}")

    # Try QI to IEntity
    print("\n=== QI to IEntity ===")
    try:
        entity = typed_qi(live_edge, "IEntity", module=mod)
        print(f"IEntity: {type(entity).__name__}")

        # Check IEntity methods
        entity_methods = [m for m in dir(entity) if "select" in m.lower()]
        print(f"IEntity selection methods: {entity_methods}")

        # Try Select4 on IEntity
        if hasattr(entity, "Select4"):
            doc.ClearSelection2(True)
            result = entity.Select4(False, None)
            print(f"Select4 result: {result}")

            sel_mgr = doc.SelectionManager
            count = sel_mgr.GetSelectedObjectCount()
            print(f"Selected objects: {count}")
    except Exception as ex:
        print(f"QI to IEntity failed: {ex}")

    # Try using the raw live_edge directly with Select2
    print("\n=== Direct Select2 on live_edge ===")
    try:
        if hasattr(live_edge, "Select2"):
            doc.ClearSelection2(True)
            result = live_edge.Select2(False, 0)
            print(f"Select2 result: {result}")
        else:
            print("No Select2 method")
    except Exception as ex:
        print(f"Select2 failed: {ex}")

    # Try SelectByID2
    print("\n=== SelectByID2 ===")
    try:
        doc.ClearSelection2(True)
        # Try selecting as EDGE
        result = doc.SelectByID2("", "EDGE", 0, 0, 0, False, 0, None, 0)
        print(f"SelectByID2 result: {result}")
    except Exception as ex:
        print(f"SelectByID2 failed: {ex}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
