"""Test: pass IEntity objects in VARIANT for AddEdges."""

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

    # Get live edge and QI to IEntity
    bodies = doc.GetBodies2(0, True)
    edges_raw = bodies[0].GetEdges()
    ext = typed_extension(doc, module=mod)

    raw_edge = edges_raw[0]
    pid = ext.GetPersistReference3(raw_edge)
    result = ext.GetObjectByPersistReference3(pid)
    live_edge = result[0] if isinstance(result, tuple) else result

    # QI to IEntity
    entity = typed_qi(live_edge, "IEntity", module=mod)
    print(f"Entity type: {type(entity).__name__}")

    # Test 1: VARIANT with IEntity
    print("\n=== Test 1: VARIANT with IEntity ===")
    try:
        efl_data = fm.CreateDefinition(37)
        efl = typed_qi(efl_data, "IEdgeFlangeFeatureData", module=mod)
        efl.BendAngle = 1.5708
        efl.BendRadius = 0.002
        efl.UseDefaultBendRadius = False

        edge_var = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [entity]
        )
        efl.Edges = edge_var
        count = efl.GetEdgeCount()
        print(f"  Edges with IEntity, count={count}")
        if count > 0:
            print("  SUCCESS!")
            efeat = fm.CreateFeature(efl_data)
            if efeat:
                print(f"  CreateFeature: {efeat.Name}")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 2: VARIANT with IEntity._oleobj_
    print("\n=== Test 2: VARIANT with IEntity._oleobj_ ===")
    try:
        efl_data2 = fm.CreateDefinition(37)
        efl2 = typed_qi(efl_data2, "IEdgeFlangeFeatureData", module=mod)
        efl2.BendAngle = 1.5708
        efl2.BendRadius = 0.002
        efl2.UseDefaultBendRadius = False

        edge_var2 = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [entity._oleobj_]
        )
        efl2.Edges = edge_var2
        count = efl2.GetEdgeCount()
        print(f"  Edges with IEntity._oleobj_, count={count}")
        if count > 0:
            print("  SUCCESS!")
            efeat = fm.CreateFeature(efl_data2)
            if efeat:
                print(f"  CreateFeature: {efeat.Name}")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    # Test 3: Multiple edges as IEntity
    print("\n=== Test 3: Multiple edges as IEntity ===")
    try:
        # Get multiple edges as IEntity
        entities = []
        for raw_e in edges_raw[:3]:  # First 3 edges
            pid = ext.GetPersistReference3(raw_e)
            if pid is None:
                continue
            result = ext.GetObjectByPersistReference3(pid)
            live_e = result[0] if isinstance(result, tuple) else result
            if live_e is not None and not isinstance(live_e, int):
                ent = typed_qi(live_e, "IEntity", module=mod)
                entities.append(ent)

        print(f"  Got {len(entities)} entities")

        efl_data3 = fm.CreateDefinition(37)
        efl3 = typed_qi(efl_data3, "IEdgeFlangeFeatureData", module=mod)
        efl3.BendAngle = 1.5708
        efl3.BendRadius = 0.002
        efl3.UseDefaultBendRadius = False

        edge_var3 = win32com.client.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, entities
        )
        efl3.Edges = edge_var3
        count = efl3.GetEdgeCount()
        print(f"  Edges with multiple IEntity, count={count}")
        if count > 0:
            print("  SUCCESS!")
    except Exception as ex:
        print(f"  FAILED: {type(ex).__name__}: {ex}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
