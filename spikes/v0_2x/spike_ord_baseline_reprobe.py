"""W31v S1 - Re-probe ordinate/baseline dimensions with PROVEN selection paths.

Gate 1: Can we select an in-view datum?
- Route 1: IView.SelectEntity(entity, append) - the direct method
- Route 2: IEntity.Select2(append, mark) with view ACTIVE
- Route 3: SketchManager.CreatePoint → Select2

Gate 2: Does AddOrdinateDimension create dims with datum selected?

Evidence: ISelectionMgr.GetSelectedObjectCount2(-1) after each selection attempt.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

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


def create_test_part(sw, mod) -> tuple[str, Any, Any]:
    """Create a simple rectangular part with extruded features.

    Returns (part_path, mdoc2, part_doc).
    """
    tmp_dir = tempfile.mkdtemp(prefix="w31v_")
    part_path = os.path.join(tmp_dir, "test_rect_part.SLDPRT")

    template = find_part_template()
    if not template:
        raise RuntimeError("No part template found")

    doc_raw = sw.NewDocument(template, 0, 0, 0)
    if doc_raw is None or isinstance(doc_raw, int):
        raise RuntimeError("NewDocument(part) returned None")

    mdoc2 = typed(doc_raw, "IModelDoc2", module=mod)
    ext = typed_extension(doc_raw, module=mod)

    # Create a rectangle with extrusion
    ext.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
    skm = mdoc2.SketchManager
    skm.InsertSketch(True)
    skm.CreateCenterRectangle(0, 0, 0, 0.05, 0.025, 0)  # 100x50mm
    skm.InsertSketch(True)

    # Extrude 20mm
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

    return part_path, mdoc2, doc_raw


def create_test_drawing(sw, mod, part_path: str) -> tuple[str, Any, Any, Any]:
    """Create a drawing with a front view.

    Returns (drw_path, drawing_doc, mdoc2, view).
    """
    tmp_dir = tempfile.mkdtemp(prefix="w31v_draw_")
    drw_path = os.path.join(tmp_dir, "test_rect_drawing.SLDDRW")

    template = find_drawing_template()
    if not template:
        raise RuntimeError("No drawing template found")

    doc_raw = sw.NewDocument(template, 0, 0.21, 0.297)
    if doc_raw is None or isinstance(doc_raw, int):
        raise RuntimeError("NewDocument(drawing) returned None")

    drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
    mdoc2 = typed(doc_raw, "IModelDoc2", module=mod)

    view_raw = drawing_doc.CreateDrawViewFromModelView3(
        part_path, "*Front", 0.1, 0.15, 0.0
    )
    if view_raw is None or isinstance(view_raw, int):
        raise RuntimeError(f"CreateDrawViewFromModelView3 returned {view_raw}")

    view = typed_qi(view_raw, "IView", module=mod)
    mdoc2.SaveAs3(drw_path, 0, 2)

    return drw_path, drawing_doc, mdoc2, view


def get_selection_count(doc, mod) -> int:
    """Get ISelectionMgr.GetSelectedObjectCount2(-1)."""
    try:
        sel_mgr = doc.ISelectionManager
        if sel_mgr is None:
            return 0
        typed_sel_mgr = typed_qi(sel_mgr, "ISelectionMgr", module=mod)
        return typed_sel_mgr.GetSelectedObjectCount2(-1)
    except Exception:
        return 0


def clear_selection(doc, mod) -> None:
    """Clear selection via ISelectionMgr."""
    try:
        sel_mgr = doc.ISelectionManager
        if sel_mgr:
            typed_sel_mgr = typed_qi(sel_mgr, "ISelectionMgr", module=mod)
            typed_sel_mgr.ClearSelection2(-1)
    except Exception:
        pass


def count_dims(view, mod) -> tuple[int, list[dict]]:
    """Count display dimensions in a view."""
    try:
        disp_dims = view.GetDisplayDimensions()
    except Exception:
        return 0, []

    if not disp_dims:
        return 0, []

    dims = []
    for dd_raw in disp_dims:
        if dd_raw is None:
            continue
        try:
            dd = typed_qi(dd_raw, "IDisplayDimension", module=mod)
            dim_raw = dd.GetDimension2(0)
            if dim_raw is None:
                continue
            dim = typed_qi(dim_raw, "IDimension", module=mod)

            dim_type = None
            value = None
            try:
                dim_type = dd.GetType()
            except Exception:
                pass
            try:
                value = dim.GetSystemValue2("")
            except Exception:
                pass

            dims.append({"type": dim_type, "value": value})
        except Exception:
            continue

    return len(dims), dims


def test_gate1_selection(sw, mod) -> dict:
    """Gate 1: Test all three selection routes with ISelectionMgr evidence."""
    result = {
        "gate": 1,
        "question": "Can we select an in-view datum?",
        "routes": {},
    }

    try:
        part_path, part_mdoc2, part_doc = create_test_part(sw, mod)
        drw_path, drawing_doc, drw_mdoc2, view = create_test_drawing(sw, mod, part_path)

        # Activate the view
        view_name = view.Name
        drawing_doc.ActivateView(view_name)

        # Get selection manager from drawing doc
        sel_count_before = get_selection_count(drw_mdoc2, mod)
        result["sel_count_before"] = sel_count_before

        # --------------------------------------------------------------
        # Route 1: IView.SelectEntity(entity, append)
        # --------------------------------------------------------------
        result["routes"]["route1"] = {"method": "IView.SelectEntity"}

        # Get a visible entity from the view
        # EntityType values: 1=face, 2=edge, 3=vertex
        # Try edges first (EntityType=2)
        try:
            # GetVisibleEntities(ViewComponent, EntityType)
            # ViewComponent=None for all visible entities
            entities_raw = view.GetVisibleEntities(None, 2)  # 2 = edge
            result["routes"]["route1"]["get_visible_edges_result"] = str(
                entities_raw is not None
            )
            result["routes"]["route1"]["get_visible_edges_type"] = type(
                entities_raw
            ).__name__

            if entities_raw is not None and not isinstance(entities_raw, int):
                # Check if it's an iterable
                if hasattr(entities_raw, "__iter__") and not isinstance(
                    entities_raw, (str, bytes)
                ):
                    entity_count = len(list(entities_raw)) if entities_raw else 0
                    result["routes"]["route1"]["visible_edge_count"] = entity_count

                    if entity_count > 0:
                        # Get first edge
                        edges = list(entities_raw)
                        first_edge = edges[0]

                        # Try SelectEntity
                        clear_selection(drw_mdoc2, mod)
                        try:
                            sel_ok = view.SelectEntity(first_edge, False)
                            result["routes"]["route1"]["select_entity_result"] = str(
                                sel_ok
                            )

                            # Check selection count on drawing doc
                            sel_count_after = get_selection_count(drw_mdoc2, mod)
                            result["routes"]["route1"][
                                "sel_count_after"
                            ] = sel_count_after

                            # Also check on part doc's SelectionMgr
                            part_sel_count = get_selection_count(part_mdoc2, mod)
                            result["routes"]["route1"][
                                "part_sel_count_after"
                            ] = part_sel_count

                            if sel_count_after > 0 or part_sel_count > 0:
                                result["routes"]["route1"]["success"] = True
                                result["routes"]["route1"][
                                    "selected_entity_type"
                                ] = "edge"
                                result["routes"]["route1"]["selection_context"] = (
                                    "drawing" if sel_count_after > 0 else "part"
                                )
                            else:
                                result["routes"]["route1"]["success"] = False
                                result["routes"]["route1"][
                                    "reason"
                                ] = "sel_count stayed 0 on both drawing and part"
                        except Exception as e:
                            result["routes"]["route1"]["select_entity_error"] = str(e)
                    else:
                        result["routes"]["route1"]["reason"] = "no visible edges"
                else:
                    result["routes"]["route1"][
                        "reason"
                    ] = f"entities not iterable: {type(entities_raw)}"
            else:
                result["routes"]["route1"][
                    "reason"
                ] = f"GetVisibleEntities returned None/int"
        except Exception as e:
            result["routes"]["route1"]["get_visible_entities_error"] = str(e)

        # Also try vertices (EntityType=3)
        clear_selection(drw_mdoc2, mod)
        try:
            vertices_raw = view.GetVisibleEntities(None, 3)  # 3 = vertex
            result["routes"]["route1"]["get_visible_vertices_result"] = str(
                vertices_raw is not None
            )

            if vertices_raw is not None and hasattr(vertices_raw, "__iter__"):
                vertex_count = len(list(vertices_raw)) if vertices_raw else 0
                result["routes"]["route1"]["visible_vertex_count"] = vertex_count

                if vertex_count > 0:
                    vertices = list(vertices_raw)
                    first_vertex = vertices[0]

                    clear_selection(drw_mdoc2, mod)
                    try:
                        sel_ok = view.SelectEntity(first_vertex, False)
                        result["routes"]["route1"]["select_vertex_result"] = str(sel_ok)

                        sel_count_after = get_selection_count(drw_mdoc2, mod)
                        result["routes"]["route1"][
                            "sel_count_after_vertex"
                        ] = sel_count_after

                        if sel_count_after > 0:
                            result["routes"]["route1"][
                                "vertex_selection_success"
                            ] = True
                    except Exception as e:
                        result["routes"]["route1"]["select_vertex_error"] = str(e)
        except Exception as e:
            result["routes"]["route1"]["get_visible_vertices_error"] = str(e)

        # --------------------------------------------------------------
        # Route 2: IEntity.Select2 with view ACTIVE
        # Get a model entity from the part and select it
        # --------------------------------------------------------------
        result["routes"]["route2"] = {
            "method": "IEntity.Select2 (model entity with view active)"
        }
        clear_selection(drw_mdoc2, mod)

        try:
            # Get a body from the part
            bodies = part_mdoc2.GetBodies2(0, True)  # swSolidBody=0, visible only
            if bodies and len(bodies) > 0:
                body = bodies[0]
                edges = body.GetEdges2()  # or GetEdges

                if edges and len(edges) > 0:
                    first_model_edge = edges[0]

                    # Get IEntity interface
                    entity = typed_qi(first_model_edge, "IEntity", module=mod)

                    # Select via IEntity.Select2
                    try:
                        sel_ok = entity.Select2(False, 0)  # append=False, mark=0
                        result["routes"]["route2"]["entity_select2_result"] = str(
                            sel_ok
                        )

                        sel_count_after = get_selection_count(drw_mdoc2, mod)
                        result["routes"]["route2"]["sel_count_after"] = sel_count_after

                        if sel_count_after > 0:
                            result["routes"]["route2"]["success"] = True
                        else:
                            result["routes"]["route2"][
                                "reason"
                            ] = "model entity selected but drawing sel_count=0"
                    except Exception as e:
                        result["routes"]["route2"]["select2_error"] = str(e)
                else:
                    result["routes"]["route2"]["reason"] = "no edges in part body"
            else:
                result["routes"]["route2"]["reason"] = "no bodies in part"
        except Exception as e:
            result["routes"]["route2"]["get_bodies_error"] = str(e)

        # --------------------------------------------------------------
        # Route 3: SketchManager.CreatePoint → Select2 (W19 path)
        # --------------------------------------------------------------
        result["routes"]["route3"] = {"method": "SketchManager.CreatePoint → Select2"}
        clear_selection(drw_mdoc2, mod)

        try:
            # Get view outline for positioning
            outline = view.GetOutline()
            cx = (outline[0] + outline[2]) / 2.0
            cy = (outline[1] + outline[3]) / 2.0

            # Create a point at center of view (in sheet coordinates)
            skm = drw_mdoc2.SketchManager
            point = skm.CreatePoint(cx, cy, 0.0)
            result["routes"]["route3"]["create_point_result"] = str(point is not None)

            if point is not None:
                # Select the point
                try:
                    # Get IEntity from the point
                    point_entity = typed_qi(point, "IEntity", module=mod)
                    sel_ok = point_entity.Select2(False, 0)
                    result["routes"]["route3"]["point_select2_result"] = str(sel_ok)

                    sel_count_after = get_selection_count(drw_mdoc2, mod)
                    result["routes"]["route3"]["sel_count_after"] = sel_count_after

                    if sel_count_after > 0:
                        result["routes"]["route3"]["success"] = True
                    else:
                        result["routes"]["route3"][
                            "reason"
                        ] = "point created but sel_count=0"
                except Exception as e:
                    result["routes"]["route3"]["select_error"] = str(e)
            else:
                result["routes"]["route3"]["reason"] = "CreatePoint returned None"
        except Exception as e:
            result["routes"]["route3"]["sketch_error"] = str(e)

        # Determine overall Gate 1 result
        any_success = any(
            r.get("success") or r.get("vertex_selection_success")
            for r in result["routes"].values()
            if isinstance(r, dict)
        )
        result["gate1_result"] = "PASS" if any_success else "FAIL"

        # Cleanup
        t = drw_mdoc2.GetTitle
        t = t() if callable(t) else t
        sw.CloseDoc(t)
        sw.CloseDoc(os.path.basename(part_path))

    except Exception as e:
        result["error"] = str(e)
        import traceback

        result["traceback"] = traceback.format_exc()

    return result


def test_gate2_ordinate_with_datum(sw, mod) -> dict:
    """Gate 2: Test AddOrdinateDimension after datum selection."""
    result = {
        "gate": 2,
        "question": "Does AddOrdinateDimension create dims with datum selected?",
    }

    try:
        part_path, part_mdoc2, part_doc = create_test_part(sw, mod)
        drw_path, drawing_doc, drw_mdoc2, view = create_test_drawing(sw, mod, part_path)

        view_name = view.Name
        drawing_doc.ActivateView(view_name)

        outline = view.GetOutline()
        x_ll = outline[0]
        y_ll = outline[1]

        # Count dims before
        count_before, dims_before = count_dims(view, mod)
        result["dim_count_before"] = count_before

        # --------------------------------------------------------------
        # Step 1: Get a visible vertex and select it as datum
        # --------------------------------------------------------------
        clear_selection(drw_mdoc2, mod)

        # Try vertices
        vertices_raw = view.GetVisibleEntities(None, 3)  # 3 = vertex
        result["get_visible_entities_result"] = str(vertices_raw is not None)

        if vertices_raw is not None and hasattr(vertices_raw, "__iter__"):
            vertices = list(vertices_raw)
            result["visible_vertex_count"] = len(vertices)

            if len(vertices) > 0:
                datum_vertex = vertices[0]

                # Select the datum vertex
                try:
                    sel_ok = view.SelectEntity(datum_vertex, False)
                    result["datum_select_result"] = str(sel_ok)

                    sel_count = get_selection_count(drw_mdoc2, mod)
                    result["sel_count_after_datum"] = sel_count

                    if sel_count > 0:
                        result["datum_selected"] = True

                        # --------------------------------------------------------------
                        # Step 2: Call AddOrdinateDimension
                        # --------------------------------------------------------------
                        # Try horizontal ordinate (type=0)
                        try:
                            ok_h = drawing_doc.AddOrdinateDimension(
                                0, x_ll + 0.01, y_ll + 0.01, 0.0
                            )
                            result["AddOrdinateDimension(0)_result"] = str(ok_h)
                        except Exception as e:
                            result["AddOrdinateDimension(0)_error"] = str(e)

                        # Try vertical ordinate (type=1)
                        try:
                            ok_v = drawing_doc.AddOrdinateDimension(
                                1, x_ll + 0.02, y_ll + 0.02, 0.0
                            )
                            result["AddOrdinateDimension(1)_result"] = str(ok_v)
                        except Exception as e:
                            result["AddOrdinateDimension(1)_error"] = str(e)

                        # Rebuild and count
                        drw_mdoc2.EditRebuild3()
                        count_after, dims_after = count_dims(view, mod)
                        result["dim_count_after_create"] = count_after
                        result["dims_added_immediately"] = count_after - count_before
                        result["dims_after_create"] = dims_after

                        # Save, close, reopen, verify
                        drw_mdoc2.SaveAs3(drw_path, 0, 2)

                        t = drw_mdoc2.GetTitle
                        t = t() if callable(t) else t
                        sw.CloseDoc(t)
                        sw.CloseDoc(os.path.basename(part_path))

                        # Reopen
                        tsw = typed(sw, "ISldWorks", module=mod)
                        ret = tsw.OpenDoc6(drw_path, 3, 1, "", 0, 0)
                        reopened_doc = ret[0] if isinstance(ret, tuple) else ret

                        if reopened_doc is None:
                            result["error"] = "Failed to reopen drawing"
                            return result

                        reopened_drawing = typed_qi(
                            reopened_doc, "IDrawingDoc", module=mod
                        )
                        reopened_mdoc2 = typed(reopened_doc, "IModelDoc2", module=mod)

                        views_raw = reopened_drawing.GetViews()
                        reopened_view = typed_qi(views_raw[0], "IView", module=mod)

                        count_reopen, dims_reopen = count_dims(reopened_view, mod)
                        result["dim_count_after_reopen"] = count_reopen
                        result["dims_added_final"] = count_reopen - count_before
                        result["dims_reopen"] = dims_reopen

                        if count_reopen > count_before:
                            result["gate2_result"] = "PASS"
                            result["verdict"] = "GREEN"
                        else:
                            result["gate2_result"] = "FAIL"
                            result["verdict"] = "NO-GO"
                            result["reason"] = (
                                "dims added during create but not persisted"
                            )

                        # Cleanup
                        t2 = reopened_mdoc2.GetTitle
                        t2 = t2() if callable(t2) else t2
                        sw.CloseDoc(t2)
                        sw.CloseDoc(os.path.basename(part_path))
                    else:
                        result["datum_selected"] = False
                        result["reason"] = (
                            f"datum selection failed (sel_count={sel_count})"
                        )
                        result["gate2_result"] = "SKIP"
                except Exception as e:
                    result["datum_select_error"] = str(e)
                    result["gate2_result"] = "SKIP"
            else:
                result["reason"] = "no visible vertices"
                result["gate2_result"] = "SKIP"
        else:
            result["reason"] = "GetVisibleEntities failed or not iterable"
            result["gate2_result"] = "SKIP"

        # Cleanup if we didn't go through reopen path
        if "gate2_result" not in result:
            try:
                t = drw_mdoc2.GetTitle
                t = t() if callable(t) else t
                sw.CloseDoc(t)
                sw.CloseDoc(os.path.basename(part_path))
            except Exception:
                pass

    except Exception as e:
        result["error"] = str(e)
        import traceback

        result["traceback"] = traceback.format_exc()

    return result


def main() -> None:
    import win32com.client

    print("=== W31v S1: Ordinate/Baseline Re-probe ===\n")

    sw = win32com.client.Dispatch("SldWorks.Application")
    sw.Visible = True
    mod = wrapper_module()

    print("--- GATE 1: Selection Test ---")
    g1_result = test_gate1_selection(sw, mod)
    print(json.dumps(g1_result, indent=2, default=str))

    print("\n--- GATE 2: Ordinate Dimension Test ---")
    g2_result = test_gate2_ordinate_with_datum(sw, mod)
    print(json.dumps(g2_result, indent=2, default=str))

    # Write results
    results_path = Path(__file__).parent / "_results" / "ord_baseline.json"
    with open(results_path, "w") as f:
        json.dump(
            {
                "gate1": g1_result,
                "gate2_ordinate": g2_result,
            },
            f,
            indent=2,
            default=str,
        )

    print(f"\n=== Results: {results_path} ===")

    # Summary
    g1_pass = g1_result.get("gate1_result") == "PASS"
    g2_verdict = g2_result.get("verdict", "NO-GO")
    print(f"\nGate 1 (selection): {g1_result.get('gate1_result', 'UNKNOWN')}")
    print(f"Gate 2 (ordinate): {g2_verdict}")
    print(f"\nOVERALL: {'GREEN' if g1_pass and g2_verdict == 'GREEN' else 'NO-GO'}")


if __name__ == "__main__":
    main()
