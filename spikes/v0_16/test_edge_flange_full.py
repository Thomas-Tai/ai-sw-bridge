"""Diagnostic: full edge flange creation with selection."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "v0_15"))

import pythoncom
import win32com.client

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
    print(f"base flange: {feat.Name}")

    # Get live edge
    bodies = doc.GetBodies2(0, True)
    edges_raw = bodies[0].GetEdges()
    ext = typed_extension(doc, module=mod)
    
    raw_edge = edges_raw[0]
    pid = ext.GetPersistReference3(raw_edge)
    result = ext.GetObjectByPersistReference3(pid)
    live_edge = result[0] if isinstance(result, tuple) else result
    
    # Select the edge
    doc.ClearSelection2(True)
    sel_result = live_edge.Select2(False, 0)
    print(f"Selected edge: {sel_result}")
    
    sel_mgr = doc.SelectionManager
    count = sel_mgr.GetSelectedObjectCount
    print(f"Selection count: {count}")

    # Test 1: InsertSheetMetalEdgeFlange with minimal params
    print("\n=== Test 1: InsertSheetMetalEdgeFlange (8 params) ===")
    try:
        feat2 = fm.InsertSheetMetalEdgeFlange(
            1.5708,     # BendAngle (90 degrees in radians)
            False,      # ReverseDirection
            True,       # UseDefaultBendRadius
            0.002,      # BendRadius
            False,      # Flipped
            False,      # UsePositionSchedule
            0,          # PositionSchedule
            0           # PositionType
        )
        if feat2:
            print(f"SUCCESS: {feat2.Name}")
        else:
            print("FAILED: returned None")
    except Exception as ex:
        print(f"FAILED: {type(ex).__name__}: {ex}")

    # Test 2: Try with different param count
    print("\n=== Test 2: InsertSheetMetalEdgeFlange (6 params) ===")
    try:
        feat3 = fm.InsertSheetMetalEdgeFlange(
            1.5708,     # BendAngle
            False,      # ReverseDirection
            True,       # UseDefaultBendRadius
            0.002,      # BendRadius
            False,      # Flipped
            False       # UsePositionSchedule
        )
        if feat3:
            print(f"SUCCESS: {feat3.Name}")
        else:
            print("FAILED: returned None")
    except Exception as ex:
        print(f"FAILED: {type(ex).__name__}: {ex}")

    # Test 3: Try CreateDefinition approach with selection
    print("\n=== Test 3: CreateDefinition(37) with selection ===")
    try:
        doc.ClearSelection2(True)
        live_edge.Select2(False, 0)
        
        efl_data = fm.CreateDefinition(37)
        efl = typed_qi(efl_data, "IEdgeFlangeFeatureData", module=mod)
        efl.BendAngle = 1.5708
        efl.BendRadius = 0.002
        efl.UseDefaultBendRadius = False
        
        # Don't call AddEdges - let it use the selection
        count = efl.GetEdgeCount()
        print(f"Edge count (from selection): {count}")
        
        if count > 0:
            efeat = fm.CreateFeature(efl_data)
            if efeat:
                print(f"SUCCESS: {efeat.Name}")
            else:
                print("FAILED: CreateFeature returned None")
        else:
            print("FAILED: no edges from selection")
    except Exception as ex:
        print(f"FAILED: {type(ex).__name__}: {ex}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
