"""Diagnostic: test VARIANT marshaling for edge flange edges."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "v0_15"))

import pythoncom
import win32com.client

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

    # Get live edges
    bodies = doc.GetBodies2(0, True)
    edges_raw = bodies[0].GetEdges()
    ext = typed_extension(doc, module=mod)
    live_edges = []
    for e in edges_raw:
        pid = ext.GetPersistReference3(e)
        if pid is None:
            continue
        result = ext.GetObjectByPersistReference3(pid)
        obj = result[0] if isinstance(result, tuple) else result
        if obj is not None and not isinstance(obj, int):
            live_edges.append(obj)
    print(f"live edges: {len(live_edges)}")

    # Create edge flange data
    efl_data = fm.CreateDefinition(37)
    efl = typed_qi(efl_data, "IEdgeFlangeFeatureData", module=mod)
    efl.BendAngle = 1.5708
    efl.BendRadius = 0.002
    efl.UseDefaultBendRadius = False

    # Test 1: VARIANT(VT_ARRAY | VT_DISPATCH) to Edges property
    print("\n=== Test 1: VARIANT to Edges property ===")
    try:
        edge_var = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, live_edges
        )
        print(f"  VARIANT created: {type(edge_var).__name__}")
        efl.Edges = edge_var
        count = efl.GetEdgeCount()
        print(f"  Edges assigned, count={count}")
        if count > 0:
            print("  SUCCESS!")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 2: VARIANT to AddEdges
    print("\n=== Test 2: VARIANT to AddEdges ===")
    try:
        efl2_data = fm.CreateDefinition(37)
        efl2 = typed_qi(efl2_data, "IEdgeFlangeFeatureData", module=mod)
        efl2.BendAngle = 1.5708
        efl2.BendRadius = 0.002
        efl2.UseDefaultBendRadius = False
        edge_var2 = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, live_edges
        )
        efl2.AddEdges(edge_var2)
        count = efl2.GetEdgeCount()
        print(f"  AddEdges with VARIANT, count={count}")
        if count > 0:
            print("  SUCCESS!")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 3: VARIANT with _oleobj_ pointers
    print("\n=== Test 3: VARIANT with _oleobj_ pointers ===")
    try:
        efl3_data = fm.CreateDefinition(37)
        efl3 = typed_qi(efl3_data, "IEdgeFlangeFeatureData", module=mod)
        efl3.BendAngle = 1.5708
        efl3.BendRadius = 0.002
        efl3.UseDefaultBendRadius = False
        raw_ptrs = [e._oleobj_ for e in live_edges]
        edge_var3 = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, raw_ptrs
        )
        efl3.Edges = edge_var3
        count = efl3.GetEdgeCount()
        print(f"  Edges with _oleobj_, count={count}")
        if count > 0:
            print("  SUCCESS!")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 4: If any method got edges, try CreateFeature
    print("\n=== Test 4: CreateFeature with edges ===")
    for label, efl_x_data in [("Edges prop", efl_data)]:
        try:
            efl_x = typed_qi(efl_x_data, "IEdgeFlangeFeatureData", module=mod)
            count = efl_x.GetEdgeCount()
            if count > 0:
                doc.ClearSelection2(True)
                efeat = fm.CreateFeature(efl_x_data)
                if efeat:
                    print(f"  {label}: CreateFeature Ok: {efeat.Name}")
                else:
                    print(f"  {label}: CreateFeature returned None")
            else:
                print(f"  {label}: edge count is 0, skipping")
        except Exception as ex:
            print(f"  {label}: {ex}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
