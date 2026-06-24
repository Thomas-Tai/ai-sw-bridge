"""Diagnostic: check IEdge selection methods and legacy InsertSheetMetalEdgeFlange."""

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

    # Get typed IEdge
    bodies = doc.GetBodies2(0, True)
    edges_raw = bodies[0].GetEdges()
    ext = typed_extension(doc, module=mod)

    typed_edge = None
    for e in edges_raw:
        pid = ext.GetPersistReference3(e)
        if pid is None:
            continue
        result = ext.GetObjectByPersistReference3(pid)
        obj = result[0] if isinstance(result, tuple) else result
        if obj is not None and not isinstance(obj, int):
            try:
                typed_edge = typed_qi(obj, "IEdge", module=mod)
                break
            except:
                continue

    if not typed_edge:
        print("No typed edge available")
        sys.exit(1)

    # Check what selection methods exist
    print("\n=== Checking IEdge selection methods ===")
    for method in ["Select", "Select2", "Select3", "Select4"]:
        if hasattr(typed_edge, method):
            print(f"  {method}: EXISTS")
        else:
            print(f"  {method}: missing")

    # Test 1: Try Select2
    print("\n=== Test 1: Select2 ===")
    try:
        doc.ClearSelection2(True)
        result = typed_edge.Select2(False, 0)
        print(f"  Select2 result: {result}")

        # Check selection count
        sel_mgr = doc.SelectionManager
        count = sel_mgr.GetSelectedObjectCount()
        print(f"  Selected objects: {count}")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 2: Try legacy InsertSheetMetalEdgeFlange with pre-selection
    print("\n=== Test 2: Legacy InsertSheetMetalEdgeFlange ===")
    try:
        doc.ClearSelection2(True)
        typed_edge.Select2(False, 0)

        # Try with VARIANT for the edge array
        edge_var = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [typed_edge]
        )

        feat2 = fm.InsertSheetMetalEdgeFlange(
            0.002,  # Thickness
            0.001,  # BendRadius
            edge_var,  # Edges as VARIANT
            1.5708,  # BendAngle (90 degrees)
            False,  # AutoRelease
            1,  # FlangePosition (1 = Material Inside)
            False,  # UseDefaultBendRadius
            0.0,  # Offset
            0.001,  # ReliefRatio
            True,  # UseReliefRatio
            0,  # ReliefType
            0.001,  # ReliefWidth
            0.001,  # ReliefDepth
            False,  # UseGaugeTable
            "",  # GaugeTablePath
            False,  # OverrideDefaultSheetMetalParameters
        )

        if feat2:
            print(f"  SUCCESS: {feat2.Name}")
        else:
            print(f"  FAILED: returned None")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 3: Try InsertSheetMetalEdgeFlange without VARIANT
    print("\n=== Test 3: Legacy without VARIANT ===")
    try:
        doc.ClearSelection2(True)
        typed_edge.Select2(False, 0)

        feat3 = fm.InsertSheetMetalEdgeFlange(
            0.002,  # Thickness
            0.001,  # BendRadius
            [typed_edge],  # Edges as list
            1.5708,  # BendAngle
            False,  # AutoRelease
            1,  # FlangePosition
            False,  # UseDefaultBendRadius
            0.0,  # Offset
            0.001,  # ReliefRatio
            True,  # UseReliefRatio
            0,  # ReliefType
            0.001,  # ReliefWidth
            0.001,  # ReliefDepth
            False,  # UseGaugeTable
            "",  # GaugeTablePath
            False,  # OverrideDefaultSheetMetalParameters
        )

        if feat3:
            print(f"  SUCCESS: {feat3.Name}")
        else:
            print(f"  FAILED: returned None")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
