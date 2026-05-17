"""
Direct-COM build executor for v0.2 spec parts.

Walks a validated spec.features list in order. For each feature, calls the
matching SW COM API via pywin32 late-binding (per Phase 0 findings - all 22
API surfaces tested work via direct call). Records what was built into a
manifest so the caller can verify intent against reality.

Phase 0 findings baked in:
- Use legacy 5-arg `doc.SelectByID(name, type, x, y, z)`; never SelectByID2.
- `SketchManager.CreateCircle(xc, yc, zc, xp, yp, zp)`; never CreateCircleByRadius.
- Rename feature with `.Name = "..."` immediately after creation. Bind dims
  using the renamed identifier.
- Full 4-call sequence to link locals: FilePath + LinkToFile=True +
  AutomaticRebuild=True + UpdateValuesFromExternalEquationFile.
- `EquationMgr.Add2(-1, formula, True)` returns -1 on silent failure; non-
  negative on success.
"""

from __future__ import annotations

import copy
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..locals_io import parse as parse_locals
from ..sw_com import get_sw_app
from ..sw_types import (  # noqa: F401  -- re-exported for downstream users
    SW_END_COND_BLIND,
    SW_END_COND_THROUGH_ALL,
    SW_END_COND_THROUGH_NEXT,
    SW_END_COND_MID_PLANE,
    SW_END_COND_THROUGH_ALL_BOTH,
    SW_START_SKETCH_PLANE,
    assert_args,
)


# swUserPreferenceToggle.swInputDimValOnCreate -- the toggle ID is NOT
# documented in the CHM enum (descriptions just say "see System Options").
# Empirically, ID=8 reads back False on this build but does NOT suppress
# the popup. Kept in place because it's harmless and may help on some
# SW builds; see MMP_DEBUG_SESSION.md for the full investigation.
SW_PREF_INPUT_DIM_VAL_ON_CREATE = 8


# Plane name -> outward-normal vector (in part coordinates, +X right, +Y up, +Z out of screen)
# Matches SW's default English template orientation:
#   Front Plane = XY plane (normal +Z)
#   Top   Plane = XZ plane (normal +Y)
#   Right Plane = YZ plane (normal +X)
PLANE_NORMALS: dict[str, tuple[float, float, float]] = {
    "Front": (0.0, 0.0, 1.0),
    "Top":   (0.0, 1.0, 0.0),
    "Right": (1.0, 0.0, 0.0),
}
PLANE_FULL_NAME = {
    "Front": "Front Plane",
    "Top":   "Top Plane",
    "Right": "Right Plane",
}


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
}


@dataclass
class BuiltFeature:
    name: str
    type: str
    sw_object: Any = None  # the IFeature CDispatch
    # For sketches (plane-based): the normal of the parent reference plane.
    # Used by the subsequent extrusion to inherit its axis. None for face-
    # based sketches (their parent is a face whose normal is already known).
    parent_plane_normal: tuple[float, float, float] | None = None
    # For extrusions: the actual extrude axis (outward normal of the boss/cut),
    # origin of the base face in part coords, blind depth in meters, and the
    # `flip` flag (True = extrude in -axis direction). Used by child sketches
    # on this extrusion's faces to compute world coords.
    extrude_axis: tuple[float, float, float] | None = None
    extrude_origin: tuple[float, float, float] | None = None
    extrude_depth_m: float | None = None
    extrude_flip: bool = False


@dataclass
class BuildContext:
    """Per-build state. Holds the SW app/doc handle and feature lookup."""
    sw: Any
    doc: Any
    features_by_name: dict[str, BuiltFeature] = field(default_factory=dict)
    rebuild_count: int = 0
    # no_dim mode: skip all AddDimension2 calls and Add2 bindings. Geometry
    # is built at literal target sizes (rhs's resolved at the spec level
    # before any handler runs). The resulting part has no equation links to
    # locals.txt -- editing locals requires re-running ai-sw-build.
    no_dim: bool = False


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


# -----------------------------------------------------------------------------
# no_dim mode: resolve {rhs} -> literal mm at build time, skip AddDimension2
# -----------------------------------------------------------------------------
#
# Why: AddDimension2 opens a Modify-Dimension popup + PM pane on SW 2024 SP1
# that cannot be suppressed via any swUserPreferenceToggle we've tried
# (Spike I: toggle 8, Spike M: toggle 78, both no effect). The popup blocks
# until the user manually ticks. MMP needs ~16 ticks per build.
#
# Workaround: resolve every {"rhs": "..."} reference against the linked
# locals file in Python BEFORE calling SW, substitute the literal mm value
# into the spec, and bypass AddDimension2 entirely. The resulting part has
# correct geometry but no equations linked to locals.txt -- editing locals
# requires re-running ai-sw-build to propagate.


def _load_locals_map(locals_path: str | Path) -> dict[str, float]:
    """Parse a SW Link-to-file locals file into a name->float (mm) map.

    Non-literal entries (those whose RHS references other variables or uses
    arithmetic) are evaluated recursively. Cycles raise; unresolvable refs
    raise KeyError on the missing name.
    """
    text = Path(locals_path).read_text(encoding="utf-8")
    entries = parse_locals(text)
    raw: dict[str, str] = {e.name: e.expression for e in entries}
    resolved: dict[str, float] = {}
    resolving: set[str] = set()

    def _resolve(name: str) -> float:
        if name in resolved:
            return resolved[name]
        if name in resolving:
            raise ValueError(f"cycle in locals while resolving '{name}'")
        if name not in raw:
            raise KeyError(f"locals has no entry for '{name}'")
        resolving.add(name)
        try:
            value = _eval_rhs(raw[name], _resolve)
        finally:
            resolving.discard(name)
        resolved[name] = value
        return value

    for name in raw:
        _resolve(name)
    return resolved


def _eval_rhs(rhs: str, lookup: Any) -> float:
    """Evaluate an rhs expression like '"PART_DIAMETER"' or '"FOO" + 0.5'.

    Quoted variable refs are substituted with their numeric value via the
    `lookup` callable (which takes a name and returns a float, recursing as
    needed). The remainder is evaluated as a Python expression with no
    builtins -- only +, -, *, /, parens, and numeric literals are usable.
    """
    def _sub(m: "re.Match[str]") -> str:
        return repr(lookup(m.group(1)))

    py_expr = re.sub(r'"([^"]+)"', _sub, rhs)
    return float(eval(py_expr, {"__builtins__": {}}, {}))


def _resolve_rhs_in_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied spec where every {"rhs": "..."} object has been
    replaced with the literal numeric mm value resolved from spec['locals'].

    Requires spec['locals'] to be present and readable. Raises KeyError if
    any rhs references an unknown var, ValueError on locals cycles.
    """
    if "locals" not in spec or not spec["locals"]:
        # No locals = nothing to resolve. Caller may still have rhs's that
        # will fail validation, but that's a different error.
        return copy.deepcopy(spec)
    locals_map = _load_locals_map(spec["locals"])

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "rhs" in node and isinstance(node["rhs"], str):
                return _eval_rhs(node["rhs"], lambda n: locals_map[n])
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(x) for x in node]
        return node

    return _walk(spec)


# -----------------------------------------------------------------------------
# Document setup
# -----------------------------------------------------------------------------


def create_blank_part(sw: Any) -> Any:
    """Create a new blank part via NewDocument and return the doc.

    SW templates live at the user's template root (set by Tools > Options >
    File Locations > Document Templates). Default English install has
    "Part.prtdot" at `C:\\ProgramData\\SolidWorks\\SOLIDWORKS 2024\\templates\\`.

    NewDocument signature (late-binding friendly, no OUT params):
        NewDocument(templateName, paperSize, width, height) -> IModelDoc2
    """
    # GetUserPreferenceStringValue with swDefaultTemplatePart=8 (per SW API)
    template_path = sw.GetUserPreferenceStringValue(8)
    if not template_path:
        raise RuntimeError(
            "Could not resolve default Part template. Check Tools > Options > "
            "File Locations > Document Templates."
        )
    # Paper size + width + height ignored for parts; pass 0s.
    doc = sw.NewDocument(template_path, 0, 0.0, 0.0)
    if doc is None:
        raise RuntimeError(f"NewDocument returned None for template {template_path}")
    return doc


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


def link_locals(doc: Any, locals_path: str) -> None:
    """Run the full 4-call LinkToFile sequence proven in Spike C.

    Setting FilePath alone is not sufficient: globals from the file are
    NOT loaded into the equation namespace until LinkToFile=True is set,
    AutomaticRebuild=True is set, and UpdateValuesFromExternalEquationFile
    is invoked (auto-fires via late-binding property access)."""
    eq = doc.GetEquationMgr
    if eq is None:
        raise RuntimeError("doc.GetEquationMgr is None")
    eq.FilePath = str(locals_path)
    eq.LinkToFile = True
    eq.AutomaticRebuild = True
    _ = eq.UpdateValuesFromExternalEquationFile  # auto-fires reload
    if not eq.LinkToFile:
        raise RuntimeError(f"failed to activate link to {locals_path}")


# -----------------------------------------------------------------------------
# Per-feature builders
# -----------------------------------------------------------------------------


def _build_sketch_rectangle_on_plane(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    plane = feat["plane"]
    full = PLANE_FULL_NAME[plane]
    ok = ctx.doc.SelectByID(full, "PLANE", 0.0, 0.0, 0.0)
    if not ok:
        raise RuntimeError(f"could not select {full}")

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    # Use placeholder dims for rhs values; literal otherwise.
    # Placeholder = the field default mm (10mm for rectangles - arbitrary nonzero).
    width_m = _literal_or_default(feat["width"], PLACEHOLDER_MM["rectangle_side"])
    height_m = _literal_or_default(feat["height"], PLACEHOLDER_MM["rectangle_side"])
    center = feat.get("center", {})
    cx_m = float(center.get("x", 0.0)) / 1000.0
    cy_m = float(center.get("y", 0.0)) / 1000.0

    # CreateCenterRectangle (NOT CreateCornerRectangle) so the rectangle
    # is internally anchored to its CENTER via construction diagonals.
    # When dim binding resizes it, both halves grow symmetrically -- the
    # corner-rectangle equivalent would let SW's solver anchor at an
    # arbitrary corner and grow asymmetrically, putting features
    # off-center after the rebuild. Args: (center, opposite corner).
    sm.CreateCenterRectangle(
        cx_m, cy_m, 0.0,
        cx_m + width_m / 2, cy_m + height_m / 2, 0.0,
    )

    # Add driving dimensions so Add2 has D1/D2 to bind to. Selection order
    # determines dim numbering: top edge first -> D1 = width, left edge second
    # -> D2 = height (matches DIM_FIELD_MAP).
    # AddDimension2 places the dim leader at the given coord; we offset
    # outside the rectangle so the leader doesn't overlap entities.
    # Skipped in no_dim mode -- geometry is already at target size and no
    # parametric binding will happen.
    if not ctx.no_dim:
        ctx.doc.ClearSelection2(True)
        top_y = cy_m + height_m / 2
        if not ctx.doc.SelectByID("", "SKETCHSEGMENT", cx_m, top_y, 0.0):
            raise RuntimeError("could not select rectangle top edge for width dim")
        dim_w = ctx.doc.AddDimension2(cx_m, top_y + 0.005, 0.0)
        if dim_w is None:
            raise RuntimeError("AddDimension2 returned None for width")
        _dismiss_dim_pane(ctx.doc)

        ctx.doc.ClearSelection2(True)
        left_x = cx_m - width_m / 2
        if not ctx.doc.SelectByID("", "SKETCHSEGMENT", left_x, cy_m, 0.0):
            raise RuntimeError("could not select rectangle left edge for height dim")
        dim_h = ctx.doc.AddDimension2(left_x - 0.005, cy_m, 0.0)
        if dim_h is None:
            raise RuntimeError("AddDimension2 returned None for height")
        _dismiss_dim_pane(ctx.doc)

    sm.InsertSketch(True)  # close

    # Most-recent feature is the sketch we just created. Rename it.
    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no sketch produced by CreateCornerRectangle")
    sketch_feat.Name = feat["name"]

    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=sketch_feat)


def _build_sketch_circle_on_plane(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    plane = feat["plane"]
    full = PLANE_FULL_NAME[plane]
    ok = ctx.doc.SelectByID(full, "PLANE", 0.0, 0.0, 0.0)
    if not ok:
        raise RuntimeError(f"could not select {full}")

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    diameter_m = _literal_or_default(feat["diameter"], PLACEHOLDER_MM["circle_diameter_plane"])
    radius_m = diameter_m / 2
    center = feat.get("center", {})
    cx_m = float(center.get("x", 0.0)) / 1000.0
    cy_m = float(center.get("y", 0.0)) / 1000.0

    # CreateCircle(xc, yc, zc, xp, yp, zp) - perimeter point at (cx+r, cy, 0)
    sm.CreateCircle(cx_m, cy_m, 0.0, cx_m + radius_m, cy_m, 0.0)

    # Add a diameter dim. Select the circle by clicking on its perimeter,
    # then place the dim leader outside the circle.
    # Skipped in no_dim mode.
    if not ctx.no_dim:
        ctx.doc.ClearSelection2(True)
        if not ctx.doc.SelectByID("", "SKETCHSEGMENT", cx_m + radius_m, cy_m, 0.0):
            raise RuntimeError("could not select circle for diameter dim")
        dim_d = ctx.doc.AddDimension2(cx_m + radius_m + 0.005, cy_m + radius_m + 0.005, 0.0)
        if dim_d is None:
            raise RuntimeError("AddDimension2 returned None for diameter")
        _dismiss_dim_pane(ctx.doc)

    sm.InsertSketch(True)

    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no sketch produced by CreateCircle")
    sketch_feat.Name = feat["name"]

    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=sketch_feat)


def _select_extrude_face(
    ctx: BuildContext,
    parent: "BuiltFeature",
    face: str,
) -> tuple[bool, float, float, float]:
    """Select the +z or -z face of an extrusion.

    Tries the face center first; if that fails (e.g. earlier cut removed
    material at the center), tries small offsets from center until one
    succeeds. Returns (ok, fx, fy, fz) where the coords are the point on
    the face that successfully selected (for downstream use as sketch
    origin reference).
    """
    # Callers (the face-sketch builders) only invoke this on parents that
    # are extrusions; the type system can't see that without a discriminator.
    assert parent.extrude_origin is not None, f"{parent.name}: extrude_origin not set"
    assert parent.extrude_axis is not None, f"{parent.name}: extrude_axis not set"
    assert parent.extrude_depth_m is not None, f"{parent.name}: extrude_depth_m not set"
    ox, oy, oz = parent.extrude_origin
    ax, ay, az = parent.extrude_axis
    depth = parent.extrude_depth_m
    if parent.extrude_flip:
        ax, ay, az = -ax, -ay, -az
    if face == "+z":
        fx0 = ox + ax * depth
        fy0 = oy + ay * depth
        fz0 = oz + az * depth
    else:
        fx0, fy0, fz0 = ox, oy, oz

    # Candidate offsets in the face's tangent plane. Since +z faces lie
    # perpendicular to the extrude axis, the tangent plane uses the OTHER
    # two axes. For a Front-Plane sketch, axis=+Z, so tangent = (X, Y).
    # Try center first; if that hits a hole (prior cut), expand to larger
    # offsets. Use a spiral of 1mm, 5mm, 15mm, 50mm to handle holes of any
    # reasonable size. Worst case (large hole, small plate): last offset
    # still falls inside the hole AND outside the plate -- a real geometry
    # problem the caller must fix by adjusting the spec.
    offsets_2d = [
        (0, 0),
        (0.001, 0), (0, 0.001), (-0.001, 0), (0, -0.001),
        (0.005, 0), (0, 0.005), (-0.005, 0), (0, -0.005),
        (0.015, 0), (0, 0.015), (-0.015, 0), (0, -0.015),
        (0.005, 0.005), (-0.005, -0.005),
        (0.015, 0.015), (-0.015, -0.015),
    ]

    if abs(az) > 0.99:        # axis is +/-Z; tangent is (X, Y)
        for du, dv in offsets_2d:
            fx, fy, fz = fx0 + du, fy0 + dv, fz0
            ctx.doc.ClearSelection2(True)
            if ctx.doc.SelectByID("", "FACE", fx, fy, fz):
                return True, fx, fy, fz
    elif abs(ay) > 0.99:      # axis is +/-Y; tangent is (X, Z)
        for du, dv in offsets_2d:
            fx, fy, fz = fx0 + du, fy0, fz0 + dv
            ctx.doc.ClearSelection2(True)
            if ctx.doc.SelectByID("", "FACE", fx, fy, fz):
                return True, fx, fy, fz
    else:                     # axis is +/-X; tangent is (Y, Z)
        for du, dv in offsets_2d:
            fx, fy, fz = fx0, fy0 + du, fz0 + dv
            ctx.doc.ClearSelection2(True)
            if ctx.doc.SelectByID("", "FACE", fx, fy, fz):
                return True, fx, fy, fz

    return False, fx0, fy0, fz0


def _build_sketch_circle_on_face(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    parent_name = feat["of_feature"]
    parent = ctx.features_by_name.get(parent_name)
    if parent is None:
        raise RuntimeError(f"sketch_circle_on_face: '{parent_name}' not built yet")
    if parent.extrude_axis is None:
        raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

    # Compute the face center in part coordinates.
    # The face spec (e.g. "+z") is in the feature's local frame; for v1 we
    # treat the extrusion's outward normal as +z_local. So:
    #   "+z" face = outboard face = extrude_origin + axis * depth
    #   "-z" face = inboard face = extrude_origin
    # Other faces (+/- x, y) are the four side faces. v1 supports only +z and -z.
    face = feat["face"]
    if face not in ("+z", "-z"):
        raise NotImplementedError(
            f"v1 only supports +z/-z (out/in board) faces of extrusions; got {face}"
        )

    ok, fx, fy, fz = _select_extrude_face(ctx, parent, face)
    if not ok:
        raise RuntimeError(
            f"SelectByID returned False for {face} face of {parent_name} -- "
            f"tried center and offset points, none hit material"
        )

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    diameter_m = _literal_or_default(feat["diameter"], PLACEHOLDER_MM["circle_diameter_face"])
    radius_m = diameter_m / 2
    # In a face-based sketch, the sketch origin is at the face center by default.
    # 'center' offset is in sketch-local u/v (mm).
    c = feat.get("center", {})
    u_m = float(c.get("u", 0.0)) / 1000.0
    v_m = float(c.get("v", 0.0)) / 1000.0

    sm.CreateCircle(u_m, v_m, 0.0, u_m + radius_m, v_m, 0.0)

    # Add diameter dim. SelectByID for SKETCHSEGMENT uses PART-frame coords,
    # so on -z faces we mirror u (SW mirrors the sketch X axis when looking
    # at a -z face from outside).
    # Skipped in no_dim mode -- geometry is already at target diameter.
    if not ctx.no_dim:
        mirror_u = -1.0 if face.startswith("-") else 1.0
        u_click = mirror_u * u_m

        ctx.doc.ClearSelection2(True)
        sel_candidates = [
            (u_click + radius_m * mirror_u, v_m, 0.0),
            (u_click, v_m + radius_m, 0.0),
            (u_click - radius_m * mirror_u, v_m, 0.0),
            (u_click, v_m - radius_m, 0.0),
        ]
        selected = False
        for sx, sy, sz in sel_candidates:
            if ctx.doc.SelectByID("", "SKETCHSEGMENT", sx, sy, sz):
                selected = True
                break
        if not selected:
            raise RuntimeError(
                f"could not select face-sketch circle for diameter dim "
                f"(face={face}, u={u_m*1000:.1f}mm, r={radius_m*1000:.2f}mm)"
            )
        dim_d = ctx.doc.AddDimension2(u_m + radius_m + 0.005, v_m + radius_m + 0.005, 0.0)
        if dim_d is None:
            raise RuntimeError("AddDimension2 returned None for face-sketch diameter")
        _dismiss_dim_pane(ctx.doc)

    sm.InsertSketch(True)

    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no sketch produced on face")
    sketch_feat.Name = feat["name"]

    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=sketch_feat)


def _build_sketch_circles_on_face(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Multiple circles in one sketch on a feature face.

    Each circle gets its own driving diameter dim. Dim numbering follows
    selection order: first circle's diameter -> D1, second -> D2, etc.
    The builder dimensions each circle immediately after creating it so the
    numbering matches the spec's `circles` array order.
    """
    parent_name = feat["of_feature"]
    parent = ctx.features_by_name.get(parent_name)
    if parent is None:
        raise RuntimeError(f"sketch_circles_on_face: '{parent_name}' not built yet")
    if parent.extrude_axis is None:
        raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

    face = feat["face"]
    if face not in ("+z", "-z"):
        raise NotImplementedError(
            f"v1 only supports +z/-z (out/in board) faces; got {face}"
        )

    ok, fx, fy, fz = _select_extrude_face(ctx, parent, face)
    if not ok:
        raise RuntimeError(
            f"face select returned False for {face} face of {parent_name} -- "
            f"tried center and offsets"
        )

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    # On -z faces (and -x/-y), SW mirrors the sketch X axis: a circle drawn
    # at sketch (u, v) lands at part (-u, v). The CreateCircle call uses
    # sketch-local coords (so the circle ends up where the spec says relative
    # to the face's u/v frame), but SelectByID for SKETCHSEGMENT needs PART
    # coords on this build. Compute the click-coord mirror once.
    if face.startswith("-"):
        mirror_u = -1.0
    else:
        mirror_u = 1.0

    for k, c in enumerate(feat["circles"]):
        u_m = float(c["u"]) / 1000.0
        v_m = float(c["v"]) / 1000.0
        diameter_m = _literal_or_default(c["diameter"], PLACEHOLDER_MM["circle_diameter_multi"])
        radius_m = diameter_m / 2
        sm.CreateCircle(u_m, v_m, 0.0, u_m + radius_m, v_m, 0.0)
        if ctx.no_dim:
            # Geometry already at target size; no dim binding needed.
            continue
        # Dimension this circle BEFORE creating the next one, so dim
        # numbering matches array index: first circle -> D1, second -> D2.
        ctx.doc.ClearSelection2(True)
        # Click in part-frame coords; on -z faces, the u axis is mirrored.
        u_click = mirror_u * u_m
        sel_candidates = [
            (u_click + radius_m * mirror_u, v_m, 0.0),       # east-ish
            (u_click, v_m + radius_m, 0.0),                  # north
            (u_click - radius_m * mirror_u, v_m, 0.0),       # west-ish
            (u_click, v_m - radius_m, 0.0),                  # south
        ]
        selected = False
        for sx, sy, sz in sel_candidates:
            if ctx.doc.SelectByID("", "SKETCHSEGMENT", sx, sy, sz):
                selected = True
                break
        if not selected:
            raise RuntimeError(
                f"could not select circle #{k} (perimeter at radius {radius_m*1000:.2f}mm "
                f"from sketch center ({u_m*1000:.1f}, {v_m*1000:.1f}) mm, "
                f"face={face}, mirror_u={mirror_u}) -- "
                f"tried 4 cardinal perimeter points in part frame"
            )
        # Place leader offset from the circle, with stagger so consecutive
        # circles' dim leaders don't overlap.
        lead_offset = 0.005 + 0.003 * k
        dim = ctx.doc.AddDimension2(u_m + radius_m + lead_offset, v_m + lead_offset, 0.0)
        if dim is None:
            raise RuntimeError(f"AddDimension2 returned None for circle #{k}")
        _dismiss_dim_pane(ctx.doc)

    sm.InsertSketch(True)

    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no multi-circle sketch produced")
    sketch_feat.Name = feat["name"]

    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=sketch_feat)


def _call_feature_extrusion(
    ctx: BuildContext,
    *,
    end_cond: int,
    depth_m: float,
    flip: bool,
) -> Any:
    """Boss-only extrusion. For cuts use _call_feature_cut (FeatureCut4).

    SW 2017+ signature (23 args; verified via decompiled sldworksapi.chm):
      Sd, Flip, Dir, T1, T2, D1, D2,
      Dchk1, Dchk2, Ddir1, Ddir2,
      Dang1, Dang2,
      OffsetReverse1, OffsetReverse2,
      TranslateSurface1, TranslateSurface2,
      Merge,
      UseFeatScope, UseAutoSelect,
      T0, StartOffset, FlipStartOffset
    """
    fm = ctx.doc.FeatureManager
    args = (
        True,           # 1  Sd (single direction)
        flip,           # 2  Flip
        False,          # 3  Dir (use sketch normal)
        end_cond,       # 4  T1
        0,              # 5  T2
        depth_m,        # 6  D1
        0.0,            # 7  D2
        False,          # 8  Dchk1
        False,          # 9  Dchk2
        False,          # 10 Ddir1
        False,          # 11 Ddir2
        0.0,            # 12 Dang1
        0.0,            # 13 Dang2
        False,          # 14 OffsetReverse1
        False,          # 15 OffsetReverse2
        False,          # 16 TranslateSurface1
        False,          # 17 TranslateSurface2
        True,           # 18 Merge
        True,           # 19 UseFeatScope
        True,           # 20 UseAutoSelect
        SW_START_SKETCH_PLANE,  # 21 T0
        0.0,            # 22 StartOffset
        False,          # 23 FlipStartOffset
    )
    assert_args("IFeatureManager.FeatureExtrusion2", args)
    feature = fm.FeatureExtrusion2(*args)
    if feature is None:
        raise RuntimeError("FeatureExtrusion2 returned None")
    return feature


def _call_feature_cut(
    ctx: BuildContext,
    *,
    end_cond: int,
    depth_m: float,
    flip: bool,
) -> Any:
    """FeatureManager.FeatureCut4 - the cut variant of FeatureExtrusion2.

    SW 2017+ signature (27 args; verified via decompiled sldworksapi.chm
    and Spike E7 on SW 2024 SP1):
      Sd, Flip, Dir, T1, T2, D1, D2,
      Dchk1, Dchk2, Ddir1, Ddir2,
      Dang1, Dang2,
      OffsetReverse1, OffsetReverse2,
      TranslateSurface1, TranslateSurface2,
      NormalCut,
      UseFeatScope, UseAutoSelect, AssemblyFeatureScope,
      AutoSelectComponents, PropagateFeatureToParts,
      T0, StartOffset, FlipStartOffset, OptimizeGeometry
    """
    fm = ctx.doc.FeatureManager
    args = (
        True,           # 1  Sd (single-ended)
        flip,           # 2  Flip
        False,          # 3  Dir
        end_cond,       # 4  T1
        0,              # 5  T2
        depth_m,        # 6  D1
        0.0,            # 7  D2
        False,          # 8  Dchk1
        False,          # 9  Dchk2
        False,          # 10 Ddir1
        False,          # 11 Ddir2
        0.0,            # 12 Dang1
        0.0,            # 13 Dang2
        False,          # 14 OffsetReverse1
        False,          # 15 OffsetReverse2
        False,          # 16 TranslateSurface1
        False,          # 17 TranslateSurface2
        False,          # 18 NormalCut (sheet metal only)
        True,           # 19 UseFeatScope
        True,           # 20 UseAutoSelect
        True,           # 21 AssemblyFeatureScope
        True,           # 22 AutoSelectComponents
        False,          # 23 PropagateFeatureToParts
        SW_START_SKETCH_PLANE,  # 24 T0
        0.0,            # 25 StartOffset
        False,          # 26 FlipStartOffset
        False,          # 27 OptimizeGeometry (sheet metal only)
    )
    assert_args("IFeatureManager.FeatureCut4", args)
    feature = fm.FeatureCut4(*args)
    if feature is None:
        raise RuntimeError("FeatureCut4 returned None")
    return feature


def _select_sketch(ctx: BuildContext, sketch_name: str) -> None:
    ctx.doc.ClearSelection2(True)
    ok = ctx.doc.SelectByID(sketch_name, "SKETCH", 0.0, 0.0, 0.0)
    if not ok:
        raise RuntimeError(f"could not select sketch '{sketch_name}'")


def _build_boss_extrude_blind(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    sketch_name = feat["sketch"]
    sketch = ctx.features_by_name[sketch_name]

    _select_sketch(ctx, sketch_name)
    depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["extrude_depth"])
    flip = bool(feat.get("flip", False))

    f = _call_feature_extrusion(ctx, end_cond=SW_END_COND_BLIND, depth_m=depth_m, flip=flip)
    f.Name = feat["name"]

    # Inherit the axis from the parent plane-based sketch. build() stashes
    # the plane's outward normal on `parent_plane_normal` before this handler
    # runs; we reuse it as our extrude axis.
    if sketch.parent_plane_normal is None:
        raise RuntimeError(
            f"sketch '{sketch_name}' has no parent_plane_normal stashed; "
            f"build() should set it on every plane-based sketch"
        )
    return BuiltFeature(
        name=feat["name"],
        type=feat["type"],
        sw_object=f,
        extrude_axis=sketch.parent_plane_normal,
        extrude_origin=(0.0, 0.0, 0.0),
        extrude_depth_m=depth_m,
        extrude_flip=flip,
    )


def _build_cut_extrude_through_all(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    sketch_name = feat["sketch"]
    _select_sketch(ctx, sketch_name)
    flip = bool(feat.get("flip", False))
    f = _call_feature_cut(ctx, end_cond=SW_END_COND_THROUGH_ALL, depth_m=0.0, flip=flip)
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _build_cut_extrude_blind(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    sketch_name = feat["sketch"]
    _select_sketch(ctx, sketch_name)
    depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["cut_depth"])
    flip = bool(feat.get("flip", False))
    f = _call_feature_cut(ctx, end_cond=SW_END_COND_BLIND, depth_m=depth_m, flip=flip)
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


# -----------------------------------------------------------------------------
# Feature registry: unified handler + dim-binding + length-field metadata
# -----------------------------------------------------------------------------
#
# Each feature type declares (in one place):
#   - handler:      Callable[[ctx, feat_dict], BuiltFeature]
#   - dim_fields:   {spec_field_name: dim_suffix} for fixed dims
#                   (e.g. "width" -> "D1", "depth" -> "D1")
#   - rhs_walker:   Callable[[feat_dict], list[(field_path, dim_suffix, rhs)]]
#                   that yields parametric bindings for that feature. Default
#                   uses dim_fields; sketch_circles_on_face overrides because
#                   its diameter dims are inside the `circles[]` array.
#
# Adding a new feature (e.g. revolve) means adding ONE FeatureType entry --
# the validator, dim-binder, and dispatcher all read from this single source.


def _default_rhs_walker(
    dim_fields: dict[str, str],
) -> Any:
    """Build a default rhs_walker that pulls from feat[field] for each
    declared dim_field. Returns a callable suitable for FeatureType.rhs_walker."""
    def _walk(feat: dict[str, Any]) -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        for field, dim_suffix in dim_fields.items():
            value = feat.get(field)
            if isinstance(value, dict) and "rhs" in value:
                out.append((field, dim_suffix, value["rhs"]))
        return out
    return _walk


def _circles_on_face_rhs_walker(feat: dict[str, Any]) -> list[tuple[str, str, str]]:
    """sketch_circles_on_face has variadic dims: circles[k].diameter -> Dk+1."""
    out: list[tuple[str, str, str]] = []
    for k, c in enumerate(feat.get("circles", [])):
        value = c.get("diameter")
        if isinstance(value, dict) and "rhs" in value:
            out.append((f"circles[{k}].diameter", f"D{k+1}", value["rhs"]))
    return out


@dataclass(frozen=True)
class FeatureType:
    """Per-feature-type metadata. One entry per supported feature."""
    name: str
    handler: Any  # Callable[[BuildContext, dict], BuiltFeature]
    # {spec_field_name: dim_suffix} for fixed dims. dim_suffix is the SW
    # auto-name (D1, D2, ...) created by AddDimension2 in selection order.
    dim_fields: dict[str, str]
    # Override for non-default rhs walking (e.g. arrays of dims).
    # Default None means "use the dim_fields-based walker."
    rhs_walker: Any | None = None  # Callable[[dict], list[(field_path, suffix, rhs)]]

    def collect_rhs_bindings(self, feat: dict[str, Any]) -> list[tuple[str, str]]:
        """Return [(dim_name, rhs)] for every parametric ({rhs}) length in
        this feature. dim_name is the SW-fq form 'Dn@FeatureName'."""
        walker = self.rhs_walker or _default_rhs_walker(self.dim_fields)
        return [
            (f"{suffix}@{feat['name']}", rhs)
            for _field_path, suffix, rhs in walker(feat)
        ]


# THE registry. To add a new feature type, append one entry here, add a
# handler function, and add its schema in `schema.py`.
FEATURE_REGISTRY: dict[str, FeatureType] = {
    "sketch_rectangle_on_plane": FeatureType(
        name="sketch_rectangle_on_plane",
        handler=None,  # filled in below after handler defs are in scope
        dim_fields={"width": "D1", "height": "D2"},
    ),
    "sketch_circle_on_plane": FeatureType(
        name="sketch_circle_on_plane",
        handler=None,
        dim_fields={"diameter": "D1"},
    ),
    "sketch_circle_on_face": FeatureType(
        name="sketch_circle_on_face",
        handler=None,
        dim_fields={"diameter": "D1"},
    ),
    "sketch_circles_on_face": FeatureType(
        name="sketch_circles_on_face",
        handler=None,
        dim_fields={},  # variadic; see rhs_walker
        rhs_walker=_circles_on_face_rhs_walker,
    ),
    "boss_extrude_blind": FeatureType(
        name="boss_extrude_blind",
        handler=None,
        dim_fields={"depth": "D1"},
    ),
    "cut_extrude_through_all": FeatureType(
        name="cut_extrude_through_all",
        handler=None,
        dim_fields={},  # no depth dim on through-all
    ),
    "cut_extrude_blind": FeatureType(
        name="cut_extrude_blind",
        handler=None,
        dim_fields={"depth": "D1"},
    ),
}


# Wire handlers into the registry (done at module-load time, after all
# handler functions are defined above).
def _wire_handlers() -> None:
    handlers = {
        "sketch_rectangle_on_plane": _build_sketch_rectangle_on_plane,
        "sketch_circle_on_plane":    _build_sketch_circle_on_plane,
        "sketch_circle_on_face":     _build_sketch_circle_on_face,
        "sketch_circles_on_face":    _build_sketch_circles_on_face,
        "boss_extrude_blind":        _build_boss_extrude_blind,
        "cut_extrude_through_all":   _build_cut_extrude_through_all,
        "cut_extrude_blind":         _build_cut_extrude_blind,
    }
    for name, ft in FEATURE_REGISTRY.items():
        # FeatureType is frozen; rebuild with handler in place.
        FEATURE_REGISTRY[name] = FeatureType(
            name=ft.name,
            handler=handlers[name],
            dim_fields=ft.dim_fields,
            rhs_walker=ft.rhs_walker,
        )


_wire_handlers()


def _collect_feature_bindings(feat: dict[str, Any]) -> list[tuple[str, str]]:
    """[(dim_name, rhs)] for one feature. Used for interleaved per-feature
    binding so downstream geometry sees target sizes, not placeholders."""
    ft = FEATURE_REGISTRY.get(feat["type"])
    if ft is None:
        return []
    return ft.collect_rhs_bindings(feat)


def _collect_bindings(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """Whole-spec bindings in feature order. Kept for callers that want a
    flat view of what was/will be applied."""
    out: list[tuple[str, str]] = []
    for feat in spec["features"]:
        out.extend(_collect_feature_bindings(feat))
    return out


# Back-compat alias: legacy code/tests may import HANDLERS or DIM_FIELD_MAP.
HANDLERS = {name: ft.handler for name, ft in FEATURE_REGISTRY.items()}
DIM_FIELD_MAP = {name: ft.dim_fields for name, ft in FEATURE_REGISTRY.items()}


def _apply_bindings(doc: Any, bindings: list[tuple[str, str]]) -> list[int]:
    """Call EquationMgr.Add2 for each binding. Returns list of indices (or -1
    on failure)."""
    if not bindings:
        return []
    eq = doc.GetEquationMgr
    indices: list[int] = []
    for dim, rhs in bindings:
        formula = f'"{dim}" = {rhs}'
        idx = eq.Add2(-1, formula, True)
        indices.append(idx)
    return indices


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------


@dataclass
class Binding:
    """One EquationMgr.Add2 binding applied during a build."""
    dim: str           # e.g. "D1@SK_Body"
    rhs: str           # the RHS pasted into Add2 (verbatim from spec)
    add2_index: int    # value returned by EquationMgr.Add2; -1 = silent failure


@dataclass
class BuildResult:
    ok: bool
    features_built: list[str]
    bindings_added: list[Binding]
    error: str | None = None
    error_feature: str | None = None
    save_as: str | None = None
    # Full Python traceback if the build raised. Includes COM error codes
    # (HRESULT, PROGID, description) when the underlying exception is
    # pywintypes.com_error -- essential for debugging late-binding failures.
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable shape for CLI output. Single source of truth
        for the wire format so callers don't all reimplement encoding."""
        out: dict[str, Any] = {
            "ok": self.ok,
            "features_built": list(self.features_built),
            "bindings_added": [
                {"dim": b.dim, "rhs": b.rhs, "add2_index": b.add2_index}
                for b in self.bindings_added
            ],
            "save_as": self.save_as,
        }
        if self.error is not None:
            out["error"] = self.error
        if self.error_feature is not None:
            out["error_feature"] = self.error_feature
        if self.traceback is not None:
            out["traceback"] = self.traceback
        return out


def build(
    spec: dict[str, Any],
    no_dim: bool = False,
    save_as: str | None = None,
) -> BuildResult:
    """Build the spec into a fresh blank part on the running SW session.

    Caller is responsible for validating the spec first via spec.validator.validate.

    If `no_dim` is True: every {"rhs": "..."} in the spec is resolved against
    spec['locals'] upfront and substituted with a literal mm value. No
    AddDimension2 calls are made; no EquationMgr.Add2 bindings are applied.
    The resulting part has no equation links to locals.txt (editing locals
    will not propagate -- user must re-run ai-sw-build). This is the only
    way to avoid the ~16 manual ticks per MMP build on SW 2024 SP1 where
    the AddDimension2 popup can't be suppressed via any known toggle.

    If `save_as` is provided: after all features build successfully, the
    resulting part is saved to that absolute path via IModelDoc2.SaveAs3
    (version=0 i.e. current, save_options=0 i.e. default). The path must
    be absolute; missing parent directories are created. If the extension
    is not '.sldprt', it is appended.

    TRADE-OFF: SaveAs3 fires only after `build()` returns from the
    feature loop. In non-no_dim mode, the AddDimension2 popups still
    block the build mid-flight on SW 2024 SP1 -- the user must tick
    through them (~16 per MMP) BEFORE the save call happens. To save
    without any popups, combine `save_as` with `no_dim=True`.
    """
    if no_dim:
        spec = _resolve_rhs_in_spec(spec)

    sw = get_sw_app()
    doc = create_blank_part(sw)
    ctx = BuildContext(sw=sw, doc=doc, no_dim=no_dim)

    # Suppress the "Modify Dimension" popup that AddDimension2 fires by
    # default. App-level only; doc-level call was found to RE-ENABLE the
    # popup on a fresh doc (regression in MMP debug session 2026-05-16).
    prev_input_dim = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, False)

    try:
        # Link locals first so dim bindings can resolve var refs.
        # In no_dim mode, all rhs's have been resolved upfront so there
        # are no bindings to add; skip the link to avoid littering the
        # part with unused equation-manager state.
        if spec.get("locals") and not no_dim:
            link_locals(doc, spec["locals"])

        built: list[str] = []
        binding_results: list[Binding] = []
        # Track the most recent feature we touched, so a mid-loop exception
        # can report which one failed. Separated from the loop variable so
        # the typechecker can see it's always a string (or None).
        current_feat_name: str | None = None
        try:
            for feat in spec["features"]:
                current_feat_name = feat.get("name")
                handler = HANDLERS[feat["type"]]
                bf = handler(ctx, feat)

                # Stash plane info for plane-based sketches so child extrudes
                # can inherit the parent plane's outward normal as their axis.
                if bf.type in ("sketch_rectangle_on_plane", "sketch_circle_on_plane"):
                    bf.parent_plane_normal = PLANE_NORMALS[feat["plane"]]

                ctx.features_by_name[bf.name] = bf
                built.append(bf.name)

                if no_dim:
                    # rhs's were resolved upfront -- nothing to bind.
                    continue

                # Apply this feature's parametric bindings BEFORE the next
                # feature. Without this, a downstream cut may operate on a
                # sketch still at placeholder size, with no material to
                # remove (the original MMP Cut_FlangeRecess failure mode --
                # placeholder diameter 6mm was smaller than the 12mm
                # through-hole it sat over).
                feat_bindings = _collect_feature_bindings(feat)
                if feat_bindings:
                    indices = _apply_bindings(doc, feat_bindings)
                    for (d, r), i in zip(feat_bindings, indices):
                        binding_results.append(Binding(dim=d, rhs=r, add2_index=i))
                    # Force a rebuild so subsequent geometry sees the
                    # updated dim values, not the placeholder.
                    _ = doc.EditRebuild3
        except Exception as e:
            return BuildResult(
                ok=False,
                features_built=built,
                bindings_added=binding_results,
                error=str(e),
                error_feature=current_feat_name,
                traceback=traceback.format_exc(),
            )

        # Final rebuild for good measure
        _ = doc.EditRebuild3

        saved_path: str | None = None
        if save_as is not None:
            # Resolve to absolute (SW requires absolute paths for SaveAs)
            # and force the .sldprt extension. Create the parent dir if
            # missing so SaveAs3 doesn't fail on a fresh output tree.
            out_path = Path(save_as)
            if out_path.suffix.lower() != ".sldprt":
                out_path = out_path.with_suffix(".sldprt")
            out_path = out_path.resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # SaveAs3(path, version_int=0 i.e. current, save_options=0 i.e.
            # default). Per pywin32 late-binding this returns a single bool.
            save_ok = bool(doc.SaveAs3(str(out_path), 0, 0))
            if not save_ok:
                raise RuntimeError(
                    f"doc.SaveAs3 returned False for {out_path}"
                )
            saved_path = str(out_path)

        return BuildResult(
            ok=True,
            features_built=built,
            bindings_added=binding_results,
            save_as=saved_path,
        )
    finally:
        # Always restore the user's preference, even on exception
        sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, prev_input_dim)
