"""Diagnostic: list all methods on IEdge."""
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
        print("No typed edge")
        sys.exit(1)

    # List all methods
    print("=== IEdge methods ===")
    methods = [m for m in dir(typed_edge) if not m.startswith('_')]
    for m in sorted(methods):
        print(f"  {m}")

    # Check if there's a SelectByID we can use
    print("\n=== Checking for selection-related attributes ===")
    for attr in ['GetEntityId', 'GetId', 'Id', 'GetSelectById', 'GetSelectionId']:
        if hasattr(typed_edge, attr):
            print(f"  {attr}: EXISTS")
            try:
                val = getattr(typed_edge, attr)
                if callable(val):
                    print(f"    (callable)")
                else:
                    print(f"    value: {val}")
            except Exception as ex:
                print(f"    error: {ex}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
