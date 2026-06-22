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


def _gap_of(clr: dict[str, Any]) -> tuple[float | None, bool, str | None]:
    """Reduce a :func:`read_clearance` result to ``(gap_mm, touching, error)``.

    ``touching`` (Distance == -1.0, flush/overlap) maps to a ``0.0`` gap so a
    flush stack still accumulates. An unmeasurable pair (component not found,
    measure error) yields ``(None, touching, error_str)``.
    """
    touching = bool(clr.get("touching"))
    err = "; ".join(clr["errors"]) if clr.get("errors") else None
    if touching:
        return 0.0, True, err
    dist = clr.get("min_distance_mm")
    if dist is not None and err is None:
        return float(dist), False, None
    return None, touching, err


def analyze_stackup(
    asm_doc: Any,
    component_names: Any,
    *,
    check_endpoints: bool = True,
    mod: Any = None,
) -> dict[str, Any]:
    """Traverse an ORDERED component chain and accumulate the inter-component gaps.

    READ-ONLY orchestration verb (W77): composes the shipped
    :func:`read_clearance` primitive over CONSECUTIVE pairs of an ordered
    mechanical stack — ``c[0]↔c[1]``, ``c[1]↔c[2]``, … — and sums the measured
    gaps. It never mutates the model (selection + IMeasure only), so it is
    cleared for the MCP surface alongside the CLI.

    ``component_names`` is the ordered chain (``IComponent2.Name2`` values),
    e.g. ``["base-1", "spacer-1", "top-1"]``. At least two are required.

    The optional endpoint sanity check (``check_endpoints``, chains of ≥3) also
    measures the FIRST↔LAST component directly. For a clean collinear stack the
    end-to-end nearest-face distance spans the intervening BODIES too, so it
    must be **≥** the sum of the inter-component gaps — ``endpoint_span_mm`` is
    therefore reported as a *separate* datum (NOT asserted equal to the gap
    sum), and ``intervening_span_mm = endpoint_span − accumulated_gap`` is the
    cumulative body extent along the chain. ``linear_consistent`` is False only
    when the endpoint span is *shorter* than the accumulated gaps — physically
    impossible for a collinear stack, so it flags a non-linear / misaligned
    chain.

    Returns::

        {
          "ok": bool,                      # True iff ≥1 pair AND every pair measured
          "error": str | None,
          "chain": [name, ...],
          "pairs": [
            {"components": [a, b], "gap_mm": float|None,
             "touching": bool, "error": str|None}, ...
          ],
          "accumulated_gap_mm": float | None,   # Σ measured gaps (touching = 0)
          "accumulation_complete": bool,        # False if any pair unmeasurable
          "measured_pairs": int,
          "endpoint_span_mm": float | None,     # direct first↔last clearance
          "intervening_span_mm": float | None,  # endpoint_span − accumulated_gap
          "linear_consistent": bool | None,     # endpoint_span ≥ accumulated_gap
          "warnings": [str, ...],
        }
    """
    result: dict[str, Any] = {
        "ok": False,
        "error": None,
        "chain": [],
        "pairs": [],
        "accumulated_gap_mm": None,
        "accumulation_complete": False,
        "measured_pairs": 0,
        "endpoint_span_mm": None,
        "intervening_span_mm": None,
        "linear_consistent": None,
        "warnings": [],
    }

    # ── Input validation (fail fast, before any seat work) ───────────────
    if not isinstance(component_names, (list, tuple)):
        result["error"] = "component_names must be a list of component names"
        return result
    names = [str(n) for n in component_names]
    result["chain"] = names
    if len(names) < 2:
        result["error"] = "need >= 2 components to form a stack chain"
        return result
    if any(not n.strip() for n in names):
        result["error"] = "component names must be non-empty"
        return result

    if mod is None:
        mod = wrapper_module()

    # ── Traverse consecutive pairs ───────────────────────────────────────
    acc = 0.0
    measured = 0
    complete = True
    for a, b in zip(names, names[1:]):
        clr = read_clearance(asm_doc, a, b, mod)
        gap, touching, err = _gap_of(clr)
        result["pairs"].append({
            "components": [a, b],
            "gap_mm": gap,
            "touching": touching,
            "error": err,
        })
        if gap is None:
            complete = False
        else:
            acc += gap
            measured += 1

    result["measured_pairs"] = measured
    result["accumulation_complete"] = complete
    result["accumulated_gap_mm"] = round(acc, 6) if measured else None

    # ── Optional endpoint sanity check (chains of >= 3) ──────────────────
    if check_endpoints and len(names) >= 3:
        ec = read_clearance(asm_doc, names[0], names[-1], mod)
        span, _touch, _err = _gap_of(ec)
        result["endpoint_span_mm"] = span
        if span is not None and complete and result["accumulated_gap_mm"] is not None:
            acc_gap = result["accumulated_gap_mm"]
            result["intervening_span_mm"] = round(span - acc_gap, 6)
            result["linear_consistent"] = span + 1e-6 >= acc_gap
            if not result["linear_consistent"]:
                result["warnings"].append(
                    "endpoint span is shorter than the accumulated gaps — the "
                    "chain may be non-collinear or misaligned"
                )

    # ── Verdict ──────────────────────────────────────────────────────────
    if not complete:
        unmeasured = [p["components"] for p in result["pairs"] if p["gap_mm"] is None]
        result["error"] = f"unmeasurable pair(s): {unmeasured}"
        result["ok"] = False
    else:
        result["ok"] = True

    return result


def sw_analyze_stackup(
    doc: Any, component_names: Any, check_endpoints: bool = True
) -> dict[str, Any]:
    """Top-level observer: tolerance stack-up over an ordered component chain (W77).

    Validates *doc* is an assembly, then delegates to :func:`analyze_stackup`.
    Fail-closed: a non-assembly document returns ``ok=False`` with a typed
    error rather than silently mis-measuring.
    """
    try:
        doc_type = resolve(doc, "GetType")
        if callable(doc_type):
            doc_type = doc_type()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"doc.GetType failed: {exc!r}", "chain": []}

    if doc_type != SW_DOC_ASSEMBLY:
        return {
            "ok": False,
            "error": f"stack-up analysis requires assembly document (got type {doc_type})",
            "chain": list(component_names) if isinstance(component_names, (list, tuple)) else [],
        }

    return analyze_stackup(doc, component_names, check_endpoints=check_endpoints)
