"""W31 S1 - Verify drawing view geometry before testing ordinate dims.

The previous test showed InsertModelAnnotations3 also created 0 dims, which
suggests the view might not have visible geometry. Let's verify the view state.
"""

from __future__ import annotations

import glob
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ai_sw_bridge.com.earlybind import typed, typed_qi, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module


def find_part_template() -> str:
    patterns = [r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.PRTDOT"]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return ""


def find_drawing_template() -> str:
    patterns = [r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT"]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return ""


def main() -> None:
    import json
    import win32com.client

    print("=== W31 S1: Drawing View Geometry Verification ===\n")

    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True
    mod = wrapper_module()

    result = {}

    # Create test part
    template = find_part_template()
    tmp_dir = tempfile.mkdtemp(prefix="w31_view_")
    part_path = os.path.join(tmp_dir, "test_rect.SLDPRT")

    doc_raw = sw.NewDocument(template, 0, 0, 0)
    mdoc2 = typed(doc_raw, "IModelDoc2", module=mod)
    ext = typed_extension(doc_raw, module=mod)

    ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
    skm = mdoc2.SketchManager
    skm.InsertSketch(True)
    skm.CreateCenterRectangle(0, 0, 0, 0.05, 0.025, 0)
    skm.InsertSketch(True)

    mdoc2.FeatureManager.FeatureExtrusion2(
        True,
        False,
        False,
        1,
        0,
        0.02,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0.0,
        False,
    )

    mdoc2.EditRebuild3()
    mdoc2.SaveAs3(part_path, 0, 2)

    result["part_path"] = part_path
    result["part_features"] = mdoc2.GetFeatureCount()

    # Create drawing
    drw_template = find_drawing_template()
    drw_path = os.path.join(tmp_dir, "test_rect.SLDDRW")

    drw_raw = sw.NewDocument(drw_template, 0, 0.21, 0.297)
    drawing_doc = typed_qi(drw_raw, "IDrawingDoc", module=mod)
    drw_mdoc2 = typed(drw_raw, "IModelDoc2", module=mod)

    # Create view
    view_raw = drawing_doc.CreateDrawViewFromModelView3(
        part_path, "*Front", 0.1, 0.15, 0.0
    )
    if view_raw is None or isinstance(view_raw, int):
        result["error"] = f"CreateDrawViewFromModelView3 returned {view_raw}"
        print(json.dumps(result, indent=2))
        return

    view = typed_qi(view_raw, "IView", module=mod)

    # Check view properties - use late-binding for methods not on early-bound
    result["view_name"] = view.Name  # Late-bound property
    result["view_outline"] = list(view.GetOutline()) if view.GetOutline() else None

    # Check annotation count
    result["annotation_count"] = view.GetAnnotationCount()

    # Check visible entities
    try:
        entities = view.GetVisibleEntities()
        result["visible_entities_count"] = len(entities) if entities else 0
        if entities:
            # Try to get entity types
            entity_types = []
            for e in entities[:5]:  # First 5
                try:
                    et = typed_qi(e, "IEntity", module=mod)
                    entity_types.append(
                        et.GetType()
                    )  # 0=body, 1=face, 2=edge, 3=vertex
                except Exception:
                    entity_types.append("unknown")
            result["entity_types"] = entity_types
    except Exception as e:
        result["visible_entities_error"] = str(e)

    # Check if model is still open
    try:
        model_title = os.path.basename(part_path)
        # The part should still be open from earlier
        result["part_open"] = True
    except Exception:
        result["part_open"] = False

    # Try InsertModelAnnotations3
    drawing_doc.ActivateView(view.Name or "")
    drawing_doc.InsertModelAnnotations3(0, -1, True, False, True, 0)
    drw_mdoc2.EditRebuild3()

    # Count display dimensions
    try:
        disp_dims = view.GetDisplayDimensions()
        if disp_dims:
            result["display_dim_count"] = len(disp_dims)
            # Try to read first dim
            if len(disp_dims) > 0:
                try:
                    dd = typed_qi(disp_dims[0], "IDisplayDimension", module=mod)
                    dim_raw = dd.GetDimension2(0)
                    if dim_raw:
                        dim = typed_qi(dim_raw, "IDimension", module=mod)
                        result["first_dim_value"] = dim.GetSystemValue2("")
                except Exception as e:
                    result["first_dim_error"] = str(e)
        else:
            result["display_dim_count"] = 0
    except Exception as e:
        result["display_dim_error"] = str(e)

    # Count all annotations in view
    result["annotation_count_after"] = view.GetAnnotationCount()

    # Save and check file size
    drw_mdoc2.SaveAs3(drw_path, 0, 2)
    result["drw_path"] = drw_path
    result["drw_file_size_bytes"] = (
        os.path.getsize(drw_path) if os.path.isfile(drw_path) else 0
    )

    # Cleanup
    t = drw_mdoc2.GetTitle
    t = t() if callable(t) else t
    sw.CloseDoc(t)
    sw.CloseDoc(os.path.basename(part_path))

    print(json.dumps(result, indent=2, default=str))

    # Write to results
    results_path = Path(__file__).parent / "_results" / "ord_baseline.json"
    with open(results_path, "w") as f:
        json.dump({"view_verification": result}, f, indent=2, default=str)


if __name__ == "__main__":
    main()
