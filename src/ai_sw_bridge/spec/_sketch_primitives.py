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
    axis of revolution. Centerline endpoint coords are in part-frame mm;
    the third (out-of-plane) component is informational for the spec
    author but ignored when calling SW -- SW's CreateCenterLine inside an
    open non-Front sketch interprets its args as sketch-local 2D, so we
    remap `(part_X, part_Y, part_Z)` to the parent sketch's two in-plane
    axes before the COM call.

    Front Plane: sketch_X = part_X, sketch_Y = part_Y, part_Z ignored.
    Top   Plane: sketch_X = part_X, sketch_Y = part_Z, part_Y ignored.
    Right Plane: sketch_X = part_Y, sketch_Y = part_Z, part_X ignored.

    Front Plane behavior preserved bit-for-bit for legacy specs lacking
    a `z` field (defaults to 0, dropped by the remap)."""
    cl = feat.get("centerline")
    if cl is None:
        return
    plane = feat.get("plane", "Front")
    px1 = float(cl["start"]["x"]) / 1000.0
    py1 = float(cl["start"]["y"]) / 1000.0
    pz1 = float(cl["start"].get("z", 0.0)) / 1000.0
    px2 = float(cl["end"]["x"]) / 1000.0
    py2 = float(cl["end"]["y"]) / 1000.0
    pz2 = float(cl["end"].get("z", 0.0)) / 1000.0
    # Sketch-axis sign convention: see rectangle_on_plane._draw_geometry.
    # Top Plane sketch_Y = -part_Z.
    if plane == "Front":
        sx1, sy1, sx2, sy2 = px1, py1, px2, py2
    elif plane == "Top":
        sx1, sy1, sx2, sy2 = px1, -pz1, px2, -pz2
    else:  # Right
        sx1, sy1, sx2, sy2 = pz1, py1, pz2, py2
    seg = sm.CreateCenterLine(sx1, sy1, 0.0, sx2, sy2, 0.0)
    if seg is None:
        raise RuntimeError(
            f"CreateCenterLine returned None for sketch '{feat.get('name')}'"
        )


def _identify_rect_edge(rect_segs: Any, which: str) -> Any:
    """Find the requested edge (horiz_top, horiz_bot, vert_left, vert_right) from
    the segment tuple CreateCenterRectangle returns. Uses each segment's
    GetStartPoint2/GetEndPoint2 to classify by orientation and position.

    The center used for top/bot and left/right disambiguation is computed
    from the segments themselves (average of horizontal segments' Y for the
    Y-center, average of vertical segments' X for the X-center), so this
    function works regardless of which reference plane the sketch is on --
    GetStartPoint2/.GetEndPoint2 always return sketch-local 2D coords.

    Returns the matching ISketchSegment, or None if not found. Skips
    construction-geometry segments (the two diagonals).
    """
    if rect_segs is None:
        return None
    target_horiz = which.startswith("horiz")
    target_top = which.endswith("_top")
    target_left = which.endswith("_left")

    horiz_ys: list[float] = []
    vert_xs: list[float] = []
    edges: list[tuple[bool, bool, float, float, Any]] = []
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
            if is_horiz:
                horiz_ys.append(y1)
            if is_vert:
                vert_xs.append(x1)
            edges.append((is_horiz, is_vert, x1, y1, s))
        except Exception:
            continue

    y_mid = sum(horiz_ys) / len(horiz_ys) if horiz_ys else 0.0
    x_mid = sum(vert_xs) / len(vert_xs) if vert_xs else 0.0

    for is_horiz, is_vert, x1, y1, s in edges:
        if target_horiz and is_horiz:
            if (target_top and y1 > y_mid) or (not target_top and y1 < y_mid):
                return s
        elif not target_horiz and is_vert:
            if (target_left and x1 < x_mid) or (not target_left and x1 > x_mid):
                return s
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


def create_parabola(
    sm: Any,
    x_focal_mm: float,
    y_focal_mm: float,
    z_focal_mm: float,
    x_vertex_mm: float,
    y_vertex_mm: float,
    z_vertex_mm: float,
    x_end1_mm: float,
    y_end1_mm: float,
    z_end1_mm: float,
    x_end2_mm: float,
    y_end2_mm: float,
    z_end2_mm: float,
) -> Any:
    """Create a parabola sketch segment via ``ISketchManager.CreateParabola``.

    Seat-validated on SW 2024 SP1 (rev 32.1.0): the method takes **12 args**
    — focal point (xyz), vertex (xyz), and two endpoints (xyz) — all in
    model metres.  An 8-arg call raises ``DISP_E_BADPARAMCOUNT``.

    All coordinate inputs are in **millimetres** (spec-layer convention);
    converted to metres internally before the COM call.

    Returns the ``ISketchSegment`` handle.  Raises ``RuntimeError`` if
    SW returns None (under-defined or degenerate parabola).
    """
    seg = sm.CreateParabola(
        _mm_to_m(x_focal_mm),
        _mm_to_m(y_focal_mm),
        _mm_to_m(z_focal_mm),
        _mm_to_m(x_vertex_mm),
        _mm_to_m(y_vertex_mm),
        _mm_to_m(z_vertex_mm),
        _mm_to_m(x_end1_mm),
        _mm_to_m(y_end1_mm),
        _mm_to_m(z_end1_mm),
        _mm_to_m(x_end2_mm),
        _mm_to_m(y_end2_mm),
        _mm_to_m(z_end2_mm),
    )
    if seg is None:
        raise RuntimeError(
            "CreateParabola returned None (under-defined or degenerate parabola)"
        )
    return seg
