"""Test: ExportToDWG2 with more parameter combinations."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "v0_15"))

import pythoncom
import tempfile

pythoncom.CoInitialize()
try:
    from spike_earlybind_persist import connect_running_sw, ensure_sw_module
    from ai_sw_bridge.com.earlybind import typed_qi, typed
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

    # Save the document first
    tmp_dir = Path(tempfile.gettempdir())
    tmp_dir.mkdir(parents=True, exist_ok=True)
    sldprt_path = tmp_dir / "test_sheet_metal.SLDPRT"
    doc.SaveAs(str(sldprt_path))
    print(f"Saved to: {sldprt_path}")

    # Get typed IPartDoc
    part = typed(doc, "IPartDoc", module=mod)

    # Create export path
    dxf_path = tmp_dir / "test_flat_pattern.dxf"
    model_name = doc.GetPathName
    print(f"Model name: {model_name}")
    print(f"Export path: {dxf_path}")

    # Try many parameter combinations
    print("")
    print("=== Parameter combinations ===")
    tests = [
        ("2 params", (str(dxf_path), 1)),
        ("3 params v1", (str(dxf_path), model_name, 1)),
        ("3 params v2", (str(dxf_path), 1, 1)),
        ("4 params v1", (str(dxf_path), model_name, 1, True)),
        ("4 params v2", (str(dxf_path), 1, 1, True)),
        ("5 params v1", (str(dxf_path), model_name, 1, True, 0)),
        ("5 params v2", (str(dxf_path), model_name, 1, 1, 0)),
        ("6 params v1", (str(dxf_path), model_name, 1, True, 0, False)),
        ("6 params v2", (str(dxf_path), model_name, 1, 1, 0, 0)),
        ("7 params", (str(dxf_path), model_name, 1, True, 0, False, 0)),
    ]
    for name, params in tests:
        print(f"  {name}:")
        try:
            result = part.ExportToDWG2(*params)
            print(f"    Result: {result}")
            if dxf_path.exists():
                print(f"    SUCCESS: {dxf_path.stat().st_size} bytes")
                dxf_path.unlink()
                break
        except Exception as ex:
            print(f"    FAILED: {type(ex).__name__}: {str(ex)[:60]}")

    # Clean up
    if sldprt_path.exists():
        sldprt_path.unlink()

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
