"""Sketch-primitive family handlers, relocated from builder.py (Phase 3 Move 5).

The eight ``_build_sketch_*`` handlers (line/arc/spline/slot/polygon/ellipse/
text/3d_sketch) plus their eight shared helpers (`_enter_plane_sketch`,
`_close_plane_sketch_and_build`, `_apply_construction`, `_segments`,
`_enter_3d_sketch`, `_close_3d_sketch_and_build`, `_as_sketch_text`,
`_apply_text_format`). Leaf module: imports only `.._build_context`,
`.._face_geometry`, `._common` -- never builder.py or a sibling handler
module.

Each handler follows the same life-cycle: select reference plane ->
InsertSketch -> call the proven ISketchManager.Create* (or
IModelDoc2.InsertSketchText) -> close sketch -> rename the new sketch
feature -> return BuiltFeature. Coordinates are interpreted SKETCH-LOCAL 2D
(the spec gives 2D x/y on a named plane), so no part-frame projection is
applied (unlike circle_on_plane, whose `center` is part-frame). Parametric
({rhs}) dimensioning is deferred to a later pass; {rhs} fields resolve to
literal numbers before any handler runs in no_dim.

Proven live signatures (all confirmed materialising a segment on the seat):
  line     sm.CreateLine(x1,y1,z1, x2,y2,z2)
  arc      sm.CreateArc(cx,cy,cz, sx,sy,sz, ex,ey,ez, direction)  dir +1 ccw / -1 cw
  ellipse  sm.CreateEllipse(cx,cy,cz, majX,majY,majZ, minX,minY,minZ)
  polygon  sm.CreatePolygon(cx,cy,cz, px,py,pz, sides:int, inscribed:bool)
  spline   sm.CreateSpline2(VARIANT(VT_ARRAY|VT_R8)[flat x,y,z triples], False)
  slot     sm.CreateSketchSlot(ct:int, lt:int, width, x1,y1,z1, x2,y2,z2,
                               x3,y3,z3, addDim:bool, centerline:bool)
  text     doc.InsertSketchText(x,y,z, content, alignment:int, flip:int,
                               hmirror:int, widthFactor:int, spaceChars:int)
           then height/font via ISketchText.GetTextFormat -> SetTextFormat(0,tf)

Full-fidelity flags (P1.7-fidelity): `construction` marks the created
segment(s) via ISketchSegment.ConstructionGeometry (line/arc/spline/polygon/
ellipse -- seat-proven). Unsupported-on-seat requests are rejected loudly, not
faked: spline `closed`, slot `construction`, text `construction`/`angle_deg`.
"""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext, BuiltFeature
from .._face_geometry import PLANE_FULL_NAME
from ._common import _mm_to_m, _r8_safearray


def _enter_plane_sketch(ctx: BuildContext, feat: dict[str, Any]) -> Any:
    """Select the named reference plane and open a sketch; return SketchManager."""
    full = PLANE_FULL_NAME[feat["plane"]]
    if not ctx.doc.SelectByID(full, "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError(f"could not select {full}")
    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)
    return sm


def _close_plane_sketch_and_build(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Close the open sketch, rename the new sketch feature, return BuiltFeature."""
    ctx.doc.SketchManager.InsertSketch(True)
    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError(f"no sketch feature produced for '{feat['name']}'")
    sketch_feat.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=sketch_feat)


def _segments(result: Any) -> list[Any]:
    """Normalise an ``ISketchManager.Create*`` return into a list of segments.

    Single-segment creators (line/arc/spline/ellipse) return one
    ``ISketchSegment``; ``CreatePolygon`` returns a tuple of segments. A real
    segment exposes the settable ``ConstructionGeometry`` property, so that
    attribute discriminates a lone segment from a collection.
    """
    if result is None:
        return []
    if hasattr(result, "ConstructionGeometry"):
        return [result]
    try:
        return list(result)
    except TypeError:
        return [result]


def _apply_construction(result: Any, feat: dict[str, Any]) -> None:
    """Mark the created segment(s) as construction geometry when requested.

    Seat-proven on line/arc/spline/polygon/ellipse -- every returned segment
    accepts ``ConstructionGeometry = True``. Slot and text never reach here:
    their handlers reject ``construction`` (``CreateSketchSlot``'s return is a
    read-only slot object; text is not a segment).
    """
    if not feat.get("construction"):
        return
    for seg in _segments(result):
        seg.ConstructionGeometry = True


def _as_sketch_text(raw_text: Any) -> Any:
    """typed-wrap an ``InsertSketchText`` return as ``ISketchText``.

    The early-bind escape hatch: the raw return is a generic ``IDispatch`` that
    late binding cannot format (``GetTextFormat`` → "Member not found"); the
    typed wrap forces the real interface. The pywin32-dependent import is
    function-local (and this is a module-level seam) so builder stays importable
    and the text-format logic is unit-testable without SOLIDWORKS.
    """
    from ai_sw_bridge.com.earlybind import typed

    return typed(raw_text, "ISketchText")


def _apply_text_format(raw_text: Any, feat: dict[str, Any]) -> None:
    """Apply ``height`` (CharHeight, metres) and ``font`` (TypeFaceName).

    Seat-proven (SW 2024): ``ISketchText.GetTextFormat()`` → mutate the format
    object → ``SetTextFormat(0, tf)``. ``height`` is required; ``font`` is
    optional (document default kept when absent).
    """
    st = _as_sketch_text(raw_text)
    tf = st.GetTextFormat()
    tf.CharHeight = _mm_to_m(feat["height"])
    font = feat.get("font")
    if font:
        tf.TypeFaceName = str(font)
    st.SetTextFormat(0, tf)


def _build_sketch_line(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch a single line segment on a reference plane.

    Seat-proven: ``ISketchManager.CreateLine(x1, y1, z1, x2, y2, z2)``.
    """
    start, end = feat["start"], feat["end"]
    sm = _enter_plane_sketch(ctx, feat)
    seg = sm.CreateLine(
        _mm_to_m(start["x"]),
        _mm_to_m(start["y"]),
        0.0,
        _mm_to_m(end["x"]),
        _mm_to_m(end["y"]),
        0.0,
    )
    _apply_construction(seg, feat)
    return _close_plane_sketch_and_build(ctx, feat)


def _build_sketch_arc(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch a circular arc (center + start + end) on a reference plane.

    Seat-proven: ``ISketchManager.CreateArc(cx,cy,cz, sx,sy,sz, ex,ey,ez, dir)``
    where ``dir`` is +1 (counter-clockwise) or -1 (clockwise).
    """
    c, s, e = feat["center"], feat["start"], feat["end"]
    direction = 1 if str(feat.get("direction", "ccw")).lower() == "ccw" else -1
    sm = _enter_plane_sketch(ctx, feat)
    seg = sm.CreateArc(
        _mm_to_m(c["x"]),
        _mm_to_m(c["y"]),
        0.0,
        _mm_to_m(s["x"]),
        _mm_to_m(s["y"]),
        0.0,
        _mm_to_m(e["x"]),
        _mm_to_m(e["y"]),
        0.0,
        direction,
    )
    _apply_construction(seg, feat)
    return _close_plane_sketch_and_build(ctx, feat)


def _build_sketch_spline(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch a spline through a sequence of control points.

    Seat-proven: ``ISketchManager.CreateSpline2(pointBuffer, b3D=False)`` where
    ``pointBuffer`` is a ``VT_ARRAY|VT_R8`` SAFEARRAY of flat ``x,y,z`` triples
    (z=0 on a plane). Open splines only -- a point-based periodic (C2) closed
    spline has no out-of-process API on this seat (``MakeClosed`` /
    ``CreateClosedSpline`` absent; appending the first point gives a C0 cusp),
    so a ``closed`` request is rejected loudly rather than faked.
    """
    if feat.get("closed"):
        raise NotImplementedError(
            "Periodic closed splines are not supported out-of-process on this "
            "SOLIDWORKS version (no MakeClosed/CreateClosedSpline; appending the "
            "first point yields a C0 cusp, not a periodic spline). Remove "
            "'closed' and use a standard open spline."
        )
    points = feat["points"]
    flat: list[float] = []
    for p in points:
        flat.extend([_mm_to_m(p["x"]), _mm_to_m(p["y"]), _mm_to_m(p.get("z", 0.0))])
    sm = _enter_plane_sketch(ctx, feat)
    seg = sm.CreateSpline2(_r8_safearray(flat), False)
    _apply_construction(seg, feat)
    return _close_plane_sketch_and_build(ctx, feat)


def _build_sketch_slot(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch an arc-ended (round) slot on a reference plane.

    Seat-proven: ``ISketchManager.CreateSketchSlot(creationType:int,
    lengthType:int, width, x1,y1,z1, x2,y2,z2, x3,y3,z3, addDim:bool,
    centerline:bool)`` -- 14 scalars (NOT a point SAFEARRAY). ``creationType``/
    ``lengthType`` MUST be int (VT_I4) or SW raises "Type mismatch".

    The spec's ``center``/``length``/``width``/``angle_deg`` are converted to
    the two centreline endpoints P1/P2 (``length`` apart, centred on ``center``,
    rotated by ``angle_deg``) and the width-defining point P3.
    """
    import math

    if feat.get("construction") is True:
        raise NotImplementedError(
            "CreateSketchSlot returns a read-only slot object; construction "
            "geometry cannot be set on it via the API. Remove 'construction' "
            "from the slot spec."
        )
    c = feat["center"]
    cx, cy = _mm_to_m(c["x"]), _mm_to_m(c["y"])
    width = _mm_to_m(feat["width"])
    length = _mm_to_m(feat["length"])
    angle = math.radians(float(feat.get("angle_deg", 0.0)))
    dx, dy = math.cos(angle), math.sin(angle)
    px, py = -dy, dx  # in-plane perpendicular to the centreline
    half = length / 2.0
    x1, y1 = cx - half * dx, cy - half * dy
    x2, y2 = cx + half * dx, cy + half * dy
    x3, y3 = x2 + (width / 2.0) * px, y2 + (width / 2.0) * py
    sm = _enter_plane_sketch(ctx, feat)
    sm.CreateSketchSlot(
        0,
        0,
        width,
        x1,
        y1,
        0.0,
        x2,
        y2,
        0.0,
        x3,
        y3,
        0.0,
        False,
        True,
    )
    return _close_plane_sketch_and_build(ctx, feat)


def _build_sketch_polygon(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch a regular N-sided polygon on a reference plane.

    Seat-proven: ``ISketchManager.CreatePolygon(cx,cy,cz, px,py,pz, sides:int,
    inscribed:bool)`` returning an array of segments. ``(px,py)`` is a point on
    the construction circle at ``radius`` and ``angle_deg`` from the centre;
    ``inscribed`` True = radius to vertices, False = radius to edge midpoints.
    """
    import math

    c = feat["center"]
    cx, cy = _mm_to_m(c["x"]), _mm_to_m(c["y"])
    sides = int(feat["sides"])
    radius = _mm_to_m(feat["radius"])
    inscribed = bool(feat.get("inscribed", True))
    angle = math.radians(float(feat.get("angle_deg", 0.0)))
    px, py = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
    sm = _enter_plane_sketch(ctx, feat)
    result = sm.CreatePolygon(cx, cy, 0.0, px, py, 0.0, sides, inscribed)
    _apply_construction(result, feat)
    return _close_plane_sketch_and_build(ctx, feat)


def _build_sketch_ellipse(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch an ellipse on a reference plane.

    Seat-proven: ``ISketchManager.CreateEllipse(cx,cy,cz, majX,majY,majZ,
    minX,minY,minZ)``. The major-axis endpoint is ``center + major_radius`` at
    ``angle_deg``; the minor-axis endpoint is ``center + minor_radius`` along
    the in-plane perpendicular.
    """
    import math

    c = feat["center"]
    cx, cy = _mm_to_m(c["x"]), _mm_to_m(c["y"])
    major = _mm_to_m(feat["major_radius"])
    minor = _mm_to_m(feat["minor_radius"])
    angle = math.radians(float(feat.get("angle_deg", 0.0)))
    majx, majy = cx + major * math.cos(angle), cy + major * math.sin(angle)
    minx, miny = cx - minor * math.sin(angle), cy + minor * math.cos(angle)
    sm = _enter_plane_sketch(ctx, feat)
    seg = sm.CreateEllipse(cx, cy, 0.0, majx, majy, 0.0, minx, miny, 0.0)
    _apply_construction(seg, feat)
    return _close_plane_sketch_and_build(ctx, feat)


def _build_sketch_text(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch a text annotation on a reference plane.

    Seat-proven: text is a document-level op -- ``IModelDoc2.InsertSketchText(
    Ptx, Pty, Ptz, Text, Alignment, FlipDirection, HorizontalMirror,
    WidthFactor, SpaceBetweenChars)`` (the trailing args are ints; there is NO
    angle parameter). ``height`` (CharHeight) and ``font`` (TypeFaceName) are
    applied through the returned ISketchText's text format (see
    ``_apply_text_format``).

    ``angle_deg`` and ``construction`` are rejected: text baseline rotation has
    no out-of-process API on this seat (no angle on InsertSketchText/ITextFormat)
    and text is not a sketch segment.
    """
    if feat.get("construction") is True:
        raise NotImplementedError(
            "Text is not a sketch segment; construction geometry does not apply. "
            "Remove 'construction' from the text spec."
        )
    if feat.get("angle_deg"):
        raise NotImplementedError(
            "Text baseline rotation has no out-of-process API on this SOLIDWORKS "
            "version (InsertSketchText/ITextFormat expose no angle). Remove "
            "'angle_deg' from the text spec."
        )
    pos = feat["position"]
    # Open the sketch (for its side effect); text is inserted via the doc, not
    # the sketch manager, so the returned SketchManager handle is unused here.
    _enter_plane_sketch(ctx, feat)
    raw_text = ctx.doc.InsertSketchText(
        _mm_to_m(pos["x"]),
        _mm_to_m(pos["y"]),
        0.0,
        str(feat["content"]),
        0,
        0,
        0,
        1,
        1,
    )
    _apply_text_format(raw_text, feat)
    return _close_plane_sketch_and_build(ctx, feat)


# ---------------------------------------------------------------------------
# W53 -- 3D-sketch primitive.  A 3D sketch is NOT on a reference plane; it
# uses Insert3DSketch(True) (one BOOL UpdateEditRebuild arg, NOT parameterless)
# to enter/exit sketch mode.  Line segments carry real X/Y/Z coordinates
# (millimetres in the spec, converted to metres for COM).  This primitive
# unblocks weldments (FR-5-06) and swept/lofted surfaces (FR-5-02).
# ---------------------------------------------------------------------------


def _enter_3d_sketch(ctx: BuildContext) -> Any:
    """Open a 3D sketch; return SketchManager.

    No plane selection -- 3D sketches are not constrained to a reference plane.
    ``ISketchManager.Insert3DSketch`` takes one BOOL ``UpdateEditRebuild`` arg
    (seat-proven: parameterless raises 'Parameter not optional').
    """
    sm = ctx.doc.SketchManager
    sm.Insert3DSketch(True)
    return sm


def _close_3d_sketch_and_build(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Close the open 3D sketch, rename the new sketch feature, return BuiltFeature."""
    ctx.doc.SketchManager.Insert3DSketch(True)
    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError(f"no sketch feature produced for '{feat['name']}'")
    sketch_feat.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=sketch_feat)


def _build_sketch_3d_sketch(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch a 3D polyline through a sequence of 3D points.

    Opens a 3D sketch (no plane), draws line segments between consecutive
    points with real X/Y/Z coordinates, then closes.  Seat-proven recipe:
    ``Insert3DSketch(True)`` + ``CreateLine`` (spike v0.21 S2 GREEN).
    """
    points = feat["points"]
    sm = _enter_3d_sketch(ctx)
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        sm.CreateLine(
            _mm_to_m(a["x"]),
            _mm_to_m(a["y"]),
            _mm_to_m(a["z"]),
            _mm_to_m(b["x"]),
            _mm_to_m(b["y"]),
            _mm_to_m(b["z"]),
        )
    return _close_3d_sketch_and_build(ctx, feat)
