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

from dataclasses import dataclass, field
from typing import Any

from ..sw_com import get_sw_app


# SW enum values used here. Constants kept local to the builder so changes
# to SW versions don't ripple into other modules.
SW_END_COND_BLIND = 0
SW_END_COND_THROUGH_ALL = 4
SW_FEATURE_BODY_OP_CUT = 2  # used by FeatureCut4 (not used in v1; we use FeatureExtrusion2 with bodyOperation arg implicit)
SW_START_SKETCH_PLANE = 0
# swUserPreferenceToggle.swInputDimValOnCreate -- when True, AddDimension2 pops
# a "Modify Dimension" dialog and blocks waiting for user input. We toggle it
# False at build start and restore at end. Confirmed in Spike D.
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


@dataclass
class BuiltFeature:
    name: str
    type: str
    sw_object: Any = None  # the IFeature CDispatch
    # For extrusions, we record the building frame so child sketches can
    # locate faces by relative direction.
    extrude_axis: tuple[float, float, float] | None = None  # outward normal
    extrude_origin: tuple[float, float, float] | None = None  # base face center, part coords
    extrude_depth_m: float | None = None
    extrude_flip: bool = False


@dataclass
class BuildContext:
    """Per-build state. Holds the SW app/doc handle and feature lookup."""
    sw: Any
    doc: Any
    features_by_name: dict[str, BuiltFeature] = field(default_factory=dict)
    rebuild_count: int = 0


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
    width_m = _literal_or_default(feat["width"], 10.0)
    height_m = _literal_or_default(feat["height"], 10.0)
    center = feat.get("center", {})
    cx_m = float(center.get("x", 0.0)) / 1000.0
    cy_m = float(center.get("y", 0.0)) / 1000.0

    sm.CreateCornerRectangle(
        cx_m - width_m / 2, cy_m - height_m / 2, 0.0,
        cx_m + width_m / 2, cy_m + height_m / 2, 0.0,
    )

    # Add driving dimensions so Add2 has D1/D2 to bind to. Selection order
    # determines dim numbering: top edge first -> D1 = width, left edge second
    # -> D2 = height (matches DIM_FIELD_MAP).
    # AddDimension2 places the dim leader at the given coord; we offset
    # outside the rectangle so the leader doesn't overlap entities.
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

    diameter_m = _literal_or_default(feat["diameter"], 10.0)
    radius_m = diameter_m / 2
    center = feat.get("center", {})
    cx_m = float(center.get("x", 0.0)) / 1000.0
    cy_m = float(center.get("y", 0.0)) / 1000.0

    # CreateCircle(xc, yc, zc, xp, yp, zp) - perimeter point at (cx+r, cy, 0)
    sm.CreateCircle(cx_m, cy_m, 0.0, cx_m + radius_m, cy_m, 0.0)

    # Add a diameter dim. Select the circle by clicking on its perimeter,
    # then place the dim leader outside the circle.
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

    ox, oy, oz = parent.extrude_origin
    ax, ay, az = parent.extrude_axis
    depth = parent.extrude_depth_m
    # If extrude was flipped, the outboard face is at -axis*depth
    if parent.extrude_flip:
        ax, ay, az = -ax, -ay, -az
    if face == "+z":
        fx = ox + ax * depth
        fy = oy + ay * depth
        fz = oz + az * depth
    else:  # -z
        fx, fy, fz = ox, oy, oz

    ctx.doc.ClearSelection2(True)
    ok = ctx.doc.SelectByID("", "FACE", fx, fy, fz)
    if not ok:
        raise RuntimeError(
            f"SelectByID returned False at ({fx}, {fy}, {fz}) - face not at expected coord"
        )

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    diameter_m = _literal_or_default(feat["diameter"], 6.0)
    radius_m = diameter_m / 2
    # In a face-based sketch, the sketch origin is at the face center by default.
    # 'center' offset is in sketch-local u/v (mm).
    c = feat.get("center", {})
    u_m = float(c.get("u", 0.0)) / 1000.0
    v_m = float(c.get("v", 0.0)) / 1000.0

    sm.CreateCircle(u_m, v_m, 0.0, u_m + radius_m, v_m, 0.0)

    # Add diameter dim
    ctx.doc.ClearSelection2(True)
    if not ctx.doc.SelectByID("", "SKETCHSEGMENT", u_m + radius_m, v_m, 0.0):
        raise RuntimeError("could not select face-sketch circle for diameter dim")
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

    ox, oy, oz = parent.extrude_origin
    ax, ay, az = parent.extrude_axis
    depth = parent.extrude_depth_m
    if parent.extrude_flip:
        ax, ay, az = -ax, -ay, -az
    if face == "+z":
        fx = ox + ax * depth
        fy = oy + ay * depth
        fz = oz + az * depth
    else:  # -z
        fx, fy, fz = ox, oy, oz

    ctx.doc.ClearSelection2(True)
    if not ctx.doc.SelectByID("", "FACE", fx, fy, fz):
        raise RuntimeError(f"face select returned False at ({fx}, {fy}, {fz})")

    sm = ctx.doc.SketchManager
    sm.InsertSketch(True)

    for k, c in enumerate(feat["circles"]):
        u_m = float(c["u"]) / 1000.0
        v_m = float(c["v"]) / 1000.0
        diameter_m = _literal_or_default(c["diameter"], 4.0)
        radius_m = diameter_m / 2
        sm.CreateCircle(u_m, v_m, 0.0, u_m + radius_m, v_m, 0.0)
        # Dimension this circle BEFORE creating the next one, so dim
        # numbering matches array index: first circle -> D1, second -> D2.
        ctx.doc.ClearSelection2(True)
        if not ctx.doc.SelectByID("", "SKETCHSEGMENT", u_m + radius_m, v_m, 0.0):
            raise RuntimeError(f"could not select circle #{k} for diameter dim")
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
    """Common wrapper around FeatureManager.FeatureExtrusion2.

    Used by all three extrude variants (boss blind, cut through-all, cut blind).
    The bodyOperation (boss vs cut) is determined by whether there's an existing
    body intersected by the sketch + the Merge flag. For v1, FeatureExtrusion2
    naturally produces a boss on the first extrude and a cut when the sketch
    overlaps the existing solid -- SW's auto-detection handles it.

    Actually no: FeatureExtrusion2 is BOSS-ONLY. For cuts we must use
    FeatureCut4. Will refactor if v1 hits this.
    """
    fm = ctx.doc.FeatureManager
    try:
        feature = fm.FeatureExtrusion2(
            True,           # Sd (single direction)
            flip,           # Flip
            False,          # Dir (use sketch normal)
            end_cond,       # T1
            0,              # T2
            depth_m,        # D1
            0.0,            # D2
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True,           # Merge
            True,           # UseFeatScope
            True,           # UseAutoSelect
            SW_START_SKETCH_PLANE,
            0.0,
            False,
        )
    except Exception:
        # Try 22-arg fallback (some SW builds)
        feature = fm.FeatureExtrusion2(
            True, flip, False,
            end_cond, 0,
            depth_m, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            SW_START_SKETCH_PLANE,
            0.0,
        )
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

    SW 2024 signature (24 args):
      Sd, Flip, Dir, T1, T2, D1, D2,
      Dchk1, Dchk2, Ddir1, Ddir2,
      Dang1, Dang2,
      OffsetReverse1, OffsetReverse2,
      TranslateSurface1, TranslateSurface2,
      NormalCut,
      UseFeatScope, UseAutoSelect, AssemblyFeatureScope,
      T0, StartOffset, FlipStartOffset
    """
    fm = ctx.doc.FeatureManager
    feature = fm.FeatureCut4(
        True,           # 1  Sd
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
        False,          # 18 NormalCut
        True,           # 19 UseFeatScope
        True,           # 20 UseAutoSelect
        True,           # 21 AssemblyFeatureScope
        SW_START_SKETCH_PLANE,  # 22 T0
        0.0,            # 23 StartOffset
        False,          # 24 FlipStartOffset
    )
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
    depth_m = _literal_or_default(feat["depth"], 5.0)
    flip = bool(feat.get("flip", False))

    f = _call_feature_extrusion(ctx, end_cond=SW_END_COND_BLIND, depth_m=depth_m, flip=flip)
    f.Name = feat["name"]

    # Carry forward the parent sketch's plane normal so child sketches on
    # the resulting faces can compute their coords. The sketch's plane normal
    # was stashed in extrude_axis by build() before this handler ran.
    if sketch.extrude_axis is None:
        raise RuntimeError(
            f"sketch '{sketch_name}' has no plane normal stashed; "
            f"build() should set extrude_axis on every plane-based sketch"
        )
    return BuiltFeature(
        name=feat["name"],
        type=feat["type"],
        sw_object=f,
        extrude_axis=sketch.extrude_axis,
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
    depth_m = _literal_or_default(feat["depth"], 5.0)
    flip = bool(feat.get("flip", False))
    f = _call_feature_cut(ctx, end_cond=SW_END_COND_BLIND, depth_m=depth_m, flip=flip)
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


# -----------------------------------------------------------------------------
# Dim binding
# -----------------------------------------------------------------------------


# Map feature_type -> dict of {spec_field: dim_suffix}. Used to translate
# "field 'width' of sketch SK_Plate" into "D1@SK_Plate" for the Add2 binding.
DIM_FIELD_MAP: dict[str, dict[str, str]] = {
    # SW auto-numbers dims D1, D2, ... in the order they are added.
    # CreateCornerRectangle does NOT add dims - the rectangle is unconstrained.
    # We must add dimensions via AddDimension2 to get D1 (width) and D2 (height).
    # In v1, the builder calls AddDimension2 right after creating the rectangle,
    # so the first dim is width = D1, second is height = D2.
    "sketch_rectangle_on_plane": {"width": "D1", "height": "D2"},
    # Circles: CreateCircle creates the entity; we add a diameter dim = D1.
    "sketch_circle_on_plane": {"diameter": "D1"},
    "sketch_circle_on_face":  {"diameter": "D1"},
    # Extrusions: depth dim is D1 by default on FeatureExtrusion2.
    "boss_extrude_blind": {"depth": "D1"},
    "cut_extrude_blind":  {"depth": "D1"},
    # through-all cuts have no depth dim
}


def _collect_bindings(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """Walk features and produce (dim_name, rhs) tuples for every {rhs} length.

    dim_name is "D<n>@<feature_name>". rhs is the raw expression from the spec.
    For multi-circle sketches, each circle's diameter -> D{k+1}@<name> in
    spec-array order (matching the builder's dim-numbering convention).
    """
    out: list[tuple[str, str]] = []
    for feat in spec["features"]:
        if feat["type"] == "sketch_circles_on_face":
            for k, c in enumerate(feat["circles"]):
                value = c.get("diameter")
                if _is_rhs(value):
                    dim_name = f"D{k+1}@{feat['name']}"
                    out.append((dim_name, value["rhs"]))
            continue
        field_map = DIM_FIELD_MAP.get(feat["type"], {})
        for field, dim_suffix in field_map.items():
            value = feat.get(field)
            if _is_rhs(value):
                dim_name = f"{dim_suffix}@{feat['name']}"
                out.append((dim_name, value["rhs"]))
    return out


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


# Dispatch table. Each handler takes (ctx, feat_dict) and returns BuiltFeature.
HANDLERS = {
    "sketch_rectangle_on_plane": _build_sketch_rectangle_on_plane,
    "sketch_circle_on_plane":    _build_sketch_circle_on_plane,
    "sketch_circle_on_face":     _build_sketch_circle_on_face,
    "sketch_circles_on_face":    _build_sketch_circles_on_face,
    "boss_extrude_blind":        _build_boss_extrude_blind,
    "cut_extrude_through_all":   _build_cut_extrude_through_all,
    "cut_extrude_blind":         _build_cut_extrude_blind,
}


@dataclass
class BuildResult:
    ok: bool
    features_built: list[str]
    bindings_added: list[tuple[str, str, int]]  # (dim, rhs, add2_idx)
    error: str | None = None
    error_feature: str | None = None


def build(spec: dict[str, Any]) -> BuildResult:
    """Build the spec into a fresh blank part on the running SW session.

    Caller is responsible for validating the spec first via spec.validator.validate.
    """
    sw = get_sw_app()
    doc = create_blank_part(sw)
    ctx = BuildContext(sw=sw, doc=doc)

    # Suppress the "Modify Dimension" popup that AddDimension2 fires by
    # default. App-level only; doc-level call was found to RE-ENABLE the
    # popup on a fresh doc (regression in MMP debug session 2026-05-16).
    prev_input_dim = sw.GetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, False)

    try:
        # Link locals first so dim bindings can resolve var refs
        if spec.get("locals"):
            link_locals(doc, spec["locals"])

        built: list[str] = []
        feat: dict[str, Any] | None = None
        try:
            for feat in spec["features"]:
                handler = HANDLERS[feat["type"]]
                bf = handler(ctx, feat)

                # Stash plane info for sketches so child extrudes can compute the axis.
                if bf.type in ("sketch_rectangle_on_plane", "sketch_circle_on_plane"):
                    normal = PLANE_NORMALS[feat["plane"]]
                    bf.extrude_axis = normal  # repurpose to carry plane normal
                    bf.extrude_origin = (0.0, 0.0, 0.0)
                    bf.extrude_depth_m = 0.0

                ctx.features_by_name[bf.name] = bf
                built.append(bf.name)
        except Exception as e:
            return BuildResult(
                ok=False,
                features_built=built,
                bindings_added=[],
                error=str(e),
                error_feature=feat["name"] if feat is not None else None,
            )

        # All features built; now bind dims
        bindings = _collect_bindings(spec)
        indices = _apply_bindings(doc, bindings)
        binding_results = [(d, r, i) for (d, r), i in zip(bindings, indices)]

        # Final rebuild
        _ = doc.EditRebuild3

        return BuildResult(
            ok=True,
            features_built=built,
            bindings_added=binding_results,
        )
    finally:
        # Always restore the user's preference, even on exception
        sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, prev_input_dim)
