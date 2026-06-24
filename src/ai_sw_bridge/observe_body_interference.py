"""Read-only ``body_interference`` observe lane — multibody-PART interference.

The parts complement to the W27 assembly ``interference()`` lane: detects where
two solid BODIES within a single multibody part physically clash. Assemblies and
multibody parts have fundamentally different data models (Components vs Bodies),
so this is a DISTINCT lane with its own schema — never folded into the
component-level ``interference()``.

Measure-first reconnaissance (probe_body_interference, live SW2024 SP1,
2026-06-24):

  * ``IModelDocExtension.GetInterferenceEdges`` — PHANTOM (does not exist in the
    SW2024 DLL, like ``CheckModel``).
  * ``IBody2.GetIntersectionEdges(ToolBodyIn) -> Object`` — body-body
    intersection edges. ``count > 0`` is the read-only clash signal. Probe:
    overlapping boxes -> 20 edges, disjoint -> 0. Perfect discrimination.
  * Interference VOLUME, read-only and mathematically exact, via temp detached
    bodies: ``IBody2.Copy()`` -> ``Operations2(SWBODYINTERSECT=15901, tool, err)``
    -> ``GetMassProperties(density)[3]`` (m^3 -> mm^3 x1e9). Probe: the 20^3 mm
    shared region measured 8000.0 mm^3 EXACTLY, with the document unmutated.
  * Body name via ``IBody2.Name``.

Read-only contract is enforced two ways: (1) all boolean math runs on ``Copy()``
temp bodies, never document bodies; (2) a mutation guard asserts the document's
solid-body count is identical before and after.

O(N^2) hazard: pairwise checks scale combinatorially and SW COM calls are slow.
Above ``_PAIRWISE_WARN_THRESHOLD`` bodies we LOG the pairwise count (never hard-
cap or fail) so a consumer running it on a 200-body lattice knows why it blocks.
"""

from __future__ import annotations

import logging
from typing import Any

from .com.earlybind import typed
from .com.sw_type_info import wrapper_module
from .sw_com import (
    DOC_TYPE_NAMES,
    SW_DOC_PART,
    get_active_doc,
    get_sw_app,
    resolve,
)

logger = logging.getLogger("ai_sw_bridge.observe_body_interference")

# swBodyOperationType_e.SWBODYINTERSECT — boolean common (the shared volume).
_SWBODYINTERSECT = 15901
# swBodyType_e.swSolidBody
_SW_SOLID_BODY = 0
# IBody2.GetMassProperties(density) -> [cx,cy,cz, VOLUME, area, mass, ...]
_VOLUME_INDEX = 3
# Above this body count, log the O(N^2) pairwise count (don't cap/fail).
_PAIRWISE_WARN_THRESHOLD = 50


def _body_name(body: Any) -> str | None:
    for attr in ("Name", "Name2"):
        try:
            v = getattr(body, attr)
            return str(v() if callable(v) else v)
        except Exception:
            continue
    return None


def _intersection_edge_count(a: Any, b: Any) -> tuple[int | None, str | None]:
    """IBody2.GetIntersectionEdges(b) -> count of intersection edges (clash
    signal). Returns (count, error)."""
    try:
        edges = a.GetIntersectionEdges(b)
    except Exception as exc:  # noqa: BLE001
        return None, f"GetIntersectionEdges: {exc!r}"
    if edges is None:
        return 0, None
    if isinstance(edges, (list, tuple)):
        return len(edges), None
    return 1, None


def _intersection_volume_mm3(a: Any, b: Any) -> tuple[float | None, str | None]:
    """Read-only interference volume via temp-body boolean COMMON:
    a.Copy() -> Operations2(SWBODYINTERSECT, b.Copy()) -> GetMassProperties.
    Operates on DETACHED temp bodies, so the document is never mutated."""
    try:
        ta = a.Copy()
        tb = b.Copy()
    except Exception as exc:  # noqa: BLE001
        return None, f"Body.Copy: {exc!r}"
    try:
        res = ta.Operations2(_SWBODYINTERSECT, tb, 0)
    except Exception as exc:  # noqa: BLE001
        return None, f"Operations2(SWBODYINTERSECT): {exc!r}"
    bodies = res[0] if isinstance(res, tuple) else res
    if bodies is None:
        return 0.0, None
    if not isinstance(bodies, (list, tuple)):
        bodies = (bodies,)
    total_m3 = 0.0
    for rb in bodies:
        try:
            mp = rb.GetMassProperties(0.0)
            if mp is not None and len(mp) > _VOLUME_INDEX:
                total_m3 += float(mp[_VOLUME_INDEX])
        except Exception as exc:  # noqa: BLE001
            return None, f"GetMassProperties: {exc!r}"
    return total_m3 * 1e9, None


def _solid_body_count(doc: Any) -> int | None:
    try:
        bodies = doc.GetBodies2(_SW_SOLID_BODY, False)
        return len(bodies) if bodies else 0
    except Exception:
        return None


def _sw_get_body_interference_impl() -> dict[str, Any]:
    """v1 core — pairwise solid-body interference for the active multibody part.

    Keys:
      ``body_count`` — solid bodies in the part.
      ``pairwise_checks`` — N*(N-1)/2 (the O(N^2) work performed).
      ``interfering_pair_count`` — pairs whose GetIntersectionEdges count > 0.
      ``total_interference_volume_mm3`` — summed boolean-common volume.
      ``pairs`` — ``[{body_a, body_b, intersection_edge_count,
        interference_volume_mm3}]`` for clashing pairs only.
      ``clean`` — bool: no interfering pairs.
      ``mutation_guard_ok`` — bool: solid-body count unchanged (read-only proof).

    Parts only (the assembly complement is ``interference()``). Fail-soft:
    per-pair failures land in ``errors``; the load-bearing read is the body count.
    """
    result: dict[str, Any] = {
        "ok": False,
        "doc_path": None,
        "body_count": None,
        "pairwise_checks": None,
        "interfering_pair_count": None,
        "total_interference_volume_mm3": None,
        "pairs": None,
        "clean": None,
        "mutation_guard_ok": None,
        "error": None,
        "errors": [],
    }
    try:
        sw = get_sw_app()
        doc = get_active_doc(sw)
        if doc is None:
            result["error"] = "no_active_doc"
            return result
        try:
            result["doc_path"] = str(resolve(doc, "GetPathName"))
        except Exception:
            pass

        try:
            doc_type = int(resolve(doc, "GetType"))
        except Exception as exc:
            result["error"] = f"GetType failed: {exc!r}"
            return result
        if doc_type != SW_DOC_PART:
            result["error"] = (
                f"body_interference requires a part (swDocPART={SW_DOC_PART}); "
                f"active doc is type {doc_type} ({DOC_TYPE_NAMES.get(doc_type)}). "
                f"For assemblies use observe.interference()."
            )
            return result

        mod = wrapper_module()
        try:
            raw_bodies = doc.GetBodies2(_SW_SOLID_BODY, False) or ()
        except Exception as exc:
            result["error"] = f"GetBodies2 failed: {exc!r}"
            return result
        raw_bodies = list(raw_bodies)
        n = len(raw_bodies)
        result["body_count"] = n
        body_count_before = n
        pairwise = n * (n - 1) // 2
        result["pairwise_checks"] = pairwise

        # O(N^2) safeguard — log, never cap/fail.
        if n > _PAIRWISE_WARN_THRESHOLD:
            logger.warning(
                "body_interference: %d solid bodies => %d pairwise "
                "GetIntersectionEdges checks; SW COM interop may block for a "
                "while on this part.",
                n,
                pairwise,
            )

        # Fewer than 2 bodies -> no possible interference (vacuously clean).
        if n < 2:
            result["interfering_pair_count"] = 0
            result["total_interference_volume_mm3"] = 0.0
            result["pairs"] = []
            result["clean"] = True
            result["mutation_guard_ok"] = True
            result["ok"] = True
            return result

        # Type bodies to IBody2 for GetIntersectionEdges/Copy/Operations2.
        typed_bodies: list[Any] = []
        names: list[str | None] = []
        for b in raw_bodies:
            try:
                tb = typed(b, "IBody2", module=mod)
            except Exception:
                tb = b
            typed_bodies.append(tb)
            names.append(_body_name(tb))

        pairs: list[dict[str, Any]] = []
        total_vol = 0.0
        vol_complete = True
        for i in range(n):
            for j in range(i + 1, n):
                count, cerr = _intersection_edge_count(typed_bodies[i], typed_bodies[j])
                if cerr is not None:
                    result["errors"].append(f"pair({names[i]},{names[j]}): {cerr}")
                    continue
                if not count:
                    continue  # no clash
                vol_mm3, verr = _intersection_volume_mm3(
                    typed_bodies[i], typed_bodies[j]
                )
                if verr is not None:
                    result["errors"].append(
                        f"pair({names[i]},{names[j]}) volume: {verr}"
                    )
                    vol_complete = False
                elif vol_mm3 is not None:
                    total_vol += vol_mm3
                pairs.append(
                    {
                        "body_a": names[i],
                        "body_b": names[j],
                        "intersection_edge_count": count,
                        "interference_volume_mm3": vol_mm3,
                    }
                )

        result["pairs"] = pairs
        result["interfering_pair_count"] = len(pairs)
        result["total_interference_volume_mm3"] = total_vol if vol_complete else None
        result["clean"] = len(pairs) == 0

        # Mutation guard — the read-only proof: temp-body math must not have
        # touched the document's body set.
        body_count_after = _solid_body_count(doc)
        result["mutation_guard_ok"] = body_count_after == body_count_before
        if not result["mutation_guard_ok"]:
            result["errors"].append(
                f"mutation guard TRIPPED: solid body count {body_count_before} "
                f"-> {body_count_after} (boolean math leaked into the document)"
            )

        result["ok"] = bool(result["mutation_guard_ok"])
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"dispatch failed: {exc!r}"
        return result
