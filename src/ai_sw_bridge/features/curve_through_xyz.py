"""W68 — ``curve_through_xyz`` feature-add handler (registry seam).

Curve through XYZ points — a reference curve defined by a sequence of absolute
3-D coordinates (the 4th curve type, sibling to shipped composite/helix/
project_curve — W62).

  **Mode-B (legacy, the operative path)**: the SW API exposes three IModelDoc2
  methods for free-form curve insertion —

    doc.InsertCurveFileBegin()  -> None
    doc.InsertCurveFilePoint(X, Y, Z) -> Boolean   (absolute coords in METRES)
    doc.InsertCurveFileEnd()    -> Boolean

  No pre-selection is required — points are absolute model-space coordinates.
  The recipe is: ``ClearSelection2(True)`` → ``InsertCurveFileBegin()`` →
  ``InsertCurveFilePoint(x_m, y_m, z_m)`` for each point →
  ``InsertCurveFileEnd()``.  All three Insert methods are subject to the
  callable-or-property invocation guard (win32com late-bound auto-invoke).

Verify-the-EFFECT (W21/W42 doctrine): success = a new reference-curve node
materialized in the feature tree (``IFeatureManager.GetFeatures(False)``
array-length delta) AND the curve carries real arc length (W67 P3b geometric
gate — node-count alone is the W42 ghost trap).  The CURVE verify class
mirrors composite / helix / project_curve.

UNKNOWNS (probed by spike_curve_through_xyz, resolved by W0 on the seat):
  (1) exact ``GetTypeName2`` of the new node (likely "RefCurve" or
      "CurveThroughPoints" — the spike logs it);
  (2) minimum point count the kernel accepts (>= 2 assumed).
"""

from __future__ import annotations

import logging
from typing import Any

from . import verify

logger = logging.getLogger("ai_sw_bridge.features.curve_through_xyz")

SPIKE_STATUS = "UNFIRED"

VERIFY_CLASS = verify.FeatureClass.CURVE


def _call_or_get(obj: Any, attr: str) -> Any:
    """Callable-or-property guard (rollback.py idiom)."""
    v = getattr(obj, attr)
    return v() if callable(v) else v


def _count_feature_nodes(doc: Any) -> int:
    """Flat feature-node count via ``GetFeatures(False)``.  Delegates to the
    W67 verify substrate."""
    return verify.feature_node_count(doc)


def _curve_length_mm(node: Any) -> float | None:
    """Arc length (mm) of the curve node, or None if unreadable.  Delegates to
    the W67 verify substrate (seat-proven IReferenceCurve.GetSegments →
    IEdge.GetCurve → ICurve.GetLength); offline tests patch this shim."""
    return verify.curve_length_mm(node)


def _try_mode_b(doc: Any, points_mm: list[list[float]]) -> Any:
    """Mode-B: InsertCurveFileBegin/Point/End pipeline.

    Returns a truthy sentinel on success (InsertCurveFileEnd returning True),
    None on any failure.  Points are converted mm→m here.
    """
    try:
        doc.ClearSelection2(True)
    except Exception as e:
        logger.warning("[B] ClearSelection2 RAISED: %r", e)
        return None

    try:
        _call_or_get(doc, "InsertCurveFileBegin")
    except Exception as e:
        logger.warning("[B] InsertCurveFileBegin RAISED: %r", e)
        return None

    for i, pt in enumerate(points_mm):
        x_m = pt[0] / 1000.0
        y_m = pt[1] / 1000.0
        z_m = pt[2] / 1000.0
        try:
            ins = doc.InsertCurveFilePoint
            result = ins(x_m, y_m, z_m) if callable(ins) else ins
        except Exception as e:
            logger.warning("[B] InsertCurveFilePoint[%d] RAISED: %r", i, e)
            return None
        logger.warning(
            "[B] InsertCurveFilePoint[%d](%g, %g, %g) -> %r",
            i, x_m, y_m, z_m, result,
        )
        if result is not None and not result:
            logger.warning("[B] InsertCurveFilePoint[%d] returned False", i)
            return None

    try:
        end = doc.InsertCurveFileEnd
        result = end() if callable(end) else end
    except Exception as e:
        logger.warning("[B] InsertCurveFileEnd RAISED: %r", e)
        return None
    logger.warning("[B] InsertCurveFileEnd (callable=%s) -> %r", callable(end), result)
    if result:
        return result
    return None


def create_curve_through_xyz(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Insert a reference curve through absolute XYZ points.  Fail-closed.

    Mode-B is the operative path: ``InsertCurveFileBegin`` → N ×
    ``InsertCurveFilePoint(x, y, z)`` → ``InsertCurveFileEnd``.  No Mode-A
    exists (no ``CreateDefinition`` route for free-form curves in the SW2024
    swconst harvest).

    ``feature`` keys
        (none — the curve is fully defined by the point list)

    ``target`` keys
        points : list[list[float]]  — ≥ 2 points, each ``[x_mm, y_mm, z_mm]``
            (millimetres; converted to metres for the SW API call).
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    points = target.get("points")
    if not isinstance(points, list) or len(points) < 2:
        return False, "target must contain a 'points' list with >= 2 entries"

    for i, pt in enumerate(points):
        if not isinstance(pt, (list, tuple)) or len(pt) != 3:
            return False, f"point[{i}] must be a 3-number list [x, y, z]"
        try:
            float(pt[0])
            float(pt[1])
            float(pt[2])
        except (TypeError, ValueError):
            return False, f"point[{i}] contains a non-numeric coordinate"

    nodes_before = _count_feature_nodes(doc)

    feat = _try_mode_b(doc, points)
    if feat is None:
        return False, (
            "Mode-B (InsertCurveFileBegin/Point/End) failed — "
            "no curve inserted"
        )

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    nodes_after = _count_feature_nodes(doc)
    d_nodes = nodes_after - nodes_before
    if d_nodes <= 0:
        return False, (
            "Mode-B returned but no feature node materialized (ghost trap)"
        )

    new_node = verify.newest_node_by_type(
        doc, ("refcurve", "curve"), match="substring",
    )
    length_mm = _curve_length_mm(new_node)
    if verify.gate_curve(d_nodes, length_mm):
        return True, "curve_through_xyz created via Mode-B"
    return False, (
        f"a curve node materialized but carries no readable arc length "
        f"(curve_length_mm={length_mm}) — geometric ghost, not a real curve"
    )
