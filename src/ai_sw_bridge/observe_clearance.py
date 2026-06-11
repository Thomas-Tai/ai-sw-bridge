"""Clearance (min-distance) observation helper — W35 (perception axis).

Read-only minimum-distance measurement between two selected components
via ``IModelDocExtension.CreateMeasure`` → ``IMeasure.Distance``.

Seat-validated on SW 2024 SP1 (rev 32.1.0):
  - ``IComponent2.Select2(append=True, mark=0)`` selects each component;
    appended into one selection set.
  - ``IModelDocExtension.CreateMeasure()`` returns ``IMeasure``.
  - ``IMeasure.Calculate(None)`` measures the currently selected entities.
  - ``IMeasure.Distance`` (metres) IS the minimum distance between two
    selected components — proven by two-gap discrimination (10mm and 25mm).
  - No separate ``MinimumDistance`` member exists; ``Distance`` is the
    correct value.
  - Distance == -1.0 when components are touching (0mm gap) or
    overlapping (negative gap) — ``None`` returned in those cases;
    use W27 ``observe_interference`` for overlap volume.

v1 scope: min distance between TWO components in one assembly.
DEFER: face-pair by durable ref, multi-component nearest-pair sweep,
clearance with moving/swept envelope, clearance in a specific
configuration, point-to-body, angle/area measures.
"""

from __future__ import annotations

from typing import Any

from .com.earlybind import typed
from .com.sw_type_info import wrapper_module
from .sw_com import SW_DOC_ASSEMBLY, resolve


def _find_component_by_name(asm_doc: Any, name: str, mod: Any = None) -> Any | None:
    """Find a component in the assembly by its display name.

    Iterates the assembly's component list (IAssemblyDoc.GetComponents(True))
    and matches ``IComponent2.Name2`` (the instance name, e.g. ``block_20mm-1``).

    Returns the IComponent2 dispatch object, or None if not found.
    """
    if mod is None:
        mod = wrapper_module()

    try:
        asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)
    except Exception:
        return None

    try:
        comps = asm_typed.GetComponents(True)  # True = all components recursively
    except Exception:
        return None

    if comps is None:
        return None

    if not isinstance(comps, (list, tuple)):
        comps = (comps,)

    for comp in comps:
        try:
            comp_name = comp.Name2
            if callable(comp_name):
                comp_name = comp_name()
            if str(comp_name) == name:
                return comp
        except Exception:
            continue

    return None


def read_clearance(
    asm_doc: Any,
    comp_a_name: str,
    comp_b_name: str,
    mod: Any = None,
) -> dict[str, Any]:
    """Measure the minimum distance between two named components.

    Pipeline (seat-proven via W35 S1 spike):
      1. Find each component via ``IAssemblyDoc.GetComponents(True)`` +
         ``IComponent2.Name2`` match.
      2. ``IComponent2.Select2(append, mark=0)`` for each — build a
         2-item selection set.
      3. ``IModelDocExtension.CreateMeasure()`` → ``IMeasure``.
      4. ``IMeasure.Calculate(None)`` → reads currently selected entities.
      5. ``IMeasure.Distance`` (metres, -1 if touching/overlapping).

    Returns dict with:
      - min_distance_mm (float | None) — None if touching or overlapping.
      - components (list[str]) — [comp_a_name, comp_b_name].
      - touching (bool) — True if Distance returned -1.0 (touching or overlap).
      - errors (list[str]).
    """
    result: dict[str, Any] = {
        "min_distance_mm": None,
        "components": [comp_a_name, comp_b_name],
        "touching": False,
        "errors": [],
    }

    if mod is None:
        mod = wrapper_module()

    # ── Pre-flight: same-name check ──────────────────────────────────────
    if comp_a_name == comp_b_name:
        result["errors"].append("comp_a and comp_b are the same component")
        return result

    # ── Find components ──────────────────────────────────────────────────
    comp_a = _find_component_by_name(asm_doc, comp_a_name, mod)
    comp_b = _find_component_by_name(asm_doc, comp_b_name, mod)

    if comp_a is None:
        result["errors"].append(f"component not found: {comp_a_name!r}")
        return result
    if comp_b is None:
        result["errors"].append(f"component not found: {comp_b_name!r}")
        return result

    # ── Get IModelDoc2 for selection ─────────────────────────────────────
    try:
        doc_typed = typed(asm_doc, "IModelDoc2", module=mod)
    except Exception as exc:
        result["errors"].append(f"typed(IModelDoc2): {exc!r}")
        return result

    # ── Clear selection ──────────────────────────────────────────────────
    try:
        doc_typed.ClearSelection2(True)
    except Exception:
        pass

    # ── Select both components via IComponent2.Select2 ───────────────────
    for idx, comp in enumerate([comp_a, comp_b]):
        try:
            select_fn = comp.Select2
            if callable(select_fn):
                ok = select_fn(True, 0)  # append=True, mark=0
            else:
                ok = comp.Select2
            if not ok:
                name = comp_a_name if idx == 0 else comp_b_name
                result["errors"].append(f"Select2 returned False for {name!r}")
                return result
        except Exception as exc:
            name = comp_a_name if idx == 0 else comp_b_name
            result["errors"].append(f"Select2({name!r}): {exc!r}")
            return result

    # ── Verify selection count ───────────────────────────────────────────
    try:
        sel_mgr = doc_typed.SelectionManager
        count = sel_mgr.GetSelectedObjectCount2(-1)
        if count < 2:
            result["errors"].append(f"selection count = {count}, expected >= 2")
            return result
    except Exception as exc:
        result["errors"].append(f"SelectionManager: {exc!r}")
        return result

    # ── CreateMeasure ────────────────────────────────────────────────────
    measure = None
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

    # ── Calculate ────────────────────────────────────────────────────────
    try:
        calc = measure.Calculate
        if callable(calc):
            calc(None)
    except Exception as exc:
        result["errors"].append(f"Calculate: {exc!r}")
        return result

    # ── Read Distance ────────────────────────────────────────────────────
    try:
        dist = measure.Distance
        if callable(dist):
            dist = dist()
        if dist is not None:
            dist_f = float(dist)
            if dist_f == -1.0:
                # Touching or overlapping → no measurable gap
                result["touching"] = True
            else:
                result["min_distance_mm"] = dist_f * 1000.0  # m → mm
    except Exception as exc:
        result["errors"].append(f"Distance read: {exc!r}")

    return result


def sw_get_clearance(doc: Any, comp_a_name: str, comp_b_name: str) -> dict[str, Any]:
    """Top-level observer: measure clearance between two assembly components.

    Validates *doc* is an assembly, then delegates to :func:`read_clearance`.
    Returns structured report:
    ``{"ok": bool, "clearance": {...}, "error": str|None}``.

    Fail-closed:
      - Not an assembly → ``ok=False``, typed error.
      - Component not found → ``ok=False``, typed error.
      - IMeasure failure → ``ok=False``, error message.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "clearance": None,
    }

    # Check document type
    try:
        doc_type = resolve(doc, "GetType")
        if callable(doc_type):
            doc_type = doc_type()
    except Exception as exc:
        result["error"] = f"doc.GetType failed: {exc!r}"
        return result

    if doc_type != SW_DOC_ASSEMBLY:
        result["error"] = (
            f"clearance measurement requires assembly document (got type {doc_type})"
        )
        return result

    mod = wrapper_module()
    clearance = read_clearance(doc, comp_a_name, comp_b_name, mod)

    if clearance["errors"]:
        result["error"] = "; ".join(clearance["errors"])
        result["clearance"] = {
            "min_distance_mm": clearance["min_distance_mm"],
            "components": clearance["components"],
            "touching": clearance["touching"],
        }
    else:
        result["clearance"] = {
            "min_distance_mm": clearance["min_distance_mm"],
            "components": clearance["components"],
            "touching": clearance["touching"],
        }
        result["ok"] = True

    return result


def read_face_pair_clearance(
    doc: Any,
    face_a_name: str,
    face_b_name: str,
    mod: Any = None,
) -> dict[str, Any]:
    """Measure the minimum distance between two named faces (W52).

    Pipeline:
      1. ``IModelDoc2.SelectByID2(face_a_name, "FACE", ...)``, Append=False.
      2. ``SelectByID2(face_b_name, "FACE", ..., Append=True)``.
      3. ``CreateMeasure`` → ``Calculate(None)`` → ``Distance``.

    Returns dict with:
      - min_distance_mm (float | None) — None when touching or overlapping.
      - faces (list[str]) — [face_a_name, face_b_name].
      - touching (bool) — True if Distance returned -1.0.
      - errors (list[str]).
    """
    result: dict[str, Any] = {
        "min_distance_mm": None,
        "faces": [face_a_name, face_b_name],
        "touching": False,
        "errors": [],
    }

    if mod is None:
        mod = wrapper_module()

    if face_a_name == face_b_name:
        result["errors"].append("face_a and face_b are the same face")
        return result

    try:
        doc_typed = typed(doc, "IModelDoc2", module=mod)
    except Exception as exc:
        result["errors"].append(f"typed(IModelDoc2): {exc!r}")
        return result

    try:
        doc_typed.ClearSelection2(True)
    except Exception:
        pass

    try:
        ok_a = doc_typed.SelectByID2(face_a_name, "FACE", 0, 0, 0, False, 0, None, 0)
        if not ok_a:
            result["errors"].append(f"SelectByID2 failed for face {face_a_name!r}")
            return result
    except Exception as exc:
        result["errors"].append(f"SelectByID2({face_a_name!r}): {exc!r}")
        return result

    try:
        ok_b = doc_typed.SelectByID2(face_b_name, "FACE", 0, 0, 0, True, 0, None, 0)
        if not ok_b:
            result["errors"].append(f"SelectByID2 failed for face {face_b_name!r}")
            return result
    except Exception as exc:
        result["errors"].append(f"SelectByID2({face_b_name!r}): {exc!r}")
        return result

    measure = None
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

    try:
        dist = measure.Distance
        if callable(dist):
            dist = dist()
        if dist is not None:
            dist_f = float(dist)
            if dist_f == -1.0:
                result["touching"] = True
            else:
                result["min_distance_mm"] = dist_f * 1000.0
    except Exception as exc:
        result["errors"].append(f"Distance read: {exc!r}")

    return result


def sw_get_face_clearance(
    doc: Any, face_a_name: str, face_b_name: str
) -> dict[str, Any]:
    """Top-level observer: min distance between two named faces (W52).

    Returns structured report:
    ``{"ok": bool, "clearance": {...}, "error": str|None}``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "clearance": None,
    }

    mod = wrapper_module()
    clearance = read_face_pair_clearance(doc, face_a_name, face_b_name, mod)

    if clearance["errors"]:
        result["error"] = "; ".join(clearance["errors"])
        result["clearance"] = {
            "min_distance_mm": clearance["min_distance_mm"],
            "faces": clearance["faces"],
            "touching": clearance["touching"],
        }
    else:
        result["clearance"] = {
            "min_distance_mm": clearance["min_distance_mm"],
            "faces": clearance["faces"],
            "touching": clearance["touching"],
        }
        result["ok"] = True

    return result
