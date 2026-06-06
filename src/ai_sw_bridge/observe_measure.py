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

from typing import Any

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