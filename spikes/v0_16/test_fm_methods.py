"""Check all FeatureManager methods."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "v0_15"))

import pythoncom

pythoncom.CoInitialize()
try:
    from spike_earlybind_persist import connect_running_sw, ensure_sw_module
    from ai_sw_bridge.com.earlybind import typed_qi
    from ai_sw_bridge.com.sw_type_info import wrapper_module

    mod = wrapper_module() or ensure_sw_module()[0]
    sw = connect_running_sw()
    template = sw.GetUserPreferenceStringValue(8)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)

    fm = doc.FeatureManager
    typed_fm = typed_qi(fm, "IFeatureManager", module=mod)

    # Get all methods
    methods = [m for m in dir(typed_fm) if not m.startswith("_")]
    print(f"Total methods: {len(methods)}")
    print("")

    # Filter for flange-related methods
    flange_methods = [m for m in methods if "flange" in m.lower() or "Flange" in m]
    print(f"Flange-related methods ({len(flange_methods)}):")
    for m in sorted(flange_methods):
        print(f"  {m}")

    # Also check for sheet metal methods
    print("")
    sm_methods = [m for m in methods if "sheet" in m.lower() or "Sheet" in m or "metal" in m.lower() or "Metal" in m]
    print(f"Sheet metal methods ({len(sm_methods)}):")
    for m in sorted(sm_methods):
        print(f"  {m}")

    sw.CloseDoc(doc.GetTitle)
finally:
    pythoncom.CoUninitialize()
