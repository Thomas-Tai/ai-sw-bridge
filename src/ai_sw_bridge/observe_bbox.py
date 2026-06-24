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
from .sw_com import SW_DOC_ASSEMBLY, SW_DOC_PART, resolve


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
        if hasattr(part_doc, "GetPartBox"):
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


def _sw_get_bbox_from_doc_impl(doc: Any) -> dict[str, Any]:
    """Core: read bounding-box from a part document (v0.18 implementation).

    Validates doc type, then delegates to :func:`read_bbox`.
    Returns structured report:
    ``{"ok": bool, "bounding_box": {...}, "error": str|None}``.
    Internal callers (the ``SolidWorksClient.observe`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_get_bbox_from_doc` free function routes here behind a
    ``PendingDeprecationWarning``.

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


def _transform_point(
    m: list[float], x: float, y: float, z: float
) -> tuple[float, float, float]:
    """Apply a 4×4 row-major transform matrix to a 3D point."""
    tx = m[0] * x + m[1] * y + m[2] * z + m[3]
    ty = m[4] * x + m[5] * y + m[6] * z + m[7]
    tz = m[8] * x + m[9] * y + m[10] * z + m[11]
    return tx, ty, tz


def _read_component_transform(comp: Any, mod: Any = None) -> list[float] | None:
    """Read the component placement as a 16-element ROW-MAJOR 4×4 matrix
    (translation at indices 3/7/11 — the layout :func:`_transform_point` expects).

    W52-B seat: ``IComponent2.Transform2`` returns an ``IMathTransform`` whose
    ``.ArrayData`` is 16 doubles laid out ``[0-8]=3×3 rotation, [9-11]=translation,
    [12]=scale, [13-15]=0`` — NOT a row-major 4×4. We convert that to row-major.
    The offline mocks set ``Transform2`` to an already-row-major list, so a
    list/tuple is returned verbatim. Raw component first (mock-friendly); typed
    ``IComponent2`` fallback (Transform2 may not resolve on a raw component).
    """

    def _as_rowmajor(t: Any) -> list[float] | None:
        if t is None:
            return None
        if isinstance(t, (list, tuple)):
            return [float(v) for v in t[:16]] if len(t) >= 16 else None
        # IMathTransform — read ArrayData and convert SW layout → row-major.
        try:
            ad = t.ArrayData
            if callable(ad):
                ad = ad()
            ad = [float(v) for v in ad]
        except Exception:
            return None
        if len(ad) < 12:
            return None
        return [
            ad[0],
            ad[1],
            ad[2],
            ad[9],
            ad[3],
            ad[4],
            ad[5],
            ad[10],
            ad[6],
            ad[7],
            ad[8],
            ad[11],
            0.0,
            0.0,
            0.0,
            1.0,
        ]

    try:
        t = comp.Transform2
        if callable(t):
            t = t()
        res = _as_rowmajor(t)
        if res is not None:
            return res
    except Exception:
        pass
    if mod is not None:
        try:
            ct = typed(comp, "IComponent2", module=mod)
            t = ct.Transform2
            if callable(t):
                t = t()
            return _as_rowmajor(t)
        except Exception:
            pass
    return None


def read_assembly_bbox(asm_doc: Any, mod: Any = None) -> dict[str, Any]:
    """Read the combined bounding-box of all components in an assembly (W52).

    Walks every component via ``IAssemblyDoc.GetComponents(True)``, reads each
    component's part-document box (``IPartDoc.GetPartBox(True)``, metres),
    transforms the 8 corners through the component's placement matrix
    (``IComponent2.Transform2``), and unions them into a single AABB.

    Returns the same shape as :func:`read_bbox` plus ``component_count``.
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
        "component_count": 0,
        "errors": [],
    }

    if mod is None:
        mod = wrapper_module()

    try:
        asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)
    except Exception as exc:
        result["errors"].append(f"typed(IAssemblyDoc): {exc!r}")
        return result

    try:
        comps = asm_typed.GetComponents(True)
    except Exception as exc:
        result["errors"].append(f"GetComponents: {exc!r}")
        return result

    if comps is None:
        result["errors"].append("no components in assembly")
        return result

    if not isinstance(comps, (list, tuple)):
        comps = (comps,)

    result["component_count"] = len(comps)

    g_xmin = g_ymin = g_zmin = float("inf")
    g_xmax = g_ymax = g_zmax = float("-inf")
    found_any = False

    for comp in comps:
        transform = _read_component_transform(comp, mod)
        if transform is None:
            transform = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

        # GetModelDoc2 does not resolve on a RAW late-bound IComponent2 at the
        # live seat (W52-B 'Member not found'). Try late-bound FIRST — preserves
        # the offline mocks, which set comp.GetModelDoc2 and rely on identity —
        # and on a raise retry through the typed IComponent2. Each skip records
        # its reason so a seat failure is loud, not a silent drop.
        part_doc = None
        try:
            part_doc = comp.GetModelDoc2()
        except Exception:
            try:
                part_doc = typed(comp, "IComponent2", module=mod).GetModelDoc2()
            except Exception as exc:
                result["errors"].append(f"GetModelDoc2 failed: {exc!r}")
        if part_doc is None:
            continue

        try:
            pdoc_typed = typed(part_doc, "IPartDoc", module=mod)
            box = pdoc_typed.GetPartBox(True)
        except Exception as exc:
            result["errors"].append(f"GetPartBox failed: {exc!r}")
            continue

        if box is None or len(box) < 6:
            result["errors"].append(f"GetPartBox returned bad box: {box!r}")
            continue

        try:
            bx = [float(box[i]) for i in range(6)]
        except (TypeError, ValueError):
            continue

        corners = [
            (bx[0], bx[1], bx[2]),
            (bx[3], bx[1], bx[2]),
            (bx[0], bx[4], bx[2]),
            (bx[3], bx[4], bx[2]),
            (bx[0], bx[1], bx[5]),
            (bx[3], bx[1], bx[5]),
            (bx[0], bx[4], bx[5]),
            (bx[3], bx[4], bx[5]),
        ]

        for cx, cy, cz in corners:
            tx, ty, tz = _transform_point(transform, cx, cy, cz)
            g_xmin = min(g_xmin, tx)
            g_xmax = max(g_xmax, tx)
            g_ymin = min(g_ymin, ty)
            g_ymax = max(g_ymax, ty)
            g_zmin = min(g_zmin, tz)
            g_zmax = max(g_zmax, tz)
            found_any = True

    if not found_any:
        result["errors"].append("no component bounding boxes readable")
        return result

    result["x_min_mm"] = g_xmin * 1000.0
    result["x_max_mm"] = g_xmax * 1000.0
    result["y_min_mm"] = g_ymin * 1000.0
    result["y_max_mm"] = g_ymax * 1000.0
    result["z_min_mm"] = g_zmin * 1000.0
    result["z_max_mm"] = g_zmax * 1000.0
    result["dx_mm"] = (g_xmax - g_xmin) * 1000.0
    result["dy_mm"] = (g_ymax - g_ymin) * 1000.0
    result["dz_mm"] = (g_zmax - g_zmin) * 1000.0

    return result


def _sw_get_assembly_bbox_from_doc_impl(doc: Any) -> dict[str, Any]:
    """Core: read bounding-box from an assembly document (v0.18 implementation).

    Validates doc type is assembly, then delegates to :func:`read_assembly_bbox`.
    Returns structured report:
    ``{"ok": bool, "bounding_box": {...}, "error": str|None}``.
    Internal callers (the ``SolidWorksClient.observe`` facade) call this
    directly so they bypass the deprecation shim; the public
    :func:`sw_get_assembly_bbox_from_doc` free function routes here behind a
    ``PendingDeprecationWarning``.

    Fail-closed: non-assembly input → ``ok=False`` with clear error.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "bounding_box": None,
    }

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

    if doc_type != SW_DOC_ASSEMBLY:
        result["error"] = (
            f"assembly bounding-box requires assembly document (got type {doc_type})"
        )
        return result

    mod = wrapper_module()
    bbox = read_assembly_bbox(doc, mod)

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
            "component_count": bbox["component_count"],
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
            "component_count": bbox["component_count"],
        }
        result["ok"] = True

    return result
