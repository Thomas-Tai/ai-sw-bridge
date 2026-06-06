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


def _validate_views_array(
    views: list[Any],
    *,
    path_prefix: str,
) -> None:
    """Validate one views[] array (shared between legacy + per-sheet modes).

    Raises ``ValueError`` on the first semantic error found.

    ``path_prefix`` is the dotted path used in error messages (``"views"`` for
    legacy mode, ``"sheets[k].views"`` for multi-sheet mode) so the caller's
    position in the spec is obvious from the message alone.
    """
    if not isinstance(views, list) or not views:
        raise ValueError(f"{path_prefix} must be a non-empty array")

    seen_string_views: set[str] = set()
    for i, v in enumerate(views):
        if isinstance(v, str):
            if v not in DRAWING_FORMATS:
                raise ValueError(
                    f"{path_prefix}[{i}]: unknown view {v!r}; "
                    f"allowed: {sorted(DRAWING_FORMATS)}"
                )
            seen_string_views.add(v)
        elif isinstance(v, dict):
            vtype = v.get("type")
            if vtype not in ("section", "detail"):
                raise ValueError(
                    f"{path_prefix}[{i}]: object entry type must be "
                    f"'section' or 'detail'"
                )
            vname = v.get("name")
            if not isinstance(vname, str) or not vname:
                raise ValueError(
                    f"{path_prefix}[{i}]: name must be a non-empty string"
                )
            parent = v.get("parent")
            if not isinstance(parent, str) or not parent:
                raise ValueError(
                    f"{path_prefix}[{i}]: parent must be a non-empty string"
                )
            if parent not in seen_string_views:
                raise ValueError(
                    f"{path_prefix}[{i}]: parent {parent!r} must be an earlier "
                    f"ortho/iso string view within the same sheet "
                    f"(seen so far: {sorted(seen_string_views) or 'none'})"
                )
            if vtype == "section":
                cut = v.get("cut")
                if cut not in ("horizontal", "vertical"):
                    raise ValueError(
                        f"{path_prefix}[{i}]: section view requires "
                        f"cut: 'horizontal' or 'vertical'"
                    )
            if vtype == "detail":
                center = v.get("center")
                if center is not None:
                    if not (isinstance(center, list) and len(center) == 2):
                        raise ValueError(
                            f"{path_prefix}[{i}]: detail center must be "
                            f"[cx_frac, cy_frac] (two numbers)"
                        )
                radius = v.get("radius")
                if radius is not None and not (
                    isinstance(radius, (int, float)) and radius > 0
                ):
                    raise ValueError(
                        f"{path_prefix}[{i}]: detail radius must be a "
                        f"positive number"
                    )
        else:
            raise ValueError(
                f"{path_prefix}[{i}]: each entry must be a string or object, "
                f"got {type(v).__name__}"
            )


def _validate_bom_for_model(bom: Any, model: str, *, path: str) -> None:
    """bom:true requires a .sldasm model (shared between legacy + per-sheet)."""
    if bom is not None and not isinstance(bom, bool):
        raise ValueError(f"{path} must be a boolean")
    if bom:
        if not model.lower().endswith(".sldasm"):
            raise ValueError(
                "a BOM requires an assembly model; "
                "parts have no bill of materials "
                f"(.sldprt does not support {path}:true)"
            )


def validate_drawing_spec(spec: dict[str, Any]) -> None:
    """Semantic validation beyond the structural JSON-schema check.

    Two authoring modes (W23):

      - **Legacy**: top-level ``views`` (with optional ``sheet``/``dimensions``/
        ``bom``). Unchanged behaviour from pre-W23.
      - **Multi-sheet**: ``sheets[]`` array; each entry carries its own
        ``views`` (plus optional ``name``/``template_size``/``dimensions``/
        ``bom``). Top-level ``views``/``sheet``/``dimensions`` MUST be absent.

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

    has_views = "views" in spec
    has_sheets = "sheets" in spec

    if has_views and has_sheets:
        raise ValueError(
            "views and sheets are mutually exclusive — "
            "use top-level views (legacy single-sheet mode) "
            "OR sheets[] (multi-sheet mode), not both"
        )
    if not has_views and not has_sheets:
        raise ValueError(
            "spec must declare views (legacy mode) or sheets (multi-sheet mode)"
        )

    if has_sheets:
        # --- multi-sheet mode ---
        if spec.get("sheet") is not None:
            raise ValueError(
                "sheet (legacy single-sheet template) is not allowed "
                "with sheets[]; set template_size on each sheet entry"
            )
        if spec.get("dimensions") is not None:
            raise ValueError(
                "top-level dimensions is not allowed with sheets[]; "
                "set dimensions on each sheet entry"
            )
        if spec.get("bom") is not None:
            raise ValueError(
                "top-level bom is not allowed with sheets[]; "
                "set bom on each sheet entry"
            )

        sheets = spec.get("sheets")
        if not isinstance(sheets, list) or not sheets:
            raise ValueError("sheets must be a non-empty array")

        seen_names: set[str] = set()
        for k, sh in enumerate(sheets):
            if not isinstance(sh, dict):
                raise ValueError(f"sheets[{k}] must be a dict")
            sh_name = sh.get("name")
            if sh_name is not None:
                if not isinstance(sh_name, str) or not sh_name:
                    raise ValueError(
                        f"sheets[{k}].name must be a non-empty string"
                    )
                if sh_name in seen_names:
                    raise ValueError(
                        f"sheets[{k}].name {sh_name!r} duplicates an "
                        f"earlier sheet name"
                    )
                seen_names.add(sh_name)
            ts = sh.get("template_size")
            if ts is not None and ts not in SHEET_SIZES:
                raise ValueError(
                    f"sheets[{k}].template_size {ts!r} not in "
                    f"{sorted(SHEET_SIZES)}"
                )
            _validate_views_array(
                sh.get("views", []), path_prefix=f"sheets[{k}].views"
            )
            _validate_bom_for_model(
                sh.get("bom"), model, path=f"sheets[{k}].bom"
            )
        return

    # --- legacy single-sheet mode ---
    views = spec.get("views", [])
    _validate_views_array(views, path_prefix="views")

    sheet = spec.get("sheet")
    if sheet is not None:
        if not isinstance(sheet, dict):
            raise ValueError("sheet must be a dict")
        ts = sheet.get("template_size")
        if ts is not None and ts not in SHEET_SIZES:
            raise ValueError(
                f"sheet.template_size {ts!r} not in {sorted(SHEET_SIZES)}"
            )

    _validate_bom_for_model(spec.get("bom"), model, path="bom")


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
    if "sheets" in spec:
        result["sheets_requested"] = len(spec["sheets"])
        result["views_per_sheet"] = [
            len(sh.get("views", [])) for sh in spec["sheets"]
        ]
    else:
        result["views_requested"] = spec.get("views", [])
    result["ok"] = True
    return result


def _normalize_sheets(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert either authoring mode to a uniform list of per-sheet specs.

    Legacy mode (``views`` at top level) -> one-element list that carries the
    top-level ``sheet``/``dimensions``/``bom`` onto a single synthesized sheet.

    Multi-sheet mode (``sheets[]``) -> the array verbatim.

    The returned dicts all have the same shape:
    ``{name, template_size, views, dimensions, bom}`` with defaults filled in.
    ``name`` is ``None`` for "use whatever the default sheet is called".

    W28: ``dimensions`` can be bool or object (with tolerance sub-object).
    ``bool(dimensions)`` returns True for both, so we preserve the raw value.
    """
    if "sheets" in spec:
        out: list[dict[str, Any]] = []
        for sh in spec["sheets"]:
            dims_raw = sh.get("dimensions", False)
            out.append(
                {
                    "name": sh.get("name"),
                    "template_size": sh.get("template_size"),
                    "views": sh.get("views", []),
                    "dimensions": dims_raw,  # Preserve bool OR object (W28)
                    "bom": bool(sh.get("bom", False)),
                }
            )
        return out

    sheet = spec.get("sheet") or {}
    dims_raw = spec.get("dimensions", False)
    return [
        {
            "name": None,
            "template_size": sheet.get("template_size"),
            "views": spec.get("views", []),
            "dimensions": dims_raw,  # Preserve bool OR object (W28)
            "bom": bool(spec.get("bom", False)),
        }
    ]


# swDwgPaperSizes_e (subset used by the drawing spec schema).
_PAPER_SIZE_ENUM: dict[str, int] = {
    "A4": 8,
    "A3": 11,
    "A2": 12,
    "A1": 13,
    "A0": 14,
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
}

# swDwgTemplates_e: 1 = swDwgTemplateCustom (caller supplies Width/Height).
_TEMPLATE_CUSTOM = 1


def _retemplate_first_sheet(
    drawing_doc: Any,
    width_m: float,
    height_m: float,
    template_size_name: str | None,
) -> None:
    """Resize Sheet1 (the sheet NewDocument created) to the requested size.

    Uses ``ISheet.SetProperties2`` (8 args, makepy-authoritative) on the
    active sheet. The default sheet already exists when we enter this
    function -- we just retarget its size. If ``template_size_name`` is
    ``None`` we leave the sheet at the size NewDocument gave it.
    """
    if template_size_name is None:
        return
    paper_enum = _PAPER_SIZE_ENUM.get(template_size_name)
    sheet_raw = drawing_doc.GetCurrentSheet()
    if sheet_raw is None or isinstance(sheet_raw, int):
        return
    from ..com.earlybind import typed_qi
    from ..com.sw_type_info import wrapper_module
    sheet = typed_qi(sheet_raw, "ISheet", module=wrapper_module())
    try:
        sheet.SetProperties2(
            paper_enum if paper_enum is not None else 0,  # PaperSz (I4)
            _TEMPLATE_CUSTOM,                           # Templ (I4)
            1.0,                                        # Scale1 (R8)
            1.0,                                        # Scale2 (R8)
            True,                                       # FirstAngle (BOOL)
            width_m,                                    # Width (R8, metres)
            height_m,                                   # Height (R8, metres)
            False,                                      # SameCustomPropAsSheetInDocProp (BOOL)
        )
    except Exception:
        # Retemplate is best-effort: the sheet size the user asked for may
        # not be supported by their template, but the views still land on it.
        pass


def _activate_sheet_by_name(drawing_doc: Any, sheet_name: str) -> None:
    """Activate a sheet by name before placing views on it.

    Per-sheet view routing (W23) depends on ActivateSheet being called
    BEFORE CreateDrawViewFromModelView3 / InsertModelAnnotations3 /
    InsertBomTable4 -- otherwise the view silently lands on whichever sheet
    happens to be active (the same trap as W18's per-view ActivateView).
    """
    ok = drawing_doc.ActivateSheet(sheet_name)
    if not ok:
        raise RuntimeError(
            f"ActivateSheet({sheet_name!r}) returned False; "
            f"subsequent views would land on the wrong sheet"
        )


# W28: swTolType_e values (confirmed by spike_drawing_tol.py)
_SW_TOL_SYMMETRIC = 4
_SW_TOL_BILATERAL = 2
_SW_TOL_LIMIT = 3


def _apply_tolerance_to_dims(
    views: list[Any],
    tolerance_spec: dict[str, Any],
    model_mdoc2: Any,
    mod: Any,
    typed_qi: Any,
    sheet_index: int,
) -> dict[str, Any]:
    """Apply a general tolerance to all display dimensions on the given views.

    W28: Tolerances are MODEL-OWNED. Setting tolerance on a drawing's
    IDimension (via GetDimension2) affects the PART/ASM's underlying dimension.
    The caller must save the MODEL after this function returns.

    Args:
        views: list of IView objects that have display dimensions
        tolerance_spec: {type, value|max, min} dict from the spec
        model_mdoc2: IModelDoc2 of the PART/ASM (for EditRebuild3)
        mod: gen_py wrapper module
        typed_qi: typed_qi function
        sheet_index: for error messages

    Returns:
        dict with dims_processed, tolerance_applied, errors
    """
    tol_type_str = tolerance_spec.get("type", "")
    if tol_type_str not in ("symmetric", "bilateral", "limit"):
        return {
            "dims_processed": 0,
            "tolerance_applied": False,
            "errors": [f"unsupported tolerance type '{tol_type_str}'"],
        }

    # Map string type to swTolType_e
    sw_tol_type = {
        "symmetric": _SW_TOL_SYMMETRIC,
        "bilateral": _SW_TOL_BILATERAL,
        "limit": _SW_TOL_LIMIT,
    }[tol_type_str]

    # Extract tolerance values (in metres, SW system units)
    tol_min = 0.0
    tol_max = 0.0
    if tol_type_str == "symmetric":
        value = tolerance_spec.get("value", 0)
        if value < 0:
            return {
                "dims_processed": 0,
                "tolerance_applied": False,
                "errors": [f"symmetric tolerance value must be >= 0 (got {value})"],
            }
        tol_min = -value
        tol_max = value
    else:  # bilateral or limit
        tol_max = tolerance_spec.get("max", 0)
        tol_min = tolerance_spec.get("min", 0)

    dims_processed = 0
    tolerance_applied_count = 0
    errors: list[str] = []

    for view in views:
        try:
            disp_dims = view.GetDisplayDimensions()
        except Exception:
            continue

        if not disp_dims:
            continue

        for dd_raw in disp_dims:
            if dd_raw is None:
                continue
            try:
                dd = typed_qi(dd_raw, "IDisplayDimension", module=mod)
            except Exception:
                continue

            try:
                dim_raw = dd.GetDimension2(0)
            except Exception:
                continue

            if dim_raw is None:
                continue

            try:
                dim = typed_qi(dim_raw, "IDimension", module=mod)
            except Exception:
                continue

            dims_processed += 1

            try:
                dim.SetToleranceType(sw_tol_type)
                dim.SetToleranceValues(tol_min, tol_max)
                tolerance_applied_count += 1
            except Exception as e:
                dim_name = ""
                try:
                    dim_name = dim.FullName
                except Exception:
                    pass
                errors.append(
                    f"sheet[{sheet_index}] dim '{dim_name}': "
                    f"SetToleranceValues failed: {e!r}"
                )

    return {
        "dims_processed": dims_processed,
        "tolerance_applied": tolerance_applied_count > 0,
        "tolerance_applied_count": tolerance_applied_count,
        "errors": errors,
    }


def _build_sheet_views(
    drawing_doc: Any,
    mdoc2: Any,
    sheet_spec: dict[str, Any],
    model_path: str,
    *,
    sheet_index: int,
    is_first: bool,
    mod: Any,
    typed_qi: Any,
    model_mdoc2: Any | None = None,
) -> dict[str, Any]:
    """Build one sheet's views/dims/bom. Returns a per-sheet result dict.

    Fail-closed on any view failure: the caller aggregates errors and aborts
    SaveAs3 if any sheet reports ``view_errors``. Dimensions and BOM are only
    attempted when all views on the sheet materialised.

    W28: ``dimensions`` can be bool or object with tolerance. When tolerance
    is specified, we apply it to all dims via the model_mdoc2 (tolerances are
    MODEL-OWNED, so the model must be saved after this returns).
    """
    from ..com.earlybind import typed_qi as _tq  # noqa: F401 (kept for clarity)

    result: dict[str, Any] = {
        "sheet_index": sheet_index,
        "sheet_name": sheet_spec.get("name"),
        "views_placed": [],
        "view_count": 0,
        "view_errors": [],
    }

    views = sheet_spec.get("views", [])
    views_placed: list[str] = []
    placed_views: list[Any] = []
    placed_by_name: dict[str, Any] = {}
    view_errors: list[str] = []

    # ------------------------------------------------------------------
    # Pass 1: ortho/iso string views
    # ------------------------------------------------------------------
    ortho_indices = [i for i, v in enumerate(views) if isinstance(v, str)]
    derived_indices = [i for i, v in enumerate(views) if not isinstance(v, str)]

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
                    f"sheet[{sheet_index}].{view_entry}: "
                    f"CreateDrawViewFromModelView3 returned {view_raw!r}"
                )
        except Exception as exc:
            view_errors.append(f"sheet[{sheet_index}].{view_entry}: {exc!r}")

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
                f"sheet[{sheet_index}].views[{i}] ({vtype} '{vname}'): "
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
                f"sheet[{sheet_index}].views[{i}] ({vtype} '{vname}'): "
                f"{exc!r}"
            )

    result["views_placed"] = views_placed
    result["view_count"] = len(views_placed)
    result["view_errors"] = view_errors

    if view_errors:
        return result

    # ------------------------------------------------------------------
    # Dimensions (per-sheet) — W28: bool or object with tolerance
    # ------------------------------------------------------------------
    dims_spec = sheet_spec.get("dimensions")
    if dims_spec and views_placed:
        # W28: dims_spec can be bool (true/false) or object {tolerance: {...}}
        has_tolerance = isinstance(dims_spec, dict) and "tolerance" in dims_spec
        tolerance_spec = dims_spec.get("tolerance") if has_tolerance else None

        try:
            drawing_doc.InsertModelAnnotations3(0, -1, True, False, True, 0)
            result["dimensions_inserted"] = True
        except Exception as exc:
            result["dimensions_inserted"] = False
            result["view_errors"].append(
                f"sheet[{sheet_index}].dimensions: "
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
            result["view_errors"].append(
                f"sheet[{sheet_index}].dimensions: "
                f"dimensions:true but zero annotations inserted"
            )
            return result

        # W28: Apply tolerance if specified
        if has_tolerance and tolerance_spec and model_mdoc2 is not None:
            tol_result = _apply_tolerance_to_dims(
                placed_views,
                tolerance_spec,
                model_mdoc2,
                mod,
                typed_qi,
                sheet_index,
            )
            result["tolerance_result"] = tol_result
            if tol_result.get("errors"):
                result["view_errors"].extend(tol_result["errors"])
                return result
            result["tolerance_applied"] = tol_result.get("tolerance_applied", False)
            result["dims_with_tolerance"] = tol_result.get("tolerance_applied_count", 0)
        elif has_tolerance and model_mdoc2 is None:
            result["view_errors"].append(
                f"sheet[{sheet_index}].dimensions.tolerance: "
                f"tolerance specified but model doc not available"
            )
            return result

    # ------------------------------------------------------------------
    # BOM (per-sheet; requires .sldasm -- validated upstream)
    # ------------------------------------------------------------------
    if sheet_spec.get("bom") and views_placed and placed_views:
        bom_tmpl = _find_bom_template()
        if bom_tmpl is None:
            result["view_errors"].append(
                f"sheet[{sheet_index}].bom: bom:true but no BOM template "
                f"(.sldbomtbt) found under "
                f"C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\lang\\english\\"
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
                False, 0.05, 0.22, 1, 1, "", bom_tmpl, False, 2, False,
            )
        except Exception as exc:
            result["view_errors"].append(
                f"sheet[{sheet_index}].bom: InsertBomTable4 failed: {exc!r}"
            )
            return result

        bom_ok = (
            bom_annotation is not None
            and not isinstance(bom_annotation, int)
        )
        if not bom_ok:
            result["view_errors"].append(
                f"sheet[{sheet_index}].bom: InsertBomTable4 returned None"
            )
            return result

        data_rows = _count_bom_data_rows(bom_annotation)
        result["bom_data_rows"] = data_rows
        if data_rows == 0:
            result["view_errors"].append(
                f"sheet[{sheet_index}].bom: zero data rows "
                f"(assembly has no visible components in this view)"
            )
            return result
        result["bom_inserted"] = True

    return result


def commit_drawing(
    sw: Any,
    spec: dict[str, Any],
    output_path: str,
    *,
    mod: Any | None = None,
) -> dict[str, Any]:
    """Build the drawing -- create views from the model, save .SLDDRW.

    Two authoring modes (W23):

      - **Legacy**: top-level ``views`` -> normalised to a single sheet;
        behaviour unchanged from pre-W23.
      - **Multi-sheet**: ``sheets[]`` array -> one sheet per entry; sheet 1
        reuses the default sheet NewDocument created (renamed + retemplated);
        sheets 2..N added via ``IDrawingDoc.NewSheet3(name, template_in,
        paper_size, scale1, scale2, first_angle)`` then
        ``ActivateSheet(name)`` before every view/dim/bom call so the view
        provably lands on the intended sheet.

    Fail-closed (W20/W21): ANY sheet or view failure aborts BEFORE dims /
    BOM / SaveAs3 -- no partial .SLDDRW is written to disk.

    Args:
        sw: the ``SldWorks.Application`` COM object.
        spec: the validated drawing spec dict.
        output_path: where to save the ``.slddrw`` file.
        mod: the gen_py wrapper module.

    Returns:
        A result dict with ``ok``, ``sheet_count``, per-sheet
        ``sheets`` details, aggregated ``view_count`` / ``views_placed``,
        and ``error`` on failure.
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

    # Resolve per-sheet layout from either authoring mode
    sheet_specs = _normalize_sheets(spec)

    # Sheet-1 dimensions (for NewDocument + fallback retemplate of sheet 1)
    first_size_name = sheet_specs[0].get("template_size") or DEFAULT_SHEET_SIZE
    width_m, height_m = SHEET_SIZES.get(
        first_size_name, SHEET_SIZES[DEFAULT_SHEET_SIZE]
    )

    # Open the model document (required for view creation AND W28 tolerance)
    # W28: tolerance is MODEL-OWNED, so we need the model doc to save it
    model_doc = None
    model_mdoc2 = None
    try:
        tsw = typed(sw, "ISldWorks", module=mod)
        ext = os.path.splitext(model_path)[1].lower()
        doc_type = 2 if ext in (".sldasm",) else 1  # assembly vs part
        ret = tsw.OpenDoc6(model_path, doc_type, 1, "", 0, 0)
        model_doc = ret[0] if isinstance(ret, tuple) else ret
        if model_doc is not None:
            model_mdoc2 = typed_qi(model_doc, "IModelDoc2", module=mod)
    except Exception as exc:
        result["error"] = f"OpenDoc6 failed: {exc!r}"
        return result

    # Create drawing document (default sheet 1 is created here)
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
        mdoc2 = typed_qi(doc_raw, "IModelDoc2", module=mod)

        # Resize default sheet if sheet 1 asked for a non-default size
        _retemplate_first_sheet(drawing_doc, width_m, height_m, first_size_name)

        per_sheet_results: list[dict[str, Any]] = []
        all_views_placed: list[str] = []
        total_view_count = 0
        all_errors: list[str] = []
        sheet_names_created: list[str] = []

        for idx, sheet_spec in enumerate(sheet_specs):
            is_first = idx == 0

            # ----------------------------------------------------------
            # Create additional sheets via NewSheet3 (W23 S1 recipe,
            # 10-arg makepy-authoritative signature)
            # ----------------------------------------------------------
            if not is_first:
                requested_name = sheet_spec.get("name") or f"Sheet{idx + 1}"
                size_name = sheet_spec.get("template_size") or DEFAULT_SHEET_SIZE
                w, h = SHEET_SIZES.get(
                    size_name, SHEET_SIZES[DEFAULT_SHEET_SIZE]
                )
                paper_enum = _PAPER_SIZE_ENUM.get(size_name, 0)
                try:
                    new_sheet_ok = drawing_doc.NewSheet3(
                        requested_name,
                        paper_enum,          # PaperSize (I4)
                        _TEMPLATE_CUSTOM,    # TemplateIn (I4)
                        1.0,                 # Scale1 (R8)
                        1.0,                 # Scale2 (R8)
                        True,                # FirstAngle (BOOL)
                        "",                  # TemplateName (BSTR)
                        w,                   # Width (R8, metres)
                        h,                   # Height (R8, metres)
                        "",                  # PropertyViewName (BSTR)
                    )
                except Exception as exc:
                    all_errors.append(
                        f"sheet[{idx}] NewSheet3({requested_name!r}) "
                        f"raised: {exc!r}"
                    )
                    break
                if not new_sheet_ok:
                    all_errors.append(
                        f"sheet[{idx}] NewSheet3({requested_name!r}) "
                        f"returned False"
                    )
                    break
                sheet_names_created.append(requested_name)

            # Resolve the actual active sheet name (for sheet 1, which we did
            # not rename -- ask the drawing doc what it's called)
            try:
                active_raw = drawing_doc.GetCurrentSheet()
                active_sheet = (
                    typed_qi(active_raw, "ISheet", module=mod)
                    if active_raw is not None
                    and not isinstance(active_raw, int)
                    else None
                )
                current_name = (
                    active_sheet.GetName() if active_sheet is not None else ""
                )
            except Exception:
                current_name = ""

            if is_first:
                sheet_spec["name"] = sheet_spec.get("name") or current_name
                # Rename sheet 1 if the spec asked for a specific name
                if sheet_spec["name"] and sheet_spec["name"] != current_name:
                    try:
                        active_sheet.SetName(sheet_spec["name"])
                        current_name = sheet_spec["name"]
                    except Exception as exc:
                        all_errors.append(
                            f"sheet[0] rename to {sheet_spec['name']!r} "
                            f"failed: {exc!r}"
                        )
                        break
                sheet_names_created.append(current_name)
                # Always ActivateSheet(sheet 1) explicitly -- NewSheet3 for
                # later sheets may change the active sheet, and we must not
                # rely on NewDocument's "sheet 1 is active" invariant.
                try:
                    _activate_sheet_by_name(drawing_doc, current_name)
                except Exception as exc:
                    all_errors.append(str(exc))
                    break
            else:
                # Activate the sheet we just created so views land on it
                try:
                    _activate_sheet_by_name(drawing_doc, requested_name)
                    current_name = requested_name
                except Exception as exc:
                    all_errors.append(str(exc))
                    break

            # ----------------------------------------------------------
            # Build this sheet's views / dims / bom
            # ----------------------------------------------------------
            sheet_result = _build_sheet_views(
                drawing_doc,
                mdoc2,
                sheet_spec,
                model_path,
                sheet_index=idx,
                is_first=is_first,
                mod=mod,
                typed_qi=typed_qi,
                model_mdoc2=model_mdoc2,  # W28: for tolerance application
            )
            sheet_result["sheet_name"] = current_name
            per_sheet_results.append(sheet_result)

            all_views_placed.extend(sheet_result.get("views_placed", []))
            total_view_count += sheet_result.get("view_count", 0)

            if sheet_result.get("view_errors"):
                all_errors.extend(sheet_result["view_errors"])
                # Fail-closed (W20/W21): abort BEFORE creating further sheets
                # or SaveAs3 -- a partial drawing on disk is worse than no
                # drawing.
                break

        result["sheets"] = per_sheet_results
        result["sheet_count"] = len(per_sheet_results)
        result["sheet_names"] = sheet_names_created
        result["views_placed"] = all_views_placed
        result["view_count"] = total_view_count

        if all_errors:
            result["view_errors"] = all_errors
            result["error"] = (
                f"{len(all_errors)} sheet/view failure(s); "
                f"no drawing was saved: {'; '.join(all_errors)}"
            )
            return result

        # W28: Save the MODEL if any tolerance was applied
        # Tolerances are MODEL-OWNED (stored in .SLDPRT/.SLDASM, not .SLDDRW)
        any_tolerance_applied = any(
            sr.get("tolerance_applied", False)
            for sr in per_sheet_results
        )
        if any_tolerance_applied and model_doc is not None and model_mdoc2 is not None:
            try:
                model_mdoc2.EditRebuild3()
            except Exception:
                pass
            try:
                model_doc.SaveAs3(model_path, 0, 2)
                result["model_saved"] = True
                result["model_save_path"] = model_path
            except Exception as exc:
                result["error"] = f"Model SaveAs3 failed (tolerance): {exc!r}"
                return result

        # Save the drawing (only reached when EVERY sheet succeeded)
        try:
            doc_raw.SaveAs3(output_path, 0, 2)
            result["save_path"] = output_path
        except Exception as exc:
            result["error"] = f"SaveAs3 failed: {exc!r}"
            return result

        result["ok"] = True
        return result

    finally:
        try:
            t = doc_raw.GetTitle
            t = t() if callable(t) else t
            sw.CloseDoc(t)
        except Exception:
            pass
        # W28: Also close the model doc (we kept it open for tolerance)
        if model_doc is not None:
            try:
                mt = model_doc.GetTitle
                mt = mt() if callable(mt) else mt
                sw.CloseDoc(mt)
            except Exception:
                pass
