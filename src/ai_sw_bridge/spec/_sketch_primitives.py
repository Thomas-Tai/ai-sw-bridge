"""SOLIDWORKS-COM sketch primitives shared by sketch handlers.

Small verbs used by the sketch handlers in ``sketches/`` (and by
``_build_revolve_boss`` in ``builder.py``): length-with-placeholder helper,
PM-pane dismiss stub, centerline drawer, rectangle-edge identifier, and the
Spike ZF spurious-Midpoint-relation strip.
"""

from __future__ import annotations

from typing import Any


# Placeholder geometry sizes (mm) used when a length field is {rhs}-bound.
# Geometry is created at the placeholder size; the actual dim is set by the
# subsequent EquationMgr.Add2 call. Any nonzero value works; these were
# picked to be visually plausible during a failed mid-build inspection.
PLACEHOLDER_MM = {
    "rectangle_side": 10.0,
    "circle_diameter_plane": 10.0,
    "circle_diameter_face": 6.0,
    "circle_diameter_multi": 4.0,
    "extrude_depth": 5.0,
    "cut_depth": 5.0,
    "hole_diameter": 4.0,
    "hole_depth": 5.0,
}


# swConstraintType_e enum (the subset we observe on CenterRectangle)
_SW_CONSTRAINT_MIDPOINT_2D = 14


def _mm_to_m(value: Any) -> float:
    """Convert a length value (number mm) to meters. Caller must pass a literal
    number, not an {rhs} object - rhs is resolved by binding after creation."""
    if not isinstance(value, (int, float)):
        raise TypeError(
            f"_mm_to_m got {type(value).__name__}; expected literal number. "
            f"Caller forgot to extract literal vs rhs branch."
        )
    return float(value) / 1000.0


def _is_rhs(length_value: Any) -> bool:
    return isinstance(length_value, dict) and "rhs" in length_value


def _literal_or_default(length_value: Any, default_mm: float) -> float:
    """If length is a literal, return its value in meters. If it's an {rhs}
    object, return the placeholder default in meters - the actual binding
    happens later via Add2 (after the feature exists)."""
    if _is_rhs(length_value):
        return default_mm / 1000.0
    return _mm_to_m(length_value)


def _dismiss_dim_pane(doc: Any) -> None:
    """Reserved for v1.1 — currently a no-op.

    KNOWN ISSUE: After AddDimension2, SW opens a Dimension PropertyManager
    pane on the left side. The floating Modify popup is suppressed via
    swInputDimValOnCreate=False, but the side pane is NOT. Initial attempt
    to dismiss via RunCommand(-1) instead RE-ENABLED the popup on a doc
    that had previously worked (cylinder regression). Reverted to no-op.

    Until the proper API is found, leave the pane open; it accumulates
    state but does not appear to block subsequent COM calls when the
    floating popup is suppressed at the app level (cylinder previously
    succeeded end-to-end). MMP exposes a different failure mode that may
    be the cut-feature, not the pane.
    """
    return


def _draw_centerline_if_present(sm: Any, feat: dict[str, Any]) -> None:
    """If the sketch spec has a `centerline` field, draw it as a construction
    line in the currently open sketch via ISketchManager.CreateCenterLine.

    Used by plane-based sketch handlers (rectangle, circle) to embed an
    axis of revolution. Coordinates are sketch-local mm, converted to m.
    Verified working under pywin32 late-binding in Spike X (2026-05-19)."""
    cl = feat.get("centerline")
    if cl is None:
        return
    x1 = float(cl["start"]["x"]) / 1000.0
    y1 = float(cl["start"]["y"]) / 1000.0
    x2 = float(cl["end"]["x"]) / 1000.0
    y2 = float(cl["end"]["y"]) / 1000.0
    seg = sm.CreateCenterLine(x1, y1, 0.0, x2, y2, 0.0)
    if seg is None:
        raise RuntimeError(
            f"CreateCenterLine returned None for sketch '{feat.get('name')}'"
        )


def _identify_rect_edge(rect_segs: Any, which: str, cx_m: float, cy_m: float) -> Any:
    """Find the requested edge (horiz_top, horiz_bot, vert_left, vert_right) from
    the segment tuple CreateCenterRectangle returns. Uses each segment's
    GetStartPoint2/GetEndPoint2 to classify by orientation and position.

    Returns the matching ISketchSegment, or None if not found. Skips
    construction-geometry segments (the two diagonals).
    """
    if rect_segs is None:
        return None
    target_horiz = which.startswith("horiz")
    target_top = which.endswith("_top")
    target_left = which.endswith("_left")
    for s in rect_segs:
        try:
            if s.ConstructionGeometry:
                continue
            sp, ep = s.GetStartPoint2, s.GetEndPoint2
            if sp is None or ep is None:
                continue
            x1, y1 = sp.X, sp.Y
            x2, y2 = ep.X, ep.Y
            is_horiz = abs(y1 - y2) < 1e-9
            is_vert = abs(x1 - x2) < 1e-9
            if target_horiz and is_horiz:
                # Top: y > cy_m. Bot: y < cy_m.
                if (target_top and y1 > cy_m) or (not target_top and y1 < cy_m):
                    return s
            elif not target_horiz and is_vert:
                # Left: x < cx_m. Right: x > cx_m.
                if (target_left and x1 < cx_m) or (not target_left and x1 > cx_m):
                    return s
        except Exception:
            continue
    return None


def _strip_centerrectangle_midpoint_relation(doc: Any) -> bool:
    """Delete the spurious Midpoint relation that API-side CreateCenterRectangle
    adds but UI-side CenterRectangle does not.

    This relation pins the diagonal-midpoint to the part origin, removing one
    DOF and forcing a square-collapse (D2 becomes redundant/driven once D1 is
    placed). Empirically verified 2026-05-20 against SW 2024 SP1: deleting
    this relation before adding dims makes D1 and D2 land independently
    driving, AND the rectangle still stays centered on origin under driven
    resizing (SW's solver defaults to symmetric placement).

    See [spike_zf in the deferred-dim investigation] for the full evidence
    trail.

    Must be called inside the open sketch session, immediately after
    sm.CreateCenterRectangle(...) and before any AddDimension2 call.

    Returns True if a Midpoint relation was found and deleted; False if no
    Midpoint relation was present (e.g. SW version behaved like the UI by
    default, or the sketch is empty).
    """
    sk = doc.GetActiveSketch2
    if sk is None:
        return False
    try:
        rm = sk.RelationManager
    except Exception:
        return False
    if rm is None:
        return False
    rels = rm.GetRelations(0)
    if not rels:
        return False
    for r in rels:
        try:
            if r.GetRelationType == _SW_CONSTRAINT_MIDPOINT_2D:
                rm.DeleteRelation(r)
                return True
        except Exception:
            continue
    return False
