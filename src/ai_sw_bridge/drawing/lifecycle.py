"""Drawing lifecycle — propose/dry_run/commit (Wave-16/W18/W19).

End-to-end ``propose -> dry_run -> commit`` for ``kind: "drawing"`` specs.

  - **propose**: validate offline (jsonschema + semantic).
  - **dry_run**: confirm model file exists and is openable.
  - **commit**: NewDocument(drwdot) -> IDrawingDoc -> ortho views first
    (CreateDrawViewFromModelView3), then derived views in order
    (section: CreateSectionViewAt5 / detail: CreateDetailViewAt4) ->
    optional dims (W17) -> optional BOM (W18) -> SaveAs3 .SLDDRW.
"""

from __future__ import annotations

import glob
import os
import time
from pathlib import Path
from typing import Any

from .formats import DRAWING_FORMATS, resolve_format
from .spec_schema import DEFAULT_SHEET_SIZE, SHEET_SIZES


def _find_drawing_template() -> str | None:
    """Locate the drawing template (.DRWDOT) on this machine."""
    patterns = [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.DRWDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\*.drwdot",
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return None


def _find_bom_template() -> str | None:
    """Locate a BOM table template (.sldbomtbt) on this machine."""
    patterns = [
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\bom-all.sldbomtbt",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english\*.sldbomtbt",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\**\*.sldbomtbt",
    ]
    for pat in patterns:
        matches = glob.glob(pat, recursive=True)
        if matches:
            return matches[0]
    return None


def _count_bom_data_rows(bom_annotation: Any) -> int:
    """Count data rows via IBomTableAnnotation.GetComponentsCount2 iterator.

    Row 0 is the header (count == 0). Data rows start at index 1.
    Returns the number of rows that have at least 1 component.

    Dead paths (characterised W18 S1):
      - IView.GetTableAnnotationCount() is always 0 for BOM tables.
      - IView.IGetBomTable() fails with SW error 61836 ("Unable to read
        write-only property") -- not a usable getter in this context.
      - QI IBomTableAnnotation -> IBomTable raises E_NOINTERFACE.
    """
    data_rows = 0
    for row_idx in range(1, 256):
        try:
            result = bom_annotation.GetComponentsCount2(row_idx, "")
            count = result[0] if isinstance(result, (list, tuple)) else result
            if not count:
                break
            data_rows += 1
        except Exception:
            break
    return data_rows


def _create_section_view(
    drawing_doc: Any,
    mdoc2: Any,
    parent_iview: Any,
    view_spec: dict[str, Any],
    typed_qi: Any,
    mod: Any,
) -> tuple[Any, str]:
    """Create a section view from a parent IView.

    Returns ``(typed_iview, sw_name)`` or raises on failure.
    Confirmed sigs (W19 S1): CreateLine(x1,y1,z1,x2,y2,z2),
    Select2(Append:BOOL, Mark:I4 must be int 0),
    CreateSectionViewAt5(X,Y,Z,SectionLabel,Options,ExcludedComponents,SectionDepth).
    """
    cut = view_spec.get("cut", "vertical")
    # SW section labels are single uppercase letters
    label = (view_spec.get("name") or "A")[0].upper()

    ol = parent_iview.GetOutline()  # [xmin, ymin, xmax, ymax] metres
    cx = (ol[0] + ol[2]) / 2.0
    cy = (ol[1] + ol[3]) / 2.0
    margin = 0.005  # 5 mm overshoot past bbox edge

    parent_name = parent_iview.GetName2() or ""
    drawing_doc.ActivateView(parent_name)
    skm = mdoc2.SketchManager

    if cut == "vertical":
        line = skm.CreateLine(cx, ol[1] - margin, 0.0, cx, ol[3] + margin, 0.0)
        sv_x = ol[2] + 0.06  # place section view to the right
        sv_y = cy
    else:  # horizontal
        line = skm.CreateLine(ol[0] - margin, cy, 0.0, ol[2] + margin, cy, 0.0)
        sv_x = cx
        sv_y = ol[3] + 0.06  # place section view above

    if line is None:
        raise RuntimeError("skm.CreateLine returned None")
    line.Select2(False, 0)

    sec_raw = drawing_doc.CreateSectionViewAt5(
        sv_x, sv_y, 0.0,
        label,  # SectionLabel
        0,      # Options
        None,   # ExcludedComponents (VARIANT None = no exclusions)
        0.0,    # SectionDepth
    )
    if sec_raw is None:
        raise RuntimeError("CreateSectionViewAt5 returned None")

    sec_view = typed_qi(sec_raw, "IView", module=mod)
    placed_name = sec_view.GetName2() or f"Section View {label}-{label}"
    return sec_view, placed_name


def _create_detail_view(
    drawing_doc: Any,
    mdoc2: Any,
    parent_iview: Any,
    view_spec: dict[str, Any],
    typed_qi: Any,
    mod: Any,
) -> tuple[Any, str]:
    """Create a detail view from a parent IView.

    Returns ``(typed_iview, sw_name)`` or raises on failure.
    Confirmed sigs (W19 S1): CreateCircleByRadius(XC,YC,ZC,Radius),
    Select2(Append:BOOL, Mark:I4 must be int 0),
    CreateDetailViewAt4 returns CDispatch -- typed_qi to IView required.
    """
    label = (view_spec.get("name") or "B")[0].upper()

    ol = parent_iview.GetOutline()  # [xmin, ymin, xmax, ymax] metres
    bbox_w = ol[2] - ol[0]
    bbox_h = ol[3] - ol[1]
    cy = (ol[1] + ol[3]) / 2.0

    # center: [cx_frac, cy_frac] in [0,1] x [0,1] relative to parent bbox
    center_frac = view_spec.get("center") or [0.5, 0.5]
    det_cx = ol[0] + float(center_frac[0]) * bbox_w
    det_cy = ol[1] + float(center_frac[1]) * bbox_h

    # radius: fraction of the shorter bbox dimension
    radius_frac = view_spec.get("radius") or 0.25
    det_r = float(radius_frac) * min(bbox_w, bbox_h)

    # Place detail view to the right of parent
    det_x = ol[2] + 0.06
    det_y = cy

    parent_name = parent_iview.GetName2() or ""
    drawing_doc.ActivateView(parent_name)
    skm = mdoc2.SketchManager

    circle = skm.CreateCircleByRadius(det_cx, det_cy, 0.0, det_r)
    if circle is None:
        raise RuntimeError("skm.CreateCircleByRadius returned None")
    circle.Select2(False, 0)

    det_raw = drawing_doc.CreateDetailViewAt4(
        det_x, det_y, 0.0,
        0,     # Style = swDetailViewStyle_PerStandard
        2.0,   # Scale1
        1.0,   # Scale2
        label, # LabelIn
        0,     # Showtype
        True,  # FullOutline
        False, # JaggedOutline
        False, # NoOutline
        50,    # ShapeIntensity
    )
    if det_raw is None:
        raise RuntimeError("CreateDetailViewAt4 returned None")

    # CreateDetailViewAt4 returns CDispatch, not IView -- QI required (W19 S1)
    det_view = typed_qi(det_raw, "IView", module=mod)
    placed_name = det_view.GetName2() or f"Detail View {label}"
    return det_view, placed_name


def validate_drawing_spec(spec: dict[str, Any]) -> None:
    """Semantic validation beyond the structural JSON-schema check.

    Raises ``ValueError`` on the first semantic error found.
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")
    if spec.get("kind") != "drawing":
        raise ValueError("spec kind must be 'drawing'")

    name = spec.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")

    model = spec.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("model must be a non-empty string")

    views = spec.get("views")
    if not isinstance(views, list) or not views:
        raise ValueError("views must be a non-empty array")

    # Track string view names seen so far for parent-reference validation.
    # Derived views may only reference earlier ortho/iso string entries.
    seen_string_views: set[str] = set()

    for i, v in enumerate(views):
        if isinstance(v, str):
            if v not in DRAWING_FORMATS:
                raise ValueError(
                    f"views[{i}]: unknown view {v!r}; "
                    f"allowed: {sorted(DRAWING_FORMATS)}"
                )
            seen_string_views.add(v)
        elif isinstance(v, dict):
            vtype = v.get("type")
            if vtype not in ("section", "detail"):
                raise ValueError(
                    f"views[{i}]: object entry type must be 'section' or 'detail'"
                )
            vname = v.get("name")
            if not isinstance(vname, str) or not vname:
                raise ValueError(f"views[{i}]: name must be a non-empty string")
            parent = v.get("parent")
            if not isinstance(parent, str) or not parent:
                raise ValueError(f"views[{i}]: parent must be a non-empty string")
            if parent not in seen_string_views:
                raise ValueError(
                    f"views[{i}]: parent {parent!r} must be an earlier "
                    f"ortho/iso string view (seen so far: "
                    f"{sorted(seen_string_views) or 'none'})"
                )
            if vtype == "section":
                cut = v.get("cut")
                if cut not in ("horizontal", "vertical"):
                    raise ValueError(
                        f"views[{i}]: section view requires "
                        f"cut: 'horizontal' or 'vertical'"
                    )
            if vtype == "detail":
                center = v.get("center")
                if center is not None:
                    if not (isinstance(center, list) and len(center) == 2):
                        raise ValueError(
                            f"views[{i}]: detail center must be "
                            f"[cx_frac, cy_frac] (two numbers)"
                        )
                radius = v.get("radius")
                if radius is not None and not (
                    isinstance(radius, (int, float)) and radius > 0
                ):
                    raise ValueError(
                        f"views[{i}]: detail radius must be a positive number"
                    )
        else:
            raise ValueError(
                f"views[{i}]: each entry must be a string or object, "
                f"got {type(v).__name__}"
            )

    sheet = spec.get("sheet")
    if sheet is not None:
        if not isinstance(sheet, dict):
            raise ValueError("sheet must be a dict")
        ts = sheet.get("template_size")
        if ts is not None and ts not in SHEET_SIZES:
            raise ValueError(
                f"sheet.template_size {ts!r} not in {sorted(SHEET_SIZES)}"
            )

    bom = spec.get("bom")
    if bom is not None and not isinstance(bom, bool):
        raise ValueError("bom must be a boolean")
    if bom:
        if not model.lower().endswith(".sldasm"):
            raise ValueError(
                "a BOM requires an assembly model; "
                "parts have no bill of materials "
                "(.sldprt does not support bom:true)"
            )


def dry_run_drawing(spec: dict[str, Any]) -> dict[str, Any]:
    """Dry-run a drawing spec -- confirm model file exists.

    Returns a result dict with ``ok``, ``model_path``, and ``error``.
    """
    result: dict[str, Any] = {"ok": False}

    model_path = spec.get("model", "")
    if not os.path.isfile(model_path):
        result["error"] = f"model file not found: {model_path}"
        return result

    result["model_path"] = model_path
    result["views_requested"] = spec.get("views", [])
    result["ok"] = True
    return result


def commit_drawing(
    sw: Any,
    spec: dict[str, Any],
    output_path: str,
    *,
    mod: Any | None = None,
) -> dict[str, Any]:
    """Build the drawing -- create views from the model, save .SLDDRW.

    Two-pass view strategy (W19):
      Pass 1 -- ortho/iso string entries: CreateDrawViewFromModelView3,
                builds ``placed_by_name`` dict for parent lookup.
      Pass 2 -- derived object entries in spec order: section views via
                CreateSectionViewAt5, detail views via CreateDetailViewAt4.

    Args:
        sw: the ``SldWorks.Application`` COM object.
        spec: the validated drawing spec dict.
        output_path: where to save the ``.slddrw`` file.
        mod: the gen_py wrapper module.

    Returns:
        A result dict with ``ok``, ``view_count``, ``views_placed``,
        and ``error``.
    """
    from ..com.earlybind import typed, typed_qi
    from ..com.sw_type_info import wrapper_module

    if mod is None:
        mod = wrapper_module()

    result: dict[str, Any] = {"ok": False}

    model_path = spec.get("model", "")
    if not os.path.isfile(model_path):
        result["error"] = f"model file not found: {model_path}"
        return result

    # Find template
    template = _find_drawing_template()
    if template is None:
        result["error"] = "drawing template (.DRWDOT) not found"
        return result

    # Sheet dimensions
    sheet = spec.get("sheet", {})
    size_name = sheet.get("template_size", DEFAULT_SHEET_SIZE)
    width_m, height_m = SHEET_SIZES.get(size_name, SHEET_SIZES[DEFAULT_SHEET_SIZE])

    # Open the model document (required for view creation)
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        ext = os.path.splitext(model_path)[1].lower()
        doc_type = 2 if ext in (".sldasm",) else 1  # assembly vs part
        tsw.OpenDoc6(model_path, doc_type, 1, "", 0, 0)
    except Exception as exc:
        result["error"] = f"OpenDoc6 failed: {exc!r}"
        return result

    # Create drawing document
    try:
        doc_raw = sw.NewDocument(template, 0, width_m, height_m)
    except Exception as exc:
        result["error"] = f"NewDocument(drwdot) failed: {exc!r}"
        return result

    if doc_raw is None or isinstance(doc_raw, int):
        result["error"] = "NewDocument(drwdot) returned None"
        return result

    try:
        drawing_doc = typed_qi(doc_raw, "IDrawingDoc", module=mod)
        # IDrawingDoc does not inherit IModelDoc2 in the typelib --
        # SketchManager must be accessed via a separate IModelDoc2 QI (W19 S1)
        mdoc2 = typed_qi(doc_raw, "IModelDoc2", module=mod)

        views = spec.get("views", [])
        views_placed: list[str] = []
        view_errors: list[str] = []
        placed_views: list[Any] = []         # all typed IView refs (ortho + derived)
        placed_by_name: dict[str, Any] = {}  # string_view_name -> typed IView

        # ------------------------------------------------------------------
        # Pass 1: ortho/iso string views
        # ------------------------------------------------------------------
        ortho_indices: list[int] = []
        derived_indices: list[int] = []
        for i, v in enumerate(views):
            if isinstance(v, str):
                ortho_indices.append(i)
            else:
                derived_indices.append(i)

        for i in ortho_indices:
            view_entry = views[i]
            fmt = resolve_format(view_entry)
            x = fmt.default_x + (i * 0.001)
            y = fmt.default_y

            try:
                view_raw = drawing_doc.CreateDrawViewFromModelView3(
                    model_path, fmt.view_name, x, y, 0.0
                )
                if view_raw is not None and not isinstance(view_raw, int):
                    tview = typed_qi(view_raw, "IView", module=mod)
                    views_placed.append(view_entry)
                    placed_views.append(tview)
                    placed_by_name[view_entry] = tview
                else:
                    view_errors.append(
                        f"{view_entry}: CreateDrawViewFromModelView3 "
                        f"returned {view_raw!r}"
                    )
            except Exception as exc:
                view_errors.append(f"{view_entry}: {exc!r}")

        # ------------------------------------------------------------------
        # Pass 2: derived views (section / detail) in spec order
        # ------------------------------------------------------------------
        for i in derived_indices:
            vspec = views[i]
            vtype = vspec.get("type")
            vname = vspec.get("name", "")
            parent_key = vspec.get("parent", "")
            parent_iview = placed_by_name.get(parent_key)

            if parent_iview is None:
                view_errors.append(
                    f"views[{i}] ({vtype} '{vname}'): "
                    f"parent view '{parent_key}' was not placed"
                )
                continue

            try:
                if vtype == "section":
                    tview, placed_name = _create_section_view(
                        drawing_doc, mdoc2, parent_iview, vspec, typed_qi, mod
                    )
                else:  # detail
                    tview, placed_name = _create_detail_view(
                        drawing_doc, mdoc2, parent_iview, vspec, typed_qi, mod
                    )
                views_placed.append(placed_name)
                placed_views.append(tview)
            except Exception as exc:
                view_errors.append(
                    f"views[{i}] ({vtype} '{vname}'): {exc!r}"
                )

        result["views_placed"] = views_placed
        result["view_count"] = len(views_placed)

        if view_errors:
            result["view_errors"] = view_errors
            # Fail-closed (W20 hardening): a declarative drawing spec names an
            # EXACT set of views. If ANY requested view (ortho OR derived)
            # failed to materialise, abort BEFORE dims / BOM / SaveAs3 rather
            # than writing a partial .SLDDRW to disk — parity with the W17 dims
            # / W18 BOM hard-return posture and the W9/W11 assembly fail-closed
            # invariant. The validator blocks every structural error at
            # propose-time, so a commit-time view error is a live COM failure
            # that must fail the commit, not silently degrade the output.
            result["error"] = (
                f"{len(view_errors)} requested view(s) could not be created; "
                f"no drawing was saved: {'; '.join(view_errors)}"
            )
            return result

        # Insert model dimensions if requested (W17)
        insert_dims = spec.get("dimensions", False)
        if insert_dims and views_placed:
            try:
                drawing_doc.InsertModelAnnotations3(
                    0, -1, True, False, True, 0
                )
                result["dimensions_inserted"] = True
            except Exception as exc:
                result["dimensions_inserted"] = False
                result["error"] = (
                    f"InsertModelAnnotations3 failed: {exc!r}"
                )
                return result

            total_annotations = 0
            for v in placed_views:
                try:
                    ac = v.GetAnnotationCount()
                    total_annotations += ac if ac else 0
                except Exception:
                    pass
            result["total_annotations"] = total_annotations
            if total_annotations == 0:
                result["error"] = (
                    "dimensions: true but zero annotations inserted "
                    "(model may have been built with no_dim=True; "
                    "rebuild with no_dim=False for dimensioned output)"
                )
                return result

        # Insert BOM if requested (W18)
        insert_bom = spec.get("bom", False)
        if insert_bom and views_placed and placed_views:
            bom_tmpl = _find_bom_template()
            if bom_tmpl is None:
                result["error"] = (
                    "bom: true but no BOM template (.sldbomtbt) found; "
                    "expected under "
                    "C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\lang\\english\\"
                )
                return result

            first_view = placed_views[0]
            try:
                vn = first_view.GetName2() or ""
                if vn:
                    drawing_doc.ActivateView(vn)
            except Exception:
                pass

            try:
                bom_annotation = first_view.InsertBomTable4(
                    False,    # UseAnchorPoint
                    0.05,     # X metres on sheet
                    0.22,     # Y metres on sheet
                    1,        # AnchorType = swTableAnchor_TopLeft
                    1,        # BomType = swBomType_TopLevelOnly
                    "",       # Configuration (default)
                    bom_tmpl, # TableTemplate
                    False,    # Hidden
                    2,        # IndentedNumberingType = swIndentedNumberingType_None
                    False,    # DetailedCutList
                )
            except Exception as exc:
                result["error"] = f"BOM InsertBomTable4 failed: {exc!r}"
                return result

            bom_ok = (
                bom_annotation is not None
                and not isinstance(bom_annotation, int)
            )
            if not bom_ok:
                result["error"] = (
                    "InsertBomTable4 returned None -- BOM not placed "
                    "(assembly may have no components in this view context)"
                )
                return result

            data_rows = _count_bom_data_rows(bom_annotation)
            result["bom_data_rows"] = data_rows
            if data_rows == 0:
                result["error"] = (
                    "bom: true but the BOM table has zero data rows "
                    "(model has no visible components in the drawing view)"
                )
                return result

            result["bom_inserted"] = True

        # Save the drawing
        try:
            doc_raw.SaveAs3(output_path, 0, 2)
            result["save_path"] = output_path
        except Exception as exc:
            result["error"] = f"SaveAs3 failed: {exc!r}"
            return result

        # view_errors is guaranteed empty here: the fail-closed guard after
        # Pass 2 returns early on any view failure (W20 hardening), so reaching
        # this point means every requested view materialised.
        result["ok"] = True
        return result

    finally:
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
