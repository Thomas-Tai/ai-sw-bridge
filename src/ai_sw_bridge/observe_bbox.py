"""Bounding-box observation helper — W30 (perception axis).

Read-only bounding-box extraction via ``IPartDoc.GetPartBox``.

Seat-validated on SW 2024 SP1 (rev 32.1.0):
  - ``IPartDoc.GetPartBox(True)`` returns 6-tuple [Xmin, Ymin, Zmin, Xmax, Ymax, Zmax]
    in METRES (the True arg = use default bounding-box mode).
  - Values are axis-aligned in the part's coordinate system.
  - Works on parts only — assemblies/drawings get typed error result.
  - ``IModelDocExtension.GetBox`` is NOT exposed on SW 2024 typelib — use GetPartBox.

The existing ``sw_get_bbox`` in ``observe.py`` is the canonical implementation;
this module provides the read_bbox helper for module-level organization.
"""

from __future__ import annotations

from typing import Any

from .com.earlybind import typed
from .com.sw_type_info import wrapper_module
from .sw_com import SW_DOC_PART, resolve


def read_bbox(part_doc: Any, mod: Any = None) -> dict[str, Any]:
    """Read bounding-box from a part document.

    Uses ``IPartDoc.GetPartBox(True)`` which returns a 6-tuple
    [Xmin, Ymin, Zmin, Xmax, Ymax, Zmax] in metres.

    Accepts either late-bound dispatch or typed IModelDoc2/IPartDoc.
    If IModelDoc2 is passed, will try to QI to IPartDoc.

    Returns dict with min/max corners (mm) and spans (mm):
      - x_min_mm, x_max_mm, y_min_mm, y_max_mm, z_min_mm, z_max_mm
      - dx_mm, dy_mm, dz_mm (spans)

    Fail-soft: GetPartBox failure returns error field, not exception.
    """
    result: dict[str, Any] = {
        "x_min_mm": None,
        "x_max_mm": None,
        "y_min_mm": None,
        "y_max_mm": None,
        "z_min_mm": None,
        "z_max_mm": None,
        "dx_mm": None,
        "dy_mm": None,
        "dz_mm": None,
        "errors": [],
    }

    # Get IPartDoc interface - try direct first, then typed, then late-bound
    part_typed = None
    try:
        # If it's already typed IPartDoc, use it directly
        if hasattr(part_doc, 'GetPartBox'):
            part_typed = part_doc
        else:
            # Try to QI to IPartDoc
            if mod is None:
                mod = wrapper_module()
            part_typed = typed(part_doc, "IPartDoc", module=mod)
    except Exception:
        # Late-bound fallback
        part_typed = part_doc

    # GetPartBox(True) — use default bounding-box mode
    try:
        box = part_typed.GetPartBox(True)
    except Exception as exc:
        result["errors"].append(f"GetPartBox: {exc!r}")
        return result

    if box is None or len(box) < 6:
        result["errors"].append(f"GetPartBox returned unexpected shape: {box!r}")
        return result

    try:
        x_min, y_min, z_min = float(box[0]), float(box[1]), float(box[2])
        x_max, y_max, z_max = float(box[3]), float(box[4]), float(box[5])

        # Convert m → mm (×1000)
        result["x_min_mm"] = x_min * 1000.0
        result["x_max_mm"] = x_max * 1000.0
        result["y_min_mm"] = y_min * 1000.0
        result["y_max_mm"] = y_max * 1000.0
        result["z_min_mm"] = z_min * 1000.0
        result["z_max_mm"] = z_max * 1000.0

        # Compute spans (mm)
        result["dx_mm"] = (x_max - x_min) * 1000.0
        result["dy_mm"] = (y_max - y_min) * 1000.0
        result["dz_mm"] = (z_max - z_min) * 1000.0
    except (TypeError, ValueError) as exc:
        result["errors"].append(f"box parse: {exc!r}")

    return result


def sw_get_bbox_from_doc(doc: Any) -> dict[str, Any]:
    """Top-level observer: read bounding-box from a part document.

    Validates doc type, then delegates to :func:`read_bbox`.
    Returns structured report:
    ``{"ok": bool, "bounding_box": {...}, "error": str|None}``.

    Fail-closed: non-part input → ``ok=False`` with clear error.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "bounding_box": None,
    }

    mod = wrapper_module()

    # Check document type - try direct first, then late-bound
    try:
        doc_type = doc.GetType
        if callable(doc_type):
            doc_type = doc_type()
    except AttributeError:
        try:
            doc_type = resolve(doc, "GetType")
            if callable(doc_type):
                doc_type = doc_type()
        except Exception as exc:
            result["error"] = f"doc.GetType failed: {exc!r}"
            return result

    if doc_type != SW_DOC_PART:
        result["error"] = f"bounding-box requires part document (got type {doc_type})"
        return result

    bbox = read_bbox(doc, mod)
    if bbox["errors"]:
        result["error"] = "; ".join(bbox["errors"])
        result["bounding_box"] = {
            "x_min_mm": bbox["x_min_mm"],
            "x_max_mm": bbox["x_max_mm"],
            "y_min_mm": bbox["y_min_mm"],
            "y_max_mm": bbox["y_max_mm"],
            "z_min_mm": bbox["z_min_mm"],
            "z_max_mm": bbox["z_max_mm"],
            "dx_mm": bbox["dx_mm"],
            "dy_mm": bbox["dy_mm"],
            "dz_mm": bbox["dz_mm"],
        }
    else:
        result["bounding_box"] = {
            "x_min_mm": bbox["x_min_mm"],
            "x_max_mm": bbox["x_max_mm"],
            "y_min_mm": bbox["y_min_mm"],
            "y_max_mm": bbox["y_max_mm"],
            "z_min_mm": bbox["z_min_mm"],
            "z_max_mm": bbox["z_max_mm"],
            "dx_mm": bbox["dx_mm"],
            "dy_mm": bbox["dy_mm"],
            "dz_mm": bbox["dz_mm"],
        }
        result["ok"] = True

    return result