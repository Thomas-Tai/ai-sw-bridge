"""Measure observation helper — W30 (perception axis).

Read-only measurement via ``IModelDocExtension.CreateMeasure`` → ``IMeasure``.

Seat-validated on SW 2024 SP1 (rev 31.1.0):
  - ``IModelDocExtension.CreateMeasure`` returns ``IMeasure`` (property-get).
  - ``IMeasure.Calculate(None)`` measures the currently selected entities.
  - ``IMeasure.Distance``, ``DeltaX``, ``DeltaY``, ``DeltaZ`` (metres, -1 when N/A).
  - Requires pre-selection of entities via ``select_entity`` (IEntity.Select2).
  - Two-entity vertex-to-vertex measurement returns correct diagonal distance.

The existing ``sw_measure`` in ``observe.py`` is the canonical implementation;
this module provides the read_measure helper for module-level organization.
"""

from __future__ import annotations

import base64
import math
from typing import Any

from .com.earlybind import typed, typed_extension
from .com.sw_type_info import wrapper_module
from .sw_com import resolve


def read_measure(doc: Any, measure: Any) -> dict[str, Any]:
    """Read measurement results from an ``IMeasure`` object.

    After ``Calculate(None)`` has been called on selected entities,
    reads ``Distance``, ``DeltaX``, ``DeltaY``, ``DeltaZ`` (metres).

    Returns dict with measurements (mm):
      - distance_mm, delta_x_mm, delta_y_mm, delta_z_mm

    Fail-soft: -1 values or None returns that field as None.
    """
    result: dict[str, Any] = {
        "distance_mm": None,
        "delta_x_mm": None,
        "delta_y_mm": None,
        "delta_z_mm": None,
        "errors": [],
    }

    def safe_float(attr_name: str) -> float | None:
        try:
            v = resolve(measure, attr_name)
            if v is None:
                return None
            fv = float(v)
            if fv == -1.0:
                return None
            return fv * 1000.0  # m → mm
        except Exception:
            return None

    result["distance_mm"] = safe_float("Distance")
    result["delta_x_mm"] = safe_float("DeltaX")
    result["delta_y_mm"] = safe_float("DeltaY")
    result["delta_z_mm"] = safe_float("DeltaZ")

    # Check if any measurement succeeded
    if all(v is None for v in [result["distance_mm"], result["delta_x_mm"],
                               result["delta_y_mm"], result["delta_z_mm"]]):
        result["errors"].append("no valid measurements returned")

    return result


def create_measure(doc: Any) -> Any | None:
    """Create an IMeasure object from a document.

    Uses ``IModelDocExtension.CreateMeasure`` (property-get).
    Returns None on failure.
    """
    try:
        ext = resolve(doc, "Extension")
        if ext is None:
            return None
        measure = resolve(ext, "CreateMeasure")
        if callable(measure):
            measure = measure()
        return measure
    except Exception:
        return None


def sw_get_measure_from_doc(doc: Any) -> dict[str, Any]:
    """Top-level observer: measure currently selected entities.

    Validates doc exists, creates IMeasure, runs Calculate,
    then delegates to :func:`read_measure`.

    Returns structured report:
    ``{"ok": bool, "measure": {...}, "selected_count": int, "error": str|None}``.

    Note: Caller must pre-select entities via ``select_entity`` or SW UI.
    This function does NOT perform selection — it only measures what's selected.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "measure": None,
        "selected_count": 0,
    }

    # Get selection count - try direct attribute first (typed), then resolve (late-bound)
    try:
        sel_mgr = doc.SelectionManager
    except AttributeError:
        try:
            sel_mgr = resolve(doc, "SelectionManager")
        except Exception as exc:
            result["error"] = f"SelectionManager failed: {exc!r}"
            return result

    if sel_mgr is None:
        result["error"] = "SelectionManager returned None"
        return result

    try:
        count = sel_mgr.GetSelectedObjectCount2
        if callable(count):
            count = count(-1)  # -1 = all marks
        else:
            # Try as property
            count = count
        result["selected_count"] = int(count) if count is not None else 0
    except Exception:
        try:
            count = sel_mgr.GetSelectedObjectCount
            if callable(count):
                count = count()
            result["selected_count"] = int(count) if count is not None else 0
        except Exception as exc:
            result["error"] = f"GetSelectedObjectCount failed: {exc!r}"
            return result

    if result["selected_count"] == 0:
        result["error"] = "no entities selected — select entities before measuring"
        return result

    # Create IMeasure - try direct attribute first (typed), then resolve (late-bound)
    try:
        ext = doc.Extension
    except AttributeError:
        try:
            ext = resolve(doc, "Extension")
        except Exception as exc:
            result["error"] = f"Extension failed: {exc!r}"
            return result

    if ext is None:
        result["error"] = "Extension returned None"
        return result

    try:
        measure = ext.CreateMeasure
        if callable(measure):
            measure = measure()
    except Exception as exc:
        result["error"] = f"CreateMeasure failed: {exc!r}"
        return result

    if measure is None:
        result["error"] = "CreateMeasure returned None"
        return result

    # Calculate
    try:
        calc = measure.Calculate
        if callable(calc):
            calc(None)  # None = measure selected entities
    except Exception as exc:
        result["error"] = f"Calculate failed: {exc!r}"
        return result

    # Read results - try direct attributes first (typed), then resolve (late-bound)
    def safe_float(attr_name: str) -> float | None:
        try:
            v = getattr(measure, attr_name)
            if callable(v):
                v = v()
            if v is None:
                return None
            fv = float(v)
            if fv == -1.0:
                return None
            return fv * 1000.0  # m → mm
        except Exception:
            try:
                v = resolve(measure, attr_name)
                if v is None:
                    return None
                fv = float(v)
                if fv == -1.0:
                    return None
                return fv * 1000.0  # m → mm
            except Exception:
                return None

    meas: dict[str, Any] = {
        "distance_mm": safe_float("Distance"),
        "delta_x_mm": safe_float("DeltaX"),
        "delta_y_mm": safe_float("DeltaY"),
        "delta_z_mm": safe_float("DeltaZ"),
        "errors": [],
    }

    # Check if any measurement succeeded
    if all(v is None for v in [meas["distance_mm"], meas["delta_x_mm"],
                               meas["delta_y_mm"], meas["delta_z_mm"]]):
        meas["errors"].append("no valid measurements returned")

    if meas["errors"]:
        result["error"] = "; ".join(meas["errors"])
        result["measure"] = {
            "distance_mm": meas["distance_mm"],
            "delta_x_mm": meas["delta_x_mm"],
            "delta_y_mm": meas["delta_y_mm"],
            "delta_z_mm": meas["delta_z_mm"],
        }
    else:
        result["measure"] = {
            "distance_mm": meas["distance_mm"],
            "delta_x_mm": meas["delta_x_mm"],
            "delta_y_mm": meas["delta_y_mm"],
            "delta_z_mm": meas["delta_z_mm"],
        }
        result["ok"] = True

    return result


def _resolve_durable_ref(
    doc: Any, durable_ref_b64: str, mod: Any = None
) -> tuple[Any | None, str | None]:
    """Resolve a base64url-encoded persist reference to a live entity.

    Returns ``(entity, error)`` — entity is None when resolution fails,
    error carries the reason string.
    """
    if mod is None:
        mod = wrapper_module()

    try:
        pad = "=" * (-len(durable_ref_b64) % 4)
        pid_bytes = base64.urlsafe_b64decode(durable_ref_b64 + pad)
    except Exception as exc:
        return None, f"bad durable_ref: {exc}"

    try:
        ext = typed_extension(doc, module=mod)
        res = ext.GetObjectByPersistReference3(pid_bytes)
    except Exception as exc:
        return None, f"persist resolve failed: {type(exc).__name__}"

    entity = res[0] if isinstance(res, tuple) else res
    if entity is None or isinstance(entity, int):
        code = res[1] if isinstance(res, tuple) and len(res) > 1 else None
        return None, f"persist resolved to error code {code}"

    return entity, None


def _select_entity(doc: Any, entity: Any, append: bool, mod: Any = None) -> bool:
    """Select a single entity via ``IEntity.Select4`` (append, mark=0).

    Falls back to ``Select2`` if ``Select4`` is unavailable.
    Returns True on success.
    """
    if mod is None:
        mod = wrapper_module()

    try:
        ientity = typed(entity, "IEntity", module=mod)
        select_fn = getattr(ientity, "Select4", None)
        if select_fn is not None:
            return bool(select_fn(append, 0))
    except Exception:
        pass

    try:
        select_fn = getattr(entity, "Select2", None)
        if select_fn is None:
            select_fn = getattr(entity, "Select4", None)
        if select_fn is not None and callable(select_fn):
            return bool(select_fn(append, 0))
    except Exception:
        pass

    return False


def read_measure_durable_pair(
    doc: Any,
    durable_ref_a: str,
    durable_ref_b: str,
    mod: Any = None,
) -> dict[str, Any]:
    """Measure between two durable-reference entities (W52).

    Pipeline:
      1. Resolve each ``durable_ref`` (base64url persist token) to a live
         entity via ``GetObjectByPersistReference3``.
      2. Clear selection, then ``IEntity.Select4`` both (append).
      3. ``CreateMeasure`` → ``Calculate(None)`` → read Distance/DeltaX/Y/Z.

    Returns dict with:
      - distance_mm, delta_x_mm, delta_y_mm, delta_z_mm (mm, None on N/A)
      - errors (list[str])
    """
    result: dict[str, Any] = {
        "distance_mm": None,
        "delta_x_mm": None,
        "delta_y_mm": None,
        "delta_z_mm": None,
        "errors": [],
    }

    if mod is None:
        mod = wrapper_module()

    entity_a, err_a = _resolve_durable_ref(doc, durable_ref_a, mod)
    if entity_a is None:
        result["errors"].append(f"ref_a: {err_a}")
        return result

    entity_b, err_b = _resolve_durable_ref(doc, durable_ref_b, mod)
    if entity_b is None:
        result["errors"].append(f"ref_b: {err_b}")
        return result

    try:
        doc_typed = typed(doc, "IModelDoc2", module=mod)
        doc_typed.ClearSelection2(True)
    except Exception:
        pass

    if not _select_entity(doc, entity_a, False, mod):
        result["errors"].append("Select4 failed for entity_a")
        return result
    if not _select_entity(doc, entity_b, True, mod):
        result["errors"].append("Select4 failed for entity_b")
        return result

    try:
        ext = doc_typed.Extension
        measure = ext.CreateMeasure
        if callable(measure):
            measure = measure()
    except Exception as exc:
        result["errors"].append(f"CreateMeasure: {exc!r}")
        return result

    if measure is None:
        result["errors"].append("CreateMeasure returned None")
        return result

    try:
        calc = measure.Calculate
        if callable(calc):
            calc(None)
    except Exception as exc:
        result["errors"].append(f"Calculate: {exc!r}")
        return result

    def safe_float(attr_name: str) -> float | None:
        try:
            v = getattr(measure, attr_name)
            if callable(v):
                v = v()
            if v is None:
                return None
            fv = float(v)
            if fv == -1.0:
                return None
            return fv * 1000.0
        except Exception:
            return None

    result["distance_mm"] = safe_float("Distance")
    result["delta_x_mm"] = safe_float("DeltaX")
    result["delta_y_mm"] = safe_float("DeltaY")
    result["delta_z_mm"] = safe_float("DeltaZ")

    if all(v is None for v in [result["distance_mm"], result["delta_x_mm"],
                               result["delta_y_mm"], result["delta_z_mm"]]):
        result["errors"].append("no valid measurements returned")

    return result


def sw_get_measure_durable_pair(
    doc: Any, durable_ref_a: str, durable_ref_b: str
) -> dict[str, Any]:
    """Top-level observer: measure between two durable references (W52).

    Returns structured report:
    ``{"ok": bool, "measure": {distance_mm, delta_x_mm, delta_y_mm, delta_z_mm},
      "error": str|None}``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "measure": None,
    }

    mod = wrapper_module()
    meas = read_measure_durable_pair(doc, durable_ref_a, durable_ref_b, mod)

    if meas["errors"]:
        result["error"] = "; ".join(meas["errors"])
    else:
        result["ok"] = True

    result["measure"] = {
        "distance_mm": meas["distance_mm"],
        "delta_x_mm": meas["delta_x_mm"],
        "delta_y_mm": meas["delta_y_mm"],
        "delta_z_mm": meas["delta_z_mm"],
    }
    return result


def read_measure_angle(measure: Any) -> dict[str, Any]:
    """Read the ``Angle`` property from an ``IMeasure`` object.

    Returns dict with:
      - angle_deg (float | None) — degrees, None when not applicable.
      - errors (list[str])
    """
    result: dict[str, Any] = {"angle_deg": None, "errors": []}
    try:
        v = getattr(measure, "Angle")
        if callable(v):
            v = v()
        if v is None:
            result["errors"].append("Angle returned None")
            return result
        fv = float(v)
        if fv == -1.0:
            result["errors"].append("Angle not applicable (-1)")
            return result
        result["angle_deg"] = math.degrees(fv)
    except Exception as exc:
        result["errors"].append(f"Angle read: {exc!r}")
    return result


def read_measure_area(measure: Any) -> dict[str, Any]:
    """Read the ``Area`` property from an ``IMeasure`` object.

    Returns dict with:
      - area_mm2 (float | None) — mm², None when not applicable.
      - errors (list[str])
    """
    result: dict[str, Any] = {"area_mm2": None, "errors": []}
    try:
        v = getattr(measure, "Area")
        if callable(v):
            v = v()
        if v is None:
            result["errors"].append("Area returned None")
            return result
        fv = float(v)
        if fv == -1.0:
            result["errors"].append("Area not applicable (-1)")
            return result
        result["area_mm2"] = fv * 1e6
    except Exception as exc:
        result["errors"].append(f"Area read: {exc!r}")
    return result


def sw_get_measure_angle_from_doc(doc: Any) -> dict[str, Any]:
    """Top-level observer: angle of currently selected entities (W52).

    Measures the current selection and reads ``IMeasure.Angle``.
    Returns ``{"ok": bool, "measure": {"angle_deg": float|None}, "error": str|None}``.
    """
    result: dict[str, Any] = {"ok": False, "error": None, "measure": None}

    try:
        sel_mgr = doc.SelectionManager
    except AttributeError:
        try:
            sel_mgr = resolve(doc, "SelectionManager")
        except Exception as exc:
            result["error"] = f"SelectionManager failed: {exc!r}"
            return result

    if sel_mgr is None:
        result["error"] = "SelectionManager returned None"
        return result

    try:
        count = sel_mgr.GetSelectedObjectCount2
        if callable(count):
            count = count(-1)
        count = int(count) if count is not None else 0
    except Exception:
        count = 0

    if count == 0:
        result["error"] = "no entities selected — select entities before measuring"
        return result

    try:
        ext = doc.Extension
    except AttributeError:
        try:
            ext = resolve(doc, "Extension")
        except Exception as exc:
            result["error"] = f"Extension failed: {exc!r}"
            return result

    if ext is None:
        result["error"] = "Extension returned None"
        return result

    try:
        measure = ext.CreateMeasure
        if callable(measure):
            measure = measure()
    except Exception as exc:
        result["error"] = f"CreateMeasure failed: {exc!r}"
        return result

    if measure is None:
        result["error"] = "CreateMeasure returned None"
        return result

    try:
        calc = measure.Calculate
        if callable(calc):
            calc(None)
    except Exception as exc:
        result["error"] = f"Calculate failed: {exc!r}"
        return result

    angle_result = read_measure_angle(measure)
    if angle_result["errors"]:
        result["error"] = "; ".join(angle_result["errors"])
    else:
        result["ok"] = True

    result["measure"] = {"angle_deg": angle_result["angle_deg"]}
    return result


def sw_get_measure_area_from_doc(doc: Any) -> dict[str, Any]:
    """Top-level observer: area of currently selected entity (W52).

    Measures the current selection and reads ``IMeasure.Area``.
    Returns ``{"ok": bool, "measure": {"area_mm2": float|None}, "error": str|None}``.
    """
    result: dict[str, Any] = {"ok": False, "error": None, "measure": None}

    try:
        sel_mgr = doc.SelectionManager
    except AttributeError:
        try:
            sel_mgr = resolve(doc, "SelectionManager")
        except Exception as exc:
            result["error"] = f"SelectionManager failed: {exc!r}"
            return result

    if sel_mgr is None:
        result["error"] = "SelectionManager returned None"
        return result

    try:
        count = sel_mgr.GetSelectedObjectCount2
        if callable(count):
            count = count(-1)
        count = int(count) if count is not None else 0
    except Exception:
        count = 0

    if count == 0:
        result["error"] = "no entities selected — select entities before measuring"
        return result

    try:
        ext = doc.Extension
    except AttributeError:
        try:
            ext = resolve(doc, "Extension")
        except Exception as exc:
            result["error"] = f"Extension failed: {exc!r}"
            return result

    if ext is None:
        result["error"] = "Extension returned None"
        return result

    try:
        measure = ext.CreateMeasure
        if callable(measure):
            measure = measure()
    except Exception as exc:
        result["error"] = f"CreateMeasure failed: {exc!r}"
        return result

    if measure is None:
        result["error"] = "CreateMeasure returned None"
        return result

    try:
        calc = measure.Calculate
        if callable(calc):
            calc(None)
    except Exception as exc:
        result["error"] = f"Calculate failed: {exc!r}"
        return result

    area_result = read_measure_area(measure)
    if area_result["errors"]:
        result["error"] = "; ".join(area_result["errors"])
    else:
        result["ok"] = True

    result["measure"] = {"area_mm2": area_result["area_mm2"]}
    return result