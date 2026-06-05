"""Drawing lifecycle — propose/dry_run/commit (Wave-16/W18).

End-to-end ``propose → dry_run → commit`` for ``kind: "drawing"`` specs.

  - **propose**: validate offline (jsonschema + semantic).
  - **dry_run**: confirm model file exists and is openable.
  - **commit**: NewDocument(drwdot) → IDrawingDoc → per-view
    CreateDrawViewFromModelView3 → optional BOM (W18) → SaveAs3 .SLDDRW.
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
        write-only property") — not a usable getter in this context.
      - QI IBomTableAnnotation → IBomTable raises E_NOINTERFACE.
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

    for i, v in enumerate(views):
        if v not in DRAWING_FORMATS:
            raise ValueError(
                f"views[{i}]: unknown view {v!r}; "
                f"allowed: {sorted(DRAWING_FORMATS)}"
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
        model = spec.get("model", "")
        if not model.lower().endswith(".sldasm"):
            raise ValueError(
                "a BOM requires an assembly model; "
                "parts have no bill of materials "
                "(.sldprt does not support bom:true)"
            )


def dry_run_drawing(spec: dict[str, Any]) -> dict[str, Any]:
    """Dry-run a drawing spec — confirm model file exists.

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
    """Build the drawing — create views from the model, save .SLDDRW.

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

        views = spec.get("views", [])
        views_placed: list[str] = []
        view_errors: list[str] = []
        placed_views: list[Any] = []  # typed IView references

        for i, view_name in enumerate(views):
            fmt = resolve_format(view_name)
            x = fmt.default_x + (i * 0.001)  # tiny offset to avoid overlap
            y = fmt.default_y

            try:
                view = drawing_doc.CreateDrawViewFromModelView3(
                    model_path, fmt.view_name, x, y, 0.0
                )
                if view is not None and not isinstance(view, int):
                    views_placed.append(view_name)
                    placed_views.append(
                        typed_qi(view, "IView", module=mod)
                    )
                else:
                    view_errors.append(
                        f"{view_name}: CreateDrawViewFromModelView3 "
                        f"returned {view!r}"
                    )
            except Exception as exc:
                view_errors.append(f"{view_name}: {exc!r}")

        result["views_placed"] = views_placed
        result["view_count"] = len(views_placed)

        if view_errors:
            result["view_errors"] = view_errors

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

            # Fail-closed: verify at least one annotation was inserted
            # using the typed IView references we already hold.
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
            # Activate view — confirmed required for BOM insertion context (W18 S1)
            try:
                view_name = first_view.GetName2() or ""
                if view_name:
                    drawing_doc.ActivateView(view_name)
            except Exception:
                pass

            try:
                bom_annotation = first_view.InsertBomTable4(
                    False,  # UseAnchorPoint
                    0.05,   # X metres on sheet
                    0.22,   # Y metres on sheet
                    1,      # AnchorType = swTableAnchor_TopLeft
                    1,      # BomType = swBomType_TopLevelOnly
                    "",     # Configuration (default)
                    bom_tmpl,  # TableTemplate
                    False,  # Hidden
                    2,      # IndentedNumberingType = swIndentedNumberingType_None
                    False,  # DetailedCutList
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
                    "InsertBomTable4 returned None — BOM not placed "
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

        result["ok"] = len(view_errors) == 0
        if view_errors and not result.get("error"):
            result["error"] = (
                f"{len(view_errors)} view(s) failed: "
                f"{'; '.join(view_errors)}"
            )

        return result

    finally:
        # Close drawing doc
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
