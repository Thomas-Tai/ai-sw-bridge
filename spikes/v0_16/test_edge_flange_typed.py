"""Diagnostic: test typed IEdge + selection for edge flange."""
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

    # Get live edges and QI to IEdge
    bodies = doc.GetBodies2(0, True)
    edges_raw = bodies[0].GetEdges()
    ext = typed_extension(doc, module=mod)
    
    live_edges_generic = []
    typed_edges = []
    for e in edges_raw:
        pid = ext.GetPersistReference3(e)
        if pid is None:
            continue
        result = ext.GetObjectByPersistReference3(pid)
        obj = result[0] if isinstance(result, tuple) else result
        if obj is not None and not isinstance(obj, int):
            live_edges_generic.append(obj)
            # Try to QI to IEdge
            try:
                typed_edge = typed_qi(obj, "IEdge", module=mod)
                typed_edges.append(typed_edge)
            except Exception as ex:
                print(f"  QI to IEdge failed: {ex}")
    
    print(f"live edges (generic): {len(live_edges_generic)}")
    print(f"typed edges (IEdge): {len(typed_edges)}")

    if not typed_edges:
        print("No typed edges available, exiting")
        sys.exit(1)

    # Test 1: VARIANT with typed IEdge objects
    print("\n=== Test 1: VARIANT with typed IEdge ===")
    try:
        efl_data = fm.CreateDefinition(37)
        efl = typed_qi(efl_data, "IEdgeFlangeFeatureData", module=mod)
        efl.BendAngle = 1.5708
        efl.BendRadius = 0.002
        efl.UseDefaultBendRadius = False
        
        edge_var = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
            typed_edges
        )
        efl.Edges = edge_var
        count = efl.GetEdgeCount()
        print(f"  Edges with typed IEdge, count={count}")
        if count > 0:
            print("  SUCCESS!")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 2: Select edges first, then AddEdges
    print("\n=== Test 2: Select then AddEdges ===")
    try:
        efl2_data = fm.CreateDefinition(37)
        efl2 = typed_qi(efl2_data, "IEdgeFlangeFeatureData", module=mod)
        efl2.BendAngle = 1.5708
        efl2.BendRadius = 0.002
        efl2.UseDefaultBendRadius = False
        
        # Select the first edge
        doc.ClearSelection2(True)
        sel_result = typed_edges[0].Select4(False, None)
        print(f"  Selected edge: {sel_result}")
        
        # Now try AddEdges with the selection
        efl2.AddEdges([typed_edges[0]])
        count = efl2.GetEdgeCount()
        print(f"  AddEdges after selection, count={count}")
        if count > 0:
            print("  SUCCESS!")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 3: Use ISetEdges with typed edges
    print("\n=== Test 3: ISetEdges with typed IEdge ===")
    try:
        efl3_data = fm.CreateDefinition(37)
        efl3 = typed_qi(efl3_data, "IEdgeFlangeFeatureData", module=mod)
        efl3.BendAngle = 1.5708
        efl3.BendRadius = 0.002
        efl3.UseDefaultBendRadius = False
        
        edge_var = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
            typed_edges
        )
        efl3.ISetEdges(edge_var)
        count = efl3.GetEdgeCount()
        print(f"  ISetEdges with typed IEdge, count={count}")
        if count > 0:
            print("  SUCCESS!")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 4: If we got edges, try CreateFeature
    print("\n=== Test 4: CreateFeature ===")
    for label, efl_x_data in [("Test 1", efl_data if 'efl_data' in locals() else None),
                               ("Test 2", efl2_data if 'efl2_data' in locals() else None),
                               ("Test 3", efl3_data if 'efl3_data' in locals() else None)]:
        if efl_x_data is None:
            continue
        try:
            efl_x = typed_qi(efl_x_data, "IEdgeFlangeFeatureData", module=mod)
            count = efl_x.GetEdgeCount()
            if count > 0:
                doc.ClearSelection2(True)
                efeat = fm.CreateFeature(efl_x_data)
                if efeat:
                    tname = getattr(efeat, 'GetTypeName2', lambda: '?')()
                    print(f"  {label}: CreateFeature OK: {efeat.Name} ({tname})")
                else:
                    print(f"  {label}: CreateFeature returned None")
            else:
                print(f"  {label}: edge count is 0, skipping")
        except Exception as ex:
            print(f"  {label}: {ex}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
