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
    SW_CHAMFER_EQUAL_DISTANCE,
    SW_CHAMFER_ANGLE_DISTANCE,
    SW_CHAMFER_DISTANCE_DISTANCE,
    SW_FEATURE_CHAMFER_TANGENT_PROPAGATION,
    SW_FEATURE_SCOPE_ALL_BODIES,
    assert_args,
)


# swUserPreferenceToggle.swInputDimValOnCreate -- the toggle ID is NOT
# documented in the CHM enum (descriptions just say "see System Options").
# Empirically, ID=8 reads back False on this build but does NOT suppress
# the popup. Kept in place because it's harmless and may help on some
# SW builds; see MMP_DEBUG_SESSION.md for the full investigation.
SW_PREF_INPUT_DIM_VAL_ON_CREATE = 8

# swFeatureNameID_e.swFmFillet -- numeric value not exposed in the
# decompiled CHM enum table (text-only). Found empirically in Spike P
# (spikes/phase0/spike_p_fillet_pipeline.py) by probing CreateDefinition
# with ints 0..59 and checking which return object accepts
# .Initialize(swConstRadiusFillet). swFmFillet = 1 on SW 2024 SP1.
SW_FM_FILLET = 1

# swSimpleFilletType_e.swConstRadiusFillet -- value IS in the CHM enum
# table (constant radius == 0). The other useful values: swFaceFillet=2,
# swFullRoundFillet=3. v1 of the bridge supports only constant-radius.
SW_CONST_RADIUS_FILLET = 0


# Plane name -> outward-normal vector (in part coordinates, +X right, +Y up, +Z out of screen)
# Matches SW's default English template orientation:
#   Front Plane = XY plane (normal +Z)
#   Top   Plane = XZ plane (normal +Y)
#   Right Plane = YZ plane (normal +X)
PLANE_NORMALS: dict[str, tuple[float, float, float]] = {
    "Front": (0.0, 0.0, 1.0),
    "Top": (0.0, 1.0, 0.0),
    "Right": (1.0, 0.0, 0.0),
}
PLANE_FULL_NAME = {
    "Front": "Front Plane",
    "Top": "Top Plane",
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
    # For sketches: the outward normal of the parent (reference plane OR
    # face) in part coordinates. Used by the subsequent extrusion to set its
    # axis. Set for plane-based sketches by build() after the handler runs;
    # set for face-based sketches inside the handler (so the chain of stacked
    # extrudes correctly inherits direction).
    parent_plane_normal: tuple[float, float, float] | None = None
    # For face-based sketches only: world-coord origin of the parent face
    # (the point _select_extrude_face succeeded at). The child extrude that
    # consumes this sketch uses it as its extrude_origin so downstream face-
    # selects find faces in the right place along stacked-extrude chains.
    parent_face_origin: tuple[float, float, float] | None = None
    # For plane-based sketches with a `center` offset: the sketch's center
    # in part coords (meters), with the axis-aligned component zeroed.
    # The downstream extrude uses this as its extrude_origin so the +/-z
    # face center for a child face-sketch lands at the actual face centroid,
    # not at (0, 0, depth). Was the root cause of the original TensionBracket
    # bug -- plane sketches with `center` offsets recorded extrude_origin
    # as world-origin and the downstream face math went wrong.
    sketch_center_part: tuple[float, float, float] | None = None
    # For extrusions: the actual extrude axis (outward normal of the boss/cut),
    # origin of the base face in part coords, blind depth in meters, and the
    # `flip` flag (True = extrude in -axis direction). Used by child sketches
    # on this extrusion's faces to compute world coords.
    extrude_axis: tuple[float, float, float] | None = None
    extrude_origin: tuple[float, float, float] | None = None
    extrude_depth_m: float | None = None
    extrude_flip: bool = False
    # For sketches built on a rectangular profile: half-extents along the
    # sketch's local u-axis and v-axis (in meters). Set by the rectangle
    # sketch handlers. Used by side-face frames (+/-x, +/-y) to compute
    # the side-face plane equations on the parent extrusion. None means
    # "profile has no flat side faces" (e.g., a circle sketch produces a
    # cylinder whose side is curved and not accessible via this builder).
    sketch_extent_uv: tuple[float, float] | None = None


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


def _build_sketch_rectangle_on_plane(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
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
        cx_m,
        cy_m,
        0.0,
        cx_m + width_m / 2,
        cy_m + height_m / 2,
        0.0,
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

    # Stash the sketch center in part coords so the downstream extrude
    # gets the right extrude_origin. The third coord (axis-aligned) is
    # 0 here; build() handles z=0 for plane sketches and we don't know
    # the axis until build() injects parent_plane_normal.
    # Also stash the rectangle's half-extents so a downstream face-sketch
    # on a side face (+/-x, +/-y) can compute the side-face plane.
    return BuiltFeature(
        name=feat["name"],
        type=feat["type"],
        sw_object=sketch_feat,
        sketch_center_part=(cx_m, cy_m, 0.0),
        sketch_extent_uv=(width_m / 2, height_m / 2),
    )


def _build_sketch_circle_on_plane(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    plane = feat["plane"]
    full = PLANE_FULL_NAME[plane]
    ok = ctx.doc.SelectByID(full, "PLANE", 0.0, 0.0, 0.0)
    if not ok:
        raise RuntimeError(f"could not select {full}")

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    diameter_m = _literal_or_default(
        feat["diameter"], PLACEHOLDER_MM["circle_diameter_plane"]
    )
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
        dim_d = ctx.doc.AddDimension2(
            cx_m + radius_m + 0.005, cy_m + radius_m + 0.005, 0.0
        )
        if dim_d is None:
            raise RuntimeError("AddDimension2 returned None for diameter")
        _dismiss_dim_pane(ctx.doc)

    sm.InsertSketch(True)

    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no sketch produced by CreateCircle")
    sketch_feat.Name = feat["name"]

    return BuiltFeature(
        name=feat["name"],
        type=feat["type"],
        sw_object=sketch_feat,
        sketch_center_part=(cx_m, cy_m, 0.0),
    )


# Per-face sketch-frame table for a parent extrusion whose axis is +z
# (the only parent orientation supported for side faces in v1). For each
# face, we record:
#   u_axis: the sketch +u direction in part-frame (unit vector)
#   v_axis: the sketch +v direction in part-frame (unit vector)
# Together with the face-center point, they let us convert any sketch
# (u, v) point to part-frame coords for SelectByID.
#
# Discovered empirically by Spike U4 (2026-05-18) -- created a centered
# 30mm cube, sketched circles at sketch (u=+5, v=+3) on each side face,
# extruded outward bosses, and measured the boss-cap centers in part
# coords. The mapping below reproduces those observed centers.
#
#   +z face (top):  sketch +u -> part +x, sketch +v -> part +y
#   -z face (bot):  sketch +u -> part -x, sketch +v -> part +y
#   +x face (right):sketch +u -> part -z, sketch +v -> part +y
#   -x face (left): sketch +u -> part +z, sketch +v -> part +y
#   +y face (back): sketch +u -> part +x, sketch +v -> part -z
#   -y face (front):sketch +u -> part +x, sketch +v -> part +z
_FACE_UV_AXES_PARENT_PLUSZ: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "+z": ((1, 0, 0), (0, 1, 0)),
    "-z": ((-1, 0, 0), (0, 1, 0)),
    "+x": ((0, 0, -1), (0, 1, 0)),
    "-x": ((0, 0, 1), (0, 1, 0)),
    "+y": ((1, 0, 0), (0, 0, -1)),
    "-y": ((1, 0, 0), (0, 0, 1)),
}


@dataclass(frozen=True)
class FaceFrame:
    """The part-frame embedding of a face's sketch coordinate system.

    Lets a handler do:
      part_xyz = face_center + u * u_axis + v * v_axis
    to compute the part-frame click point for a sketch entity at (u, v).

    out_normal is the face's outward-pointing unit normal in part coords;
    used for boss/cut direction inheritance.
    """

    face_center: tuple[float, float, float]
    u_axis: tuple[float, float, float]
    v_axis: tuple[float, float, float]
    out_normal: tuple[float, float, float]


def _face_frame(parent: "BuiltFeature", face: str) -> FaceFrame:
    """Build the part-frame transform for a +z-axis parent extrusion's face.

    The parent must:
      - have extrude_axis == +/- z (the only supported parent orientation
        for side faces in v1; ±z faces also work for ±y, ±x parents)
      - for ±x/±y faces specifically: have sketch_extent_uv set (i.e. the
        parent profile is a rectangle, not a circle/arbitrary curve).
        Without extents we don't know where the side face lives.

    Raises RuntimeError with a clear message on any of these violations.
    """
    assert parent.extrude_origin is not None, f"{parent.name}: extrude_origin not set"
    assert parent.extrude_axis is not None, f"{parent.name}: extrude_axis not set"
    assert parent.extrude_depth_m is not None, f"{parent.name}: extrude_depth_m not set"
    ox, oy, oz = parent.extrude_origin
    ax, ay, az = parent.extrude_axis
    depth = parent.extrude_depth_m
    if parent.extrude_flip:
        ax, ay, az = -ax, -ay, -az

    # ±z faces: handled for any parent axis. Logic preserves prior behavior:
    #   "+z" face = outboard face (extrude_origin + axis * depth)
    #   "-z" face = inboard face (extrude_origin)
    if face in ("+z", "-z"):
        if face == "+z":
            fx0 = ox + ax * depth
            fy0 = oy + ay * depth
            fz0 = oz + az * depth
            out_nrm = (ax, ay, az)
        else:
            fx0, fy0, fz0 = ox, oy, oz
            out_nrm = (-ax, -ay, -az)
        # In-face sketch frame depends on parent axis orientation. Today
        # we only have a verified table for parent axis = +z (Front Plane).
        # For Top/Right Plane parents, fall back to the historical
        # mirror_u convention so existing parts don't regress.
        if abs(az) > 0.99:
            u_ax, v_ax = _FACE_UV_AXES_PARENT_PLUSZ[face]
        elif abs(ay) > 0.99:
            # Top Plane parent (axis +y). Sketch X -> part X, sketch Y -> part Z.
            # On the inboard "-z" of this parent (= -y of part), mirror u.
            if face == "+z":
                u_ax, v_ax = (1, 0, 0), (0, 0, 1)
            else:
                u_ax, v_ax = (-1, 0, 0), (0, 0, 1)
        else:
            # Right Plane parent (axis +x). Sketch X -> part Y, sketch Y -> part Z.
            if face == "+z":
                u_ax, v_ax = (0, 1, 0), (0, 0, 1)
            else:
                u_ax, v_ax = (0, -1, 0), (0, 0, 1)
        return FaceFrame(
            face_center=(fx0, fy0, fz0),
            u_axis=(float(u_ax[0]), float(u_ax[1]), float(u_ax[2])),
            v_axis=(float(v_ax[0]), float(v_ax[1]), float(v_ax[2])),
            out_normal=out_nrm,
        )

    # ±x, ±y faces: side faces. Only supported when parent axis is +/-z
    # (Front Plane parent) AND the parent profile has known half-extents
    # (rectangle, not circle).
    if abs(az) < 0.99:
        raise RuntimeError(
            f"side face '{face}' of '{parent.name}': v1 only supports +/-x "
            f"and +/-y side faces when the parent extrude axis is +/-z "
            f"(Front Plane). Parent's axis is ({ax:+.2f}, {ay:+.2f}, "
            f"{az:+.2f}). Use a Front-Plane sketch parent for side-face "
            f"work, or address the side face via +/-z on a child extrude."
        )
    if parent.sketch_extent_uv is None:
        raise RuntimeError(
            f"side face '{face}' of '{parent.name}': parent has no "
            f"sketch_extent_uv stashed. Side faces are only addressable on "
            f"extrusions whose profile is a rectangle (the rectangle's "
            f"half-extents define where the side faces sit). For circle/"
            f"arbitrary-curve profiles the side surface is curved and "
            f"can't be sketched on through this builder."
        )
    half_u, half_v = parent.sketch_extent_uv

    # extrude_origin records the sketch's center in part-frame (X, Y) for
    # +z-axis parents. So:
    #   +x side face plane: x = ox + half_u
    #   -x side face plane: x = ox - half_u
    #   +y side face plane: y = oy + half_v
    #   -y side face plane: y = oy - half_v
    # Face-center along the extrude axis: midway through the extrude depth.
    z_mid = oz + 0.5 * az * depth
    if face == "+x":
        face_center = (ox + half_u, oy, z_mid)
        out_nrm = (1.0, 0.0, 0.0)
    elif face == "-x":
        face_center = (ox - half_u, oy, z_mid)
        out_nrm = (-1.0, 0.0, 0.0)
    elif face == "+y":
        face_center = (ox, oy + half_v, z_mid)
        out_nrm = (0.0, 1.0, 0.0)
    elif face == "-y":
        face_center = (ox, oy - half_v, z_mid)
        out_nrm = (0.0, -1.0, 0.0)
    else:
        raise RuntimeError(f"unknown face label {face!r}")

    u_ax, v_ax = _FACE_UV_AXES_PARENT_PLUSZ[face]
    return FaceFrame(
        face_center=face_center,
        u_axis=(float(u_ax[0]), float(u_ax[1]), float(u_ax[2])),
        v_axis=(float(v_ax[0]), float(v_ax[1]), float(v_ax[2])),
        out_normal=out_nrm,
    )


def _sketch_uv_to_part(frame: FaceFrame, u_m: float, v_m: float) -> tuple[float, float, float]:
    """Convert sketch-frame (u, v) in meters to part-frame (x, y, z)."""
    cx, cy, cz = frame.face_center
    ux, uy, uz = frame.u_axis
    vx, vy, vz = frame.v_axis
    return (cx + u_m * ux + v_m * vx, cy + u_m * uy + v_m * vy,
            cz + u_m * uz + v_m * vz)


def _face_center_part_coords(
    parent: "BuiltFeature",
    face: str,
) -> tuple[float, float, float]:
    """The un-offset center of a parent extrusion's face in part coords (meters).

    Used by `_select_extrude_face` to seed its probe, AND by the face-sketch
    warning to decide whether to alert the user about the part-origin-
    projection-vs-face-center gotcha.
    """
    return _face_frame(parent, face).face_center


def _warn_face_sketch_offset(
    parent: "BuiltFeature",
    face: str,
    feat: dict[str, Any],
    in_face_keys: tuple[str, str],
) -> None:
    """Emit a one-line stderr warning when the user's face-sketch will
    land at the part-origin projection rather than the face centroid.

    Triggers when:
      - parent face center (in part frame) has a meaningful in-face
        component (>0.1 mm) -- i.e. the face doesn't sit on the part
        origin's projection along the face normal, AND
      - the spec's `center` field is missing or zero (no explicit shift)

    The warning includes the in-face offset (in sketch u/v) the user
    would need to add to put the child feature at the face centroid.
    This is the #1 source of "wrong-position child feature" bugs
    surfaced in the TensionBracket work; see docs/known_limitations.md.
    """
    import sys

    frame = _face_frame(parent, face)
    fx, fy, fz = frame.face_center
    # Project the face-center vector onto the sketch u/v axes to get the
    # in-face offset of the face center from the part-origin projection.
    # u = (face_center - 0) . u_axis ; v likewise.
    ux, uy, uz = frame.u_axis
    vx, vy, vz = frame.v_axis
    tu_mm = (fx * ux + fy * uy + fz * uz) * 1000.0
    tv_mm = (fx * vx + fy * vy + fz * vz) * 1000.0

    # If face is centered on origin (within 0.1 mm), no warning needed.
    if abs(tu_mm) < 0.1 and abs(tv_mm) < 0.1:
        return

    # If user explicitly set a center offset, assume they know what they're
    # doing and don't second-guess. We don't try to validate whether the
    # offset they picked matches the face center -- that's a richer check
    # than this warning is meant to do.
    center = feat.get("center", {})
    u_key, v_key = in_face_keys
    cu = float(center.get(u_key, 0.0))
    cv = float(center.get(v_key, 0.0))
    if abs(cu) > 0.001 or abs(cv) > 0.001:
        return

    print(
        f"WARNING: {feat['type']} '{feat['name']}' on parent "
        f"'{parent.name}' face {face}: parent face center is at "
        f"part-frame ({tu_mm:+.2f}, {tv_mm:+.2f}) mm, but the face-sketch "
        f"origin lands at (0, 0) (part-origin projection). The child "
        f"feature will be drawn relative to (0, 0), NOT the face center. "
        f"If you want it centered on the face, add "
        f'`"center": {{"{u_key}": {tu_mm:.2f}, "{v_key}": {tv_mm:.2f}}}` '
        f"to the spec entry. See docs/known_limitations.md section 1.",
        file=sys.stderr,
    )


def _select_extrude_face(
    ctx: BuildContext,
    parent: "BuiltFeature",
    face: str,
) -> tuple[bool, float, float, float]:
    """Select one of the 6 faces of an extrusion (+z, -z, +x, -x, +y, -y).

    Uses _face_frame to find the face center and in-face tangent axes.
    Tries the face center first; if that fails (e.g. earlier cut removed
    material at the center), spirals outward in the face's tangent plane
    until one offset hits material. Returns (ok, fx, fy, fz) where the
    coords are the point on the face that successfully selected (used
    downstream as the sketch origin reference for stacked extrudes).

    SelectByID("", "FACE", x, y, z) is unreliable on side faces of a
    multi-boss part: it can return True while picking a DIFFERENT face
    than the one geometrically at (x, y, z) -- empirically observed when
    the part has multiple recently-modified faces sharing screen-space
    proximity. We verify by querying IFace2.Normal after each pick and
    rejecting any face whose normal doesn't match `frame.out_normal`.
    On rejection, fall back to enumerating body faces and selecting via
    IEntity.Select2 (no Callout, late-binding-safe).
    """
    frame = _face_frame(parent, face)
    fx0, fy0, fz0 = frame.face_center
    ux, uy, uz = frame.u_axis
    vx, vy, vz = frame.v_axis
    nx_e, ny_e, nz_e = frame.out_normal

    def _matches_expected(face_obj: Any) -> bool:
        try:
            n = face_obj.Normal
            return (
                abs(n[0] - nx_e) < 0.1
                and abs(n[1] - ny_e) < 0.1
                and abs(n[2] - nz_e) < 0.1
            )
        except Exception:
            return False

    # Spiral of (du, dv) offsets in the face's local sketch frame. Each
    # (du, dv) is projected to part coords via the frame's u/v axes.
    # Distances chosen to handle small interior holes (1mm) up to large
    # voids (15mm). Worst case: spec asks for a face entirely consumed
    # by prior features -- raise on caller side.
    offsets_uv = [
        (0, 0),
        (0.001, 0),
        (0, 0.001),
        (-0.001, 0),
        (0, -0.001),
        (0.005, 0),
        (0, 0.005),
        (-0.005, 0),
        (0, -0.005),
        (0.015, 0),
        (0, 0.015),
        (-0.015, 0),
        (0, -0.015),
        (0.005, 0.005),
        (-0.005, -0.005),
        (0.015, 0.015),
        (-0.015, -0.015),
    ]
    for du, dv in offsets_uv:
        fx = fx0 + du * ux + dv * vx
        fy = fy0 + du * uy + dv * vy
        fz = fz0 + du * uz + dv * vz
        ctx.doc.ClearSelection2(True)
        if ctx.doc.SelectByID("", "FACE", fx, fy, fz):
            face_obj = ctx.doc.SelectionManager.GetSelectedObject6(1, -1)
            if _matches_expected(face_obj):
                return True, fx, fy, fz
            # Wrong face picked. Clear and keep trying other offsets;
            # may pick the right one. (e.g. a SelectByID at face-center
            # may hit a screen-occluding face but an off-center probe
            # lands on the intended face.)

    # SelectByID spiral exhausted. Fall back to body-face enumeration:
    # find the face whose normal matches frame.out_normal AND whose
    # closest point to (fx0, fy0, fz0) is within 1um. Then select via
    # IEntity.Select2 (no Callout arg, late-binding-safe).
    try:
        bodies = ctx.doc.GetBodies2(0, True)  # swSolidBody=0
    except Exception:
        return False, fx0, fy0, fz0
    for body in bodies:
        faces = body.GetFaces()
        if faces is None:
            continue
        for face_obj in faces:
            if not _matches_expected(face_obj):
                continue
            try:
                cp = face_obj.GetClosestPointOn(fx0, fy0, fz0)
            except Exception:
                continue
            if cp is None or len(cp) < 3:
                continue
            d2 = (cp[0] - fx0) ** 2 + (cp[1] - fy0) ** 2 + (cp[2] - fz0) ** 2
            if d2 > 1e-12:  # >1 micron away
                continue
            ctx.doc.ClearSelection2(True)
            if face_obj.Select2(False, 0):
                return True, cp[0], cp[1], cp[2]

    return False, fx0, fy0, fz0


def _build_sketch_rectangle_on_face(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Rectangle sketched on a face of an earlier extrusion. Used for stacked
    extrudes where each upper block's profile starts from the previous block's
    top face (e.g. TensionBracket cap-slab-cap stack)."""
    parent_name = feat["of_feature"]
    parent = ctx.features_by_name.get(parent_name)
    if parent is None:
        raise RuntimeError(f"sketch_rectangle_on_face: '{parent_name}' not built yet")
    if parent.extrude_axis is None:
        raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

    face = feat["face"]
    _warn_face_sketch_offset(parent, face, feat, ("u", "v"))

    # Build the face frame (validates parent axis/extents); used for the
    # face-center seed point and for the spiral-offset probe in
    # _select_extrude_face.
    _frame = _face_frame(parent, face)

    ok, fx, fy, fz = _select_extrude_face(ctx, parent, face)
    if not ok:
        raise RuntimeError(
            f"SelectByID returned False for {face} face of {parent_name} -- "
            f"tried center and offset points, none hit material"
        )

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    width_m = _literal_or_default(feat["width"], PLACEHOLDER_MM["rectangle_side"])
    height_m = _literal_or_default(feat["height"], PLACEHOLDER_MM["rectangle_side"])
    # Face-local center offset (u, v); default (0, 0) = face center.
    c = feat.get("center", {})
    cu_m = float(c.get("u", 0.0)) / 1000.0
    cv_m = float(c.get("v", 0.0)) / 1000.0

    # Same anchoring rationale as on-plane rectangles: CreateCenterRectangle
    # anchors the rect at its centroid via construction diagonals so dim
    # binding resizes both halves symmetrically.
    sm.CreateCenterRectangle(
        cu_m,
        cv_m,
        0.0,
        cu_m + width_m / 2,
        cv_m + height_m / 2,
        0.0,
    )

    # Driving dims D1 (width) and D2 (height). SKETCHSEGMENT picks use
    # part-frame coords; transform sketch (u, v) to part via FaceFrame.
    # This works uniformly for all 6 faces (+/-z and side faces).
    if not ctx.no_dim:
        ctx.doc.ClearSelection2(True)
        top_v = cv_m + height_m / 2
        tx, ty, tz = _sketch_uv_to_part(_frame, cu_m, top_v)
        if not ctx.doc.SelectByID("", "SKETCHSEGMENT", tx, ty, tz):
            raise RuntimeError(
                f"could not select rect top edge for width dim "
                f"(face={face}, center=({cu_m*1000:.1f}, {cv_m*1000:.1f}) mm)"
            )
        dwx, dwy, dwz = _sketch_uv_to_part(_frame, cu_m, top_v + 0.005)
        dim_w = ctx.doc.AddDimension2(dwx, dwy, dwz)
        if dim_w is None:
            raise RuntimeError("AddDimension2 returned None for width on face")
        _dismiss_dim_pane(ctx.doc)

        ctx.doc.ClearSelection2(True)
        left_u = cu_m - width_m / 2
        lx, ly, lz = _sketch_uv_to_part(_frame, left_u, cv_m)
        if not ctx.doc.SelectByID("", "SKETCHSEGMENT", lx, ly, lz):
            raise RuntimeError(
                f"could not select rect left edge for height dim "
                f"(face={face}, center=({cu_m*1000:.1f}, {cv_m*1000:.1f}) mm)"
            )
        dhx, dhy, dhz = _sketch_uv_to_part(_frame, cu_m - width_m / 2 - 0.005, cv_m)
        dim_h = ctx.doc.AddDimension2(dhx, dhy, dhz)
        if dim_h is None:
            raise RuntimeError("AddDimension2 returned None for height on face")
        _dismiss_dim_pane(ctx.doc)

    sm.InsertSketch(True)

    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no rectangle sketch produced on face")
    sketch_feat.Name = feat["name"]

    # The downstream boss_extrude_blind needs the FACE's outward normal as
    # the extrude direction (so the boss grows outward from the face).
    # _face_frame supplies this consistently for all 6 face labels.
    return BuiltFeature(
        name=feat["name"],
        type=feat["type"],
        sw_object=sketch_feat,
        parent_plane_normal=_frame.out_normal,
        parent_face_origin=(fx, fy, fz),
        sketch_extent_uv=(width_m / 2, height_m / 2),
    )


def _build_sketch_circle_on_face(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    parent_name = feat["of_feature"]
    parent = ctx.features_by_name.get(parent_name)
    if parent is None:
        raise RuntimeError(f"sketch_circle_on_face: '{parent_name}' not built yet")
    if parent.extrude_axis is None:
        raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

    # Compute the face center in part coordinates.
    # The face spec ("+z", "-z", "+x", "-x", "+y", "-y") is in the parent's
    # local frame. +z/-z are the outboard/inboard faces along the parent's
    # extrude axis; +/-x +/-y are the four SIDE faces (perpendicular to
    # the axis). Side faces require a parent with axis +/-z AND a known
    # rectangle profile (so we can locate the face plane).
    face = feat["face"]
    _warn_face_sketch_offset(parent, face, feat, ("u", "v"))

    _frame = _face_frame(parent, face)

    ok, fx, fy, fz = _select_extrude_face(ctx, parent, face)
    if not ok:
        raise RuntimeError(
            f"SelectByID returned False for {face} face of {parent_name} -- "
            f"tried center and offset points, none hit material"
        )

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    diameter_m = _literal_or_default(
        feat["diameter"], PLACEHOLDER_MM["circle_diameter_face"]
    )
    radius_m = diameter_m / 2
    # In a face-based sketch, the sketch origin is at the face center by default.
    # 'center' offset is in sketch-local u/v (mm).
    c = feat.get("center", {})
    u_m = float(c.get("u", 0.0)) / 1000.0
    v_m = float(c.get("v", 0.0)) / 1000.0

    sm.CreateCircle(u_m, v_m, 0.0, u_m + radius_m, v_m, 0.0)

    # Add diameter dim. SelectByID for SKETCHSEGMENT uses PART-frame
    # coords; transform sketch (u, v) perimeter probe points to part
    # via FaceFrame. This works uniformly for all 6 faces.
    # Skipped in no_dim mode -- geometry is already at target diameter.
    if not ctx.no_dim:
        ctx.doc.ClearSelection2(True)
        # Four cardinal points on the circle perimeter, in sketch coords.
        perim_uv = [
            (u_m + radius_m, v_m),
            (u_m, v_m + radius_m),
            (u_m - radius_m, v_m),
            (u_m, v_m - radius_m),
        ]
        selected = False
        for pu, pv in perim_uv:
            sx, sy, sz = _sketch_uv_to_part(_frame, pu, pv)
            if ctx.doc.SelectByID("", "SKETCHSEGMENT", sx, sy, sz):
                selected = True
                break
        if not selected:
            raise RuntimeError(
                f"could not select face-sketch circle for diameter dim "
                f"(face={face}, u={u_m*1000:.1f}mm, r={radius_m*1000:.2f}mm)"
            )
        dx, dy, dz = _sketch_uv_to_part(
            _frame, u_m + radius_m + 0.005, v_m + radius_m + 0.005
        )
        dim_d = ctx.doc.AddDimension2(dx, dy, dz)
        if dim_d is None:
            raise RuntimeError("AddDimension2 returned None for face-sketch diameter")
        _dismiss_dim_pane(ctx.doc)

    sm.InsertSketch(True)

    sketch_feat = ctx.doc.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise RuntimeError("no sketch produced on face")
    sketch_feat.Name = feat["name"]

    # Downstream extrude direction = face's outward normal in part frame.
    return BuiltFeature(
        name=feat["name"],
        type=feat["type"],
        sw_object=sketch_feat,
        parent_plane_normal=_frame.out_normal,
        parent_face_origin=(fx, fy, fz),
    )


def _build_sketch_circles_on_face(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
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
    # NOTE: no _warn_face_sketch_offset here. sketch_circles_on_face is the
    # multi-hole variant; users already specify explicit per-circle u/v
    # positions, so they've opted into the "I know where these go" mode.
    # The single-center warning would just be noise for hole patterns where
    # the natural reference is the part origin (e.g. MMP motor holes at
    # u=+/-12.5 are explicitly relative to part X=0).

    # Build frame -- validates parent axis/extents for side faces.
    _frame = _face_frame(parent, face)

    ok, fx, fy, fz = _select_extrude_face(ctx, parent, face)
    if not ok:
        raise RuntimeError(
            f"face select returned False for {face} face of {parent_name} -- "
            f"tried center and offsets"
        )

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    # CreateCircle takes sketch-local coords. SelectByID and AddDimension2
    # take PART-frame coords; transform sketch (u, v) via FaceFrame. This
    # works uniformly for all 6 faces (the FaceFrame's u-axis encodes
    # the X-mirror on -z faces and the in-face orientation for side faces).
    for k, c in enumerate(feat["circles"]):
        u_m = float(c["u"]) / 1000.0
        v_m = float(c["v"]) / 1000.0
        diameter_m = _literal_or_default(
            c["diameter"], PLACEHOLDER_MM["circle_diameter_multi"]
        )
        radius_m = diameter_m / 2
        sm.CreateCircle(u_m, v_m, 0.0, u_m + radius_m, v_m, 0.0)
        if ctx.no_dim:
            # Geometry already at target size; no dim binding needed.
            continue
        # Dimension this circle BEFORE creating the next one, so dim
        # numbering matches array index: first circle -> D1, second -> D2.
        ctx.doc.ClearSelection2(True)
        perim_uv = [
            (u_m + radius_m, v_m),
            (u_m, v_m + radius_m),
            (u_m - radius_m, v_m),
            (u_m, v_m - radius_m),
        ]
        selected = False
        for pu, pv in perim_uv:
            sx, sy, sz = _sketch_uv_to_part(_frame, pu, pv)
            if ctx.doc.SelectByID("", "SKETCHSEGMENT", sx, sy, sz):
                selected = True
                break
        if not selected:
            raise RuntimeError(
                f"could not select circle #{k} (perimeter at radius {radius_m*1000:.2f}mm "
                f"from sketch center ({u_m*1000:.1f}, {v_m*1000:.1f}) mm, "
                f"face={face}) -- tried 4 cardinal perimeter points in part frame"
            )
        # Place leader offset from the circle, with stagger so consecutive
        # circles' dim leaders don't overlap.
        lead_offset = 0.005 + 0.003 * k
        dx, dy, dz = _sketch_uv_to_part(
            _frame, u_m + radius_m + lead_offset, v_m + lead_offset
        )
        dim = ctx.doc.AddDimension2(dx, dy, dz)
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
        True,  # 1  Sd (single direction)
        flip,  # 2  Flip
        False,  # 3  Dir (use sketch normal)
        end_cond,  # 4  T1
        0,  # 5  T2
        depth_m,  # 6  D1
        0.0,  # 7  D2
        False,  # 8  Dchk1
        False,  # 9  Dchk2
        False,  # 10 Ddir1
        False,  # 11 Ddir2
        0.0,  # 12 Dang1
        0.0,  # 13 Dang2
        False,  # 14 OffsetReverse1
        False,  # 15 OffsetReverse2
        False,  # 16 TranslateSurface1
        False,  # 17 TranslateSurface2
        True,  # 18 Merge
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
        SW_START_SKETCH_PLANE,  # 21 T0
        0.0,  # 22 StartOffset
        False,  # 23 FlipStartOffset
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
        True,  # 1  Sd (single-ended)
        flip,  # 2  Flip
        False,  # 3  Dir
        end_cond,  # 4  T1
        0,  # 5  T2
        depth_m,  # 6  D1
        0.0,  # 7  D2
        False,  # 8  Dchk1
        False,  # 9  Dchk2
        False,  # 10 Ddir1
        False,  # 11 Ddir2
        0.0,  # 12 Dang1
        0.0,  # 13 Dang2
        False,  # 14 OffsetReverse1
        False,  # 15 OffsetReverse2
        False,  # 16 TranslateSurface1
        False,  # 17 TranslateSurface2
        False,  # 18 NormalCut (sheet metal only)
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
        True,  # 21 AssemblyFeatureScope
        True,  # 22 AutoSelectComponents
        False,  # 23 PropagateFeatureToParts
        SW_START_SKETCH_PLANE,  # 24 T0
        0.0,  # 25 StartOffset
        False,  # 26 FlipStartOffset
        False,  # 27 OptimizeGeometry (sheet metal only)
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

    f = _call_feature_extrusion(
        ctx, end_cond=SW_END_COND_BLIND, depth_m=depth_m, flip=flip
    )
    f.Name = feat["name"]

    # Inherit the axis from the parent sketch. For plane-based sketches
    # build() stashes the plane's outward normal; for face-based sketches the
    # handler stashes the face's outward normal directly. Either way the
    # downstream extrude axis matches.
    if sketch.parent_plane_normal is None:
        raise RuntimeError(
            f"sketch '{sketch_name}' has no parent_plane_normal stashed; "
            f"build() should set it on every plane-based sketch and the "
            f"face-based sketch handlers should set it too"
        )
    # Pick the extrude_origin for this boss:
    # - Face-based sketch: the parent face's part-coord origin (set by the
    #   face-sketch handler).
    # - Plane-based sketch with a `center` offset: the sketch's center,
    #   converted from sketch-local (X, Y) to part-frame based on the
    #   parent plane. Front Plane (axis +Z): (cx, cy, 0). Top Plane
    #   (axis +Y): (cx, 0, cy). Right Plane (axis +X): (0, cx, cy).
    #   Without this, a plane sketch shifted off origin (e.g. TensionBracket
    #   inboard cap at y=7.5) would record extrude_origin=(0,0,0) and
    #   downstream face-selects would probe the wrong centroid -- the
    #   original TensionBracket "slab hanging off in -Y" failure mode.
    # - Plane-based sketch centered on origin: defaults to (0, 0, 0).
    if sketch.parent_face_origin is not None:
        extrude_origin = sketch.parent_face_origin
    elif sketch.sketch_center_part is not None:
        cx, cy, _ = sketch.sketch_center_part
        ax, ay, az = sketch.parent_plane_normal
        if abs(az) > 0.99:  # Front Plane: sketch XY -> part XY
            extrude_origin = (cx, cy, 0.0)
        elif abs(ay) > 0.99:  # Top Plane: sketch X -> part X, sketch Y -> part Z
            extrude_origin = (cx, 0.0, cy)
        else:  # Right Plane: sketch X -> part Y, sketch Y -> part Z
            _ = ax  # axis fully determined by ax dominance
            extrude_origin = (0.0, cx, cy)
    else:
        extrude_origin = (0.0, 0.0, 0.0)
    return BuiltFeature(
        name=feat["name"],
        type=feat["type"],
        sw_object=f,
        extrude_axis=sketch.parent_plane_normal,
        extrude_origin=extrude_origin,
        extrude_depth_m=depth_m,
        extrude_flip=flip,
        sketch_extent_uv=sketch.sketch_extent_uv,
    )


def _build_cut_extrude_through_all(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
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


def _select_edges_by_points(
    ctx: BuildContext, edge_points_mm: "list[dict[str, float]]"
) -> int:
    """Accumulate model edges into the selection set, one per (x, y, z) point.

    Replaces a naive loop of 5-arg `SelectByID("", "EDGE", x, y, z)` calls,
    which silently fail to accumulate -- each call replaces the prior
    selection so only the LAST edge ends up selected. Spike Q3
    (2026-05-17) confirmed this: SelectionMgr.GetSelectedObjectCount2(-1)
    stayed at 1 across 4 calls.

    Naive alternatives that ALSO don't work under pywin32 late binding:
      - `doc.Extension.SelectByID2(..., Append=True, ..., Callout=None, ...)`
        raises com_error('Type mismatch', ..., 8) -- Callout OUT-IDispatch
        marshalling failure
      - `IEntity.Select4(Append, Callout)` -- same Callout failure (arg 2)

    Working path (Spike Q4 GREEN, 2026-05-17):
      1. IPartDoc.GetBodies2(swSolidBody=0, bVisibleOnly=True) -> bodies
      2. For each body, body.GetEdges() -> all IEdge instances
      3. For each target point, find the closest edge via
         IEdge.GetClosestPointOn(x, y, z); zero squared-distance means
         the point is on the edge
      4. IEntity.Select2(Append=True, Mark=0) -- the older variant, NO
         Callout, marshalls cleanly

    Args are in mm; converted to meters internally. Raises if any point
    fails to match an edge within 1um.
    """
    ctx.doc.ClearSelection2(True)

    # Walk all solid bodies and collect their edges into one list. Most
    # parts have a single body; multi-body parts are rare in v1's scope
    # but cheap to support.
    try:
        bodies = ctx.doc.GetBodies2(0, True)  # swBodyType_e.swSolidBody=0
    except Exception as e:
        raise RuntimeError(f"GetBodies2 failed: {e!r}")
    if bodies is None or len(bodies) == 0:
        raise RuntimeError("part has no solid bodies; cannot select edges")

    all_edges: list = []
    for body in bodies:
        edges = body.GetEdges
        if callable(edges):
            edges = edges()
        if edges is None:
            continue
        all_edges.extend(edges)
    if not all_edges:
        raise RuntimeError("no edges on any body; cannot select")

    n_selected = 0
    for i, p in enumerate(edge_points_mm):
        x_m = float(p["x"]) / 1000.0
        y_m = float(p["y"]) / 1000.0
        z_m = float(p["z"]) / 1000.0

        # Find the closest edge. Threshold: 1 micron squared = 1e-12 m^2.
        best_edge, best_d2 = None, 1e18
        for edge in all_edges:
            try:
                cp = edge.GetClosestPointOn(x_m, y_m, z_m)
            except Exception:
                continue
            if cp is None:
                continue
            d2 = (cp[0] - x_m) ** 2 + (cp[1] - y_m) ** 2 + (cp[2] - z_m) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_edge = edge
        if best_edge is None or best_d2 > 1e-12:
            raise RuntimeError(
                f"edge #{i} at part ({p['x']}, {p['y']}, {p['z']}) mm "
                f"matches no edge within 1um (best squared distance "
                f"{best_d2:.3e} m^2)"
            )
        # IEntity.Select2(Append, Mark) -- no Callout, marshalls cleanly
        ok = best_edge.Select2(True, 0)
        if not ok:
            raise RuntimeError(
                f"IEntity.Select2(append=True, mark=0) returned False on "
                f"edge #{i} at part ({p['x']}, {p['y']}, {p['z']}) mm"
            )
        n_selected += 1
    return n_selected


def _build_fillet_constant_radius(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Constant-radius edge fillet via the SW 2020+ canonical pipeline.

    FeatureFillet3 (single-call) is marked obsolete for constant-radius
    fillets per the decompiled CHM. The recommended path is:
        data = fm.CreateDefinition(swFmFillet)
        data.Initialize(swConstRadiusFillet)
        data.DefaultRadius = radius_m
        <select edges>
        fm.CreateFeature(data)

    Spike P (spikes/phase0/spike_p_fillet_pipeline.py) verified the
    full pipeline works via pywin32 late binding -- the data-object
    arg to CreateFeature DOES marshal correctly (unlike Callout/OUT
    params that have failed on this build).

    v1 supports constant-radius only and selects edges by part-coord
    points (one per edge). No "all edges of face" sugar yet; the spec
    enumerates each edge midpoint explicitly.
    """
    radius_m = _literal_or_default(feat["radius"], 1.0)  # 1mm placeholder

    fm = ctx.doc.FeatureManager
    data = fm.CreateDefinition(SW_FM_FILLET)
    if data is None:
        raise RuntimeError("CreateDefinition(swFmFillet) returned None")
    ok = data.Initialize(SW_CONST_RADIUS_FILLET)
    if not ok:
        raise RuntimeError("ISimpleFilletFeatureData2.Initialize(0) returned False")

    # Set the default radius. Property assignment on the CDispatch worked
    # in Spike P; readback confirmed value round-trips.
    data.DefaultRadius = radius_m

    # Accumulate edges via the shared helper. The naive
    # SelectByID('', 'EDGE', x, y, z) loop does NOT accumulate -- each
    # call replaces. See _select_edges_by_points docstring.
    n_selected = _select_edges_by_points(ctx, feat["edges"])
    if n_selected == 0:
        raise RuntimeError("no edges selected; fillet would no-op")

    # CreateFeature picks up the current selection set.
    f = fm.CreateFeature(data)
    if f is None:
        raise RuntimeError(
            f"CreateFeature returned None for fillet on {n_selected} edges "
            f"with radius {radius_m*1000:.2f}mm"
        )
    f.Name = feat["name"]

    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _build_chamfer_edge(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Edge chamfer via IFeatureManager::InsertFeatureChamfer (8-arg call).

    Modes and the args that actually commit geometry on SW 2024 SP1
    (confirmed GREEN in Spike Q11/Q12, 2026-05-17):

      equal_distance -> ChamferType=swChamferDistanceDistance=2,
                        Width=OtherDist=distance_m.
                        swChamferEqualDistance=16 is listed in the CHM enum
                        but never commits geometry on this build -- the
                        feature appears in the tree with GetEdgeCount=4 but
                        body topology stays 6F/12E (plain box). DistDist with
                        equal distances is geometrically identical.

      distance_angle -> ChamferType=swChamferAngleDistance=1,
                        Width=distance_m, Angle=angle in RADIANS.
                        The CHM says "degrees" but empirically both degrees
                        and radians produce the same geometry for 45deg;
                        using radians matches the broader SW API convention.

    Options: tangent-propagation flag (4) is always set; flip adds bit 1.
    """
    import math

    mode = feat["mode"]
    distance_m = _literal_or_default(feat["distance"], 1.0)  # 1mm placeholder

    options = SW_FEATURE_CHAMFER_TANGENT_PROPAGATION
    if feat.get("flip", False):
        options |= 1  # swFeatureChamferFlipDirection

    if mode == "equal_distance":
        # Use DistanceDistance with both sides equal -- swChamferEqualDistance=16
        # never commits geometry on SW 2024 SP1 (Spike Q12).
        chamfer_type = SW_CHAMFER_DISTANCE_DISTANCE
        width = distance_m
        angle_rad = 0.0
        other_dist = distance_m
    elif mode == "distance_angle":
        chamfer_type = SW_CHAMFER_ANGLE_DISTANCE
        width = distance_m
        angle_value = feat["angle"]
        if isinstance(angle_value, dict) and "rhs" in angle_value:
            angle_deg = 45.0  # placeholder; rebound on next ctx rebuild
        else:
            angle_deg = float(angle_value)
        angle_rad = angle_deg * math.pi / 180.0
        other_dist = 0.0
    else:
        raise RuntimeError(f"chamfer_edge: unknown mode {mode!r}")

    n_selected = _select_edges_by_points(ctx, feat["edges"])
    if n_selected == 0:
        raise RuntimeError("no edges selected; chamfer would no-op")

    fm = ctx.doc.FeatureManager
    args = (options, chamfer_type, width, angle_rad, other_dist, 0.0, 0.0, 0.0)
    assert_args("IFeatureManager.InsertFeatureChamfer", args)
    f = fm.InsertFeatureChamfer(*args)
    if f is None:
        raise RuntimeError(
            f"InsertFeatureChamfer returned None for chamfer on {n_selected} "
            f"edges, mode={mode}, distance={distance_m * 1000:.2f}mm"
        )
    f.Name = feat["name"]
    ctx.doc.ForceRebuild3(False)

    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _mark_first_selection(ctx: BuildContext, mark: int) -> None:
    """Apply a selection mark to the most-recently-selected item.

    Wraps ISelectionMgr.SetSelectedObjectMark(AtIndex=1, Mark, Action=0).
    Used after a SelectByID call to retroactively tag the selection with
    a role (e.g. direction edge, mirror plane).

    Why this exists: doc.Extension.SelectByID2 takes a mark arg directly,
    but its 8th positional arg (Callout, OUT-typed IDispatch) fails to
    marshal through pywin32 late binding -- raises com_error('Type
    mismatch', ..., 8). Empirically verified 2026-05-17 in Spike R; same
    class of failure as the prior SelectByID2 issue in MMP_DEBUG_SESSION.
    Workaround: call 5-arg SelectByID (no Callout) then apply the mark
    via SelectionMgr.
    """
    sel_mgr = ctx.doc.SelectionManager
    # Action=0 is swSelectionMarkSet (per swSelectionMarkAction_e in CHM)
    if not sel_mgr.SetSelectedObjectMark(1, mark, 0):
        raise RuntimeError(
            f"SetSelectedObjectMark(1, mark={mark}, set) returned False; "
            f"selection set may be empty"
        )


def _build_linear_pattern(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Linear pattern of a seed feature along a direction edge.

    Uses the marked-selection convention required by pattern features:
      mark = 1 (swSelPatternRefEdge) -- the direction reference edge
      mark = 4 (swSelPatternBody)    -- the seed feature

    Order matters. SelectByID is non-appending by default (5-arg form
    has no Append param), so:
      1. SelectByID(EDGE) for direction -- starts a fresh selection set
      2. SetSelectedObjectMark(1, mark=1) -- tag as direction
      3. seed.Select2(append=True, mark=4) -- add seed without clearing
    Reverse order clears the seed.

    Then calls FeatureLinearPattern5 (22 args). Marked obsolete in CHM
    in favor of CreateDefinition+ILinearPatternFeatureData, but
    empirically still works on SW 2024 SP1 (Spike R GREEN 2026-05-17).
    """
    seed_name = feat["seed"]
    if seed_name not in ctx.features_by_name:
        # Defensive: validator should already have caught this.
        raise RuntimeError(f"linear_pattern seed '{seed_name}' not yet built")
    seed_built = ctx.features_by_name[seed_name]

    spacing_m = _literal_or_default(feat["spacing"], 10.0)  # 10mm placeholder
    count = int(feat["count"])
    flip = bool(feat.get("flip", False))

    # 1. Direction edge first (non-appending SelectByID)
    ctx.doc.ClearSelection2(True)
    d = feat["direction"]
    dx_m = float(d["x"]) / 1000.0
    dy_m = float(d["y"]) / 1000.0
    dz_m = float(d["z"]) / 1000.0
    if not ctx.doc.SelectByID("", "EDGE", dx_m, dy_m, dz_m):
        raise RuntimeError(
            f"could not select direction edge at part ({d['x']}, {d['y']}, "
            f"{d['z']}) mm -- point not on any edge of current geometry"
        )
    _mark_first_selection(ctx, mark=1)

    # 2. Seed via IFeature.Select2 with append=True
    if seed_built.sw_object is None:
        raise RuntimeError(f"linear_pattern seed '{seed_name}' has no sw_object handle")
    if not seed_built.sw_object.Select2(True, 4):
        raise RuntimeError(f"IFeature.Select2 on seed '{seed_name}' returned False")

    fm = ctx.doc.FeatureManager
    args = (
        count,
        spacing_m,
        1,
        0.0,  # Num1, Spacing1, Num2, Spacing2
        flip,
        False,  # FlipDir1, FlipDir2
        "",
        "",  # DName1, DName2
        False,
        False,  # GeometryPattern, VaryInstance
        False,
        False,  # HasOffset1, HasOffset2
        False,
        False,  # CtrlByNum1, CtrlByNum2
        False,
        False,  # FromCentroid1, FromCentroid2
        False,
        False,  # RevOffset1, RevOffset2
        0.0,
        0.0,  # Offset1, Offset2
        False,
        False,  # D2PatternSeedOnly, SyncSubAssemblies
    )
    assert_args("IFeatureManager.FeatureLinearPattern5", args)
    f = fm.FeatureLinearPattern5(*args)
    if f is None:
        raise RuntimeError(
            f"FeatureLinearPattern5 returned None (seed='{seed_name}', "
            f"count={count}, spacing={spacing_m * 1000:.2f}mm). The "
            f"selected edge may not run in the direction you expect -- "
            f"on a box, perimeter edges of a face are perpendicular to "
            f"the face's normal but oriented along the face's other axis."
        )
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _build_circular_pattern(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Circular pattern of a seed feature around a rotation axis.

    Selection marks (same as linear_pattern):
      mark = 1 -- the axis reference (circular edge or cylindrical face)
      mark = 4 -- the seed feature

    Axis selection strategy: try EDGE first (the spec's `axis` point should
    sit on a circular model edge such as the rim of a cylindrical hub),
    then fall back to FACE (a cylindrical face -- SW infers the axis of
    revolution from it). Both verified GREEN in Spike T (2026-05-17).

    Calls FeatureCircularPattern5 (14 args). Marked obsolete in CHM in
    favor of CreateDefinition+ICircularPatternFeatureData, but empirically
    still works on SW 2024 SP1 (same outcome as the linear_pattern path).
    """
    import math

    seed_name = feat["seed"]
    if seed_name not in ctx.features_by_name:
        raise RuntimeError(f"circular_pattern seed '{seed_name}' not yet built")
    seed_built = ctx.features_by_name[seed_name]

    count = int(feat["count"])
    total_angle_deg = float(feat.get("total_angle", 360.0))
    total_angle_rad = total_angle_deg * math.pi / 180.0
    flip = bool(feat.get("flip", False))

    a = feat["axis"]
    ax_m = float(a["x"]) / 1000.0
    ay_m = float(a["y"]) / 1000.0
    az_m = float(a["z"]) / 1000.0

    # 1. Axis reference -- try EDGE, then FACE (non-appending SelectByID)
    ctx.doc.ClearSelection2(True)
    ok = ctx.doc.SelectByID("", "EDGE", ax_m, ay_m, az_m)
    if not ok:
        ok = ctx.doc.SelectByID("", "FACE", ax_m, ay_m, az_m)
        if not ok:
            raise RuntimeError(
                f"could not select axis reference at part ({a['x']}, "
                f"{a['y']}, {a['z']}) mm -- point is not on any circular "
                f"edge or cylindrical face of current geometry"
            )
    _mark_first_selection(ctx, mark=1)

    # 2. Seed via IFeature.Select2 with append=True
    if seed_built.sw_object is None:
        raise RuntimeError(
            f"circular_pattern seed '{seed_name}' has no sw_object handle"
        )
    if not seed_built.sw_object.Select2(True, 4):
        raise RuntimeError(f"IFeature.Select2 on seed '{seed_name}' returned False")

    fm = ctx.doc.FeatureManager
    args = (
        count,  # Number
        total_angle_rad,  # Spacing (= total sweep angle when EqualSpacing=True)
        flip,  # FlipDirection
        "",  # DName
        False,  # GeometryPattern
        True,  # EqualSpacing
        False,  # VaryInstance
        False,  # SyncSubAssemblies
        False,  # BDir2
        False,  # BSymmetric
        1,  # Number2
        0.0,  # Spacing2
        "",  # DName2
        False,  # EqualSpacing2
    )
    assert_args("IFeatureManager.FeatureCircularPattern5", args)
    f = fm.FeatureCircularPattern5(*args)
    if f is None:
        raise RuntimeError(
            f"FeatureCircularPattern5 returned None (seed='{seed_name}', "
            f"count={count}, total_angle={total_angle_deg:.1f}deg). The "
            f"axis point may not lie on a circular edge or cylindrical "
            f"face -- try a point exactly on a model edge or pick a "
            f"cylindrical face's mid-surface point."
        )
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _build_mirror_feature(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Mirror a seed feature about one of the three default reference planes.

    Selection marks:
      mark = 2  -- the mirror plane (Front/Top/Right Plane by name)
      mark = 1  -- the seed feature(s) to mirror

    Same order-matters reasoning as _build_linear_pattern:
      1. SelectByID('Front Plane', 'PLANE') -- starts fresh selection
      2. SetSelectedObjectMark(1, mark=2) -- tag as mirror plane
      3. seed.Select2(append=True, mark=1) -- add seed

    Verified GREEN on SW 2024 SP1 in Spike S (2026-05-17).
    """
    seed_name = feat["seed"]
    if seed_name not in ctx.features_by_name:
        raise RuntimeError(f"mirror_feature seed '{seed_name}' not yet built")
    seed_built = ctx.features_by_name[seed_name]

    plane = feat["plane"]
    full_plane_name = PLANE_FULL_NAME[plane]

    # 1. Plane by name (non-appending)
    ctx.doc.ClearSelection2(True)
    if not ctx.doc.SelectByID(full_plane_name, "PLANE", 0.0, 0.0, 0.0):
        raise RuntimeError(f"could not select mirror plane '{full_plane_name}'")
    _mark_first_selection(ctx, mark=2)

    # 2. Seed via IFeature.Select2 with append=True
    if seed_built.sw_object is None:
        raise RuntimeError(f"mirror_feature seed '{seed_name}' has no sw_object handle")
    if not seed_built.sw_object.Select2(True, 1):
        raise RuntimeError(f"IFeature.Select2 on seed '{seed_name}' returned False")

    fm = ctx.doc.FeatureManager
    args = (
        False,  # BMirrorBody (False = feature mirror)
        False,  # BGeometryPattern
        False,  # BMerge (body-only; irrelevant here)
        False,  # BKnit (surface-only; irrelevant here)
        SW_FEATURE_SCOPE_ALL_BODIES,  # ScopeOptions = 0
    )
    assert_args("IFeatureManager.InsertMirrorFeature2", args)
    f = fm.InsertMirrorFeature2(*args)
    if f is None:
        raise RuntimeError(
            f"InsertMirrorFeature2 returned None (seed='{seed_name}', "
            f"plane='{plane}'). Selection marks may have been lost."
        )
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
    "sketch_rectangle_on_face": FeatureType(
        name="sketch_rectangle_on_face",
        handler=None,
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
    "fillet_constant_radius": FeatureType(
        name="fillet_constant_radius",
        handler=None,
        # SW auto-names the fillet's driving radius dim D1@<FilletName>
        # (verified empirically: Parameter('D1@Fillet_FromSpike') returns
        # a CDispatch; Parameter('RadiusDim@...') returns None on SW 2024
        # SP1, despite some forum docs suggesting RadiusDim@). Use D1.
        dim_fields={"radius": "D1"},
    ),
    "chamfer_edge": FeatureType(
        name="chamfer_edge",
        handler=None,
        # InsertFeatureChamfer's driving dim auto-name on SW 2024 SP1 is
        # not yet verified. Empirical convention from other modify features
        # suggests D1@<ChamferName> for the primary distance, D2@... for
        # an angle when present. To be confirmed by Spike Q output.
        # Initial guess: distance->D1, angle->D2.
        dim_fields={"distance": "D1", "angle": "D2"},
    ),
    "linear_pattern": FeatureType(
        name="linear_pattern",
        handler=None,
        # Pattern dims (spacing) are not currently parametric -- the
        # `spacing` field accepts {rhs} but the binding is not yet
        # wired through because pattern dim naming differs from boss
        # extrudes. Defer parametric pattern spacing to a follow-up.
        dim_fields={},
    ),
    "circular_pattern": FeatureType(
        name="circular_pattern",
        handler=None,
        # Pattern dims (total_angle) are not currently parametric --
        # `total_angle` is a plain number in the spec, no {rhs} object
        # form yet. Same rationale as linear_pattern.
        dim_fields={},
    ),
    "mirror_feature": FeatureType(
        name="mirror_feature",
        handler=None,
        # Mirror has no driving dims of its own.
        dim_fields={},
    ),
}


# Wire handlers into the registry (done at module-load time, after all
# handler functions are defined above).
def _wire_handlers() -> None:
    handlers = {
        "sketch_rectangle_on_plane": _build_sketch_rectangle_on_plane,
        "sketch_rectangle_on_face": _build_sketch_rectangle_on_face,
        "sketch_circle_on_plane": _build_sketch_circle_on_plane,
        "sketch_circle_on_face": _build_sketch_circle_on_face,
        "sketch_circles_on_face": _build_sketch_circles_on_face,
        "boss_extrude_blind": _build_boss_extrude_blind,
        "cut_extrude_through_all": _build_cut_extrude_through_all,
        "cut_extrude_blind": _build_cut_extrude_blind,
        "fillet_constant_radius": _build_fillet_constant_radius,
        "chamfer_edge": _build_chamfer_edge,
        "linear_pattern": _build_linear_pattern,
        "circular_pattern": _build_circular_pattern,
        "mirror_feature": _build_mirror_feature,
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

    dim: str  # e.g. "D1@SK_Body"
    rhs: str  # the RHS pasted into Add2 (verbatim from spec)
    add2_index: int  # value returned by EquationMgr.Add2; -1 = silent failure


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
                raise RuntimeError(f"doc.SaveAs3 returned False for {out_path}")
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
