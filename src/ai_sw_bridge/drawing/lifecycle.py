"""Drawing lifecycle — propose/dry_run/commit (Wave-16).

End-to-end ``propose → dry_run → commit`` for ``kind: "drawing"`` specs.

  - **propose**: validate offline (jsonschema + semantic).
  - **dry_run**: confirm model file exists and is openable.
  - **commit**: NewDocument(drwdot) → IDrawingDoc → per-view
    CreateDrawViewFromModelView3 → SaveAs3 .SLDDRW.
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
