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

import ast
import copy
import logging
import re
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors.wrapper import com_error_boundary, emit_envelope_to_stderr
from ..errors.build_error import BuildError
from ..locals_io import parse as parse_locals
from ..sw_com import get_sw_app
from ..units import SpecUnit, convert_spec_units
from ..com.connection import with_reconnect
from ..telemetry import counter as telemetry_counter
from ..telemetry import histogram as telemetry_histogram
from ..telemetry import new_trace_id, trace_id
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
    SW_THIN_WALL_ONE_DIRECTION,
    assert_args,
)
from ._build_context import (
    BuildContext,
    BuiltFeature,
    DeferredDim,
    FeatureDescriptor,
    FeatureType,
)
from ._face_geometry import (
    PLANE_FULL_NAME,
    _face_frame,
    _select_extrude_face,
    _sketch_uv_to_part,
    _warn_face_sketch_offset,
)
from ._sketch_primitives import (
    PLACEHOLDER_MM,
    _literal_or_default,
)
from ._version_resolver import (
    DEFAULT_KEY,
    SW_2025_MAJOR,
    resolve_op,
    versioned,
)
from .sketches import (
    CircleOnFaceHandler,
    CircleOnPlaneHandler,
    CirclesOnFaceHandler,
    RectangleOnFaceHandler,
    RectangleOnPlaneHandler,
)
from .schema import SKETCH_TYPES

# swUserPreferenceToggle.swInputDimValOnCreate -- the toggle ID is NOT
# documented in the CHM enum (descriptions just say "see System Options").
# Empirically, ID=8 reads back False on this build but does NOT suppress
# the popup. Kept in place because it's harmless and may help on some
# SW builds; see MMP_DEBUG_SESSION.md for the full investigation.
SW_PREF_INPUT_DIM_VAL_ON_CREATE = 8

logger = logging.getLogger("ai_sw_bridge.builder")

# W2.4 — SaveAs3 version mapping (swSaveAsVersion_e).
# SaveAs3's third argument selects the file-format year. 0 means "same
# version as the running SW session." Non-zero values target older format
# versions for back-compat with older seats.
SAVE_FORMAT_VERSIONS: dict[str, int] = {
    "current": 0,
    "2024": 33,
    "2023": 32,
    "2022": 31,
    "2021": 30,
}

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


# Plane name -> outward-normal vector in part coordinates
# (+X right, +Y up, +Z out of screen).
# Matches SW's default English template orientation:
#   Front Plane = XY plane (normal +Z)
#   Top   Plane = XZ plane (normal +Y)
#   Right Plane = YZ plane (normal +X)
PLANE_NORMALS: dict[str, tuple[float, float, float]] = {
    "Front": (0.0, 0.0, 1.0),
    "Top": (0.0, 1.0, 0.0),
    "Right": (1.0, 0.0, 0.0),
}


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


# Allowed AST node operators for the locals arithmetic evaluator. After
# quoted variable refs are substituted with their numeric values, the
# expression is pure arithmetic: numeric literals, + - * /, unary +/-, and
# parentheses. This is the surface LENGTH_SCHEMA's rhs documents.
#
# Why a custom evaluator and not eval(): ROADMAP principle 3 is "zero
# arbitrary code execution -- no eval, no exec." The prior implementation
# called eval() with empty builtins, which is sandboxed and low-risk but
# still eval -- an auditor cannot let "we say no eval" sit next to eval(.
# This evaluator enforces exactly the documented grammar and rejects names,
# calls, attribute access, power, modulo, comparisons, etc.
_ARITH_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ARITH_UNARYOPS = (ast.UAdd, ast.USub)


def _safe_arith_eval(expr: str) -> float:
    """Evaluate a pure-arithmetic expression without ``eval``.

    Supports numeric literals, ``+ - * /``, unary ``+``/``-``, and
    parentheses -- the exact surface the locals rhs grammar allows once
    quoted variable references have been substituted to numbers. Raises
    ``ValueError`` on any construct outside that grammar.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid arithmetic expression {expr!r}: {exc}") from exc

    def _ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ARITH_BINOPS):
            left, right = _ev(node.left), _ev(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            return left / right  # ast.Div
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ARITH_UNARYOPS):
            operand = _ev(node.operand)
            return +operand if isinstance(node.op, ast.UAdd) else -operand
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            return float(node.value)
        raise ValueError(
            f"disallowed element in arithmetic expression {expr!r}: "
            f"{type(node).__name__}; only numeric literals, + - * /, "
            f"unary +/-, and parentheses are permitted"
        )

    return float(_ev(tree))


def _eval_rhs(rhs: str, lookup: Any) -> float:
    """Evaluate an rhs expression like '"PART_DIAMETER"' or '"FOO" + 0.5'.

    Quoted variable refs are substituted with their numeric value via the
    `lookup` callable (which takes a name and returns a float, recursing as
    needed). The remainder is evaluated by `_safe_arith_eval` -- NOT eval --
    so only +, -, *, /, unary +/-, parens, and numeric literals are usable.
    """

    def _sub(m: "re.Match[str]") -> str:
        return repr(lookup(m.group(1)))

    arith_expr = re.sub(r'"([^"]+)"', _sub, rhs)
    return _safe_arith_eval(arith_expr)


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


# -----------------------------------------------------------------------------
# FeatureCut4 -- version-dispatched arg-builders (FR-X-04)
# -----------------------------------------------------------------------------
#
# FeatureCut4 is the reference call wrapped through the version resolver. The
# 2024 (default) variant produces the EXACT 27-arg tuple the call site has
# always used -- behaviour-preserving on the only proven build. The 2025
# variant is a 🔴 SEAT stub: the reference codebase branches on RevisionNumber
# == 33 (SW 2025) because FeatureCut4's arity changed there, but we have no
# 2025 seat to verify the new signature, so it is registered (so the dispatch
# wiring is real and testable) but NEVER exercised on 2024.


@versioned("FeatureCut4", DEFAULT_KEY)
def _cut4_args_2024(
    *,
    end_cond: int,
    depth_m: float,
    flip: bool,
    end_cond2: int | None = None,
    depth2_m: float = 0.0,
) -> tuple:
    """SW 2024 SP1 FeatureCut4 arg tuple (27 args; default/proven variant).

    SW 2017+ signature (verified via decompiled sldworksapi.chm and Spike E7
    on SW 2024 SP1):
      Sd, Flip, Dir, T1, T2, D1, D2,
      Dchk1, Dchk2, Ddir1, Ddir2,
      Dang1, Dang2,
      OffsetReverse1, OffsetReverse2,
      TranslateSurface1, TranslateSurface2,
      NormalCut,
      UseFeatScope, UseAutoSelect, AssemblyFeatureScope,
      AutoSelectComponents, PropagateFeatureToParts,
      T0, StartOffset, FlipStartOffset, OptimizeGeometry

    ``end_cond2`` opts into a second (reverse) direction: when given, ``Sd``
    (single-ended) flips False and ``T2``/``D2`` carry the second direction's
    end-condition/depth. When ``None`` (the default) the tuple is byte-for-byte
    the single-direction shape the call site has always produced.
    """
    single_dir = end_cond2 is None
    return (
        single_dir,  # 1  Sd (single-ended unless a 2nd direction is requested)
        flip,  # 2  Flip
        False,  # 3  Dir
        end_cond,  # 4  T1
        0 if single_dir else end_cond2,  # 5  T2
        depth_m,  # 6  D1
        0.0 if single_dir else depth2_m,  # 7  D2
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


@versioned("FeatureCut4", SW_2025_MAJOR)
def _cut4_args_2025(
    *,
    end_cond: int,
    depth_m: float,
    flip: bool,
    end_cond2: int | None = None,
    depth2_m: float = 0.0,
) -> tuple:
    """🔴 SEAT (SW 2025 / RevisionNumber major 33) -- UNVERIFIED.

    The reference codebase branches on RevisionNumber == 33 because
    FeatureCut4's arity changed in SW 2025. This stub exists so the
    version-dispatch wiring is real and unit-testable, but the actual 2025
    signature has NOT been confirmed against a 2025 seat. It is currently a
    1:1 copy of the 2024 tuple as a placeholder. DO NOT treat as working.

    🔴 SEAT follow-up: obtain a SW 2025 seat, confirm the FeatureCut4 arg
    count/order (and update sw_types.METHOD_SIGNATURES if it differs), then
    replace this body with the verified 2025 tuple and re-GREEN against a
    real cut on 2025.
    """
    return _cut4_args_2024(
        end_cond=end_cond, depth_m=depth_m, flip=flip,
        end_cond2=end_cond2, depth2_m=depth2_m,
    )


def _call_feature_cut(
    ctx: BuildContext,
    *,
    end_cond: int,
    depth_m: float,
    flip: bool,
    end_cond2: int | None = None,
    depth2_m: float = 0.0,
) -> Any:
    """FeatureManager.FeatureCut4 - the cut variant of FeatureExtrusion2.

    Routed through the version-dispatch resolver (FR-X-04): the running SW
    major revision (read once, late-bound, from ``ctx.sw.RevisionNumber``)
    selects the arg-builder via newest->older cascade. On SW 2024 (the only
    proven build) this resolves to ``_cut4_args_2024`` and the produced 27-arg
    tuple is identical to the pre-resolver call -- behaviour-preserving. The
    2025 variant is a 🔴 SEAT stub that is never reached on 2024.

    ``end_cond2``/``depth2_m`` add an optional second (reverse) cut direction
    (two-direction cuts); omitted, the call is single-direction as before.
    """
    arg_builder = resolve_op("FeatureCut4", sw=ctx.sw)
    args = arg_builder(
        end_cond=end_cond, depth_m=depth_m, flip=flip,
        end_cond2=end_cond2, depth2_m=depth2_m,
    )
    assert_args("IFeatureManager.FeatureCut4", args)
    fm = ctx.doc.FeatureManager
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
    #
    # NOTE on `center.z`: v0.8 added optional `center.z` for Top Plane
    # rectangle/circle sketches (DriveRoller O-ring groove). When set, the
    # `cz` component carries an explicit part-frame Z that does not pass
    # through the sketch-local-to-part-frame remap below -- callers that
    # extrude a Top Plane sketch with non-zero `center.z` will currently
    # see extrude_origin's part-Z come from the sketch-local-Y remap, not
    # from `center.z`. Only `revolve_cut`/`revolve_boss` are exercised on
    # such sketches today, and those don't consume `extrude_origin`. If a
    # future spec extrudes a Top Plane sketch with non-zero `center.z`,
    # this remap needs revisiting.
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


def _build_cut_extrude_midplane(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Mid-plane cut: removes ``depth`` of material centred on the sketch plane
    (``depth/2`` each side). One arg-shape change vs blind -- T1 = mid-plane.
    Like the other cuts it emits a bare BuiltFeature (no extrude_origin/axis
    metadata; cuts don't feed the downstream face-geometry derivation)."""
    sketch_name = feat["sketch"]
    _select_sketch(ctx, sketch_name)
    depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["cut_depth"])
    flip = bool(feat.get("flip", False))
    f = _call_feature_cut(ctx, end_cond=SW_END_COND_MID_PLANE, depth_m=depth_m, flip=flip)
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _build_cut_extrude_two_direction(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Two-direction blind cut: ``depth`` into +normal AND ``depth2`` into
    -normal from the sketch plane. Drives FeatureCut4 with ``Sd=False`` and
    independent T1/D1, T2/D2 (both blind). Bare BuiltFeature like the other
    cuts."""
    sketch_name = feat["sketch"]
    _select_sketch(ctx, sketch_name)
    depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["cut_depth"])
    depth2_m = _literal_or_default(feat["depth2"], PLACEHOLDER_MM["cut_depth"])
    flip = bool(feat.get("flip", False))
    f = _call_feature_cut(
        ctx, end_cond=SW_END_COND_BLIND, depth_m=depth_m, flip=flip,
        end_cond2=SW_END_COND_BLIND, depth2_m=depth2_m,
    )
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _build_revolve_boss(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Revolve the named profile sketch about its embedded centerline.

    The profile sketch must have been built via a plane-based sketch handler
    with a `centerline` field (drawn as construction line inside the sketch).
    SW auto-picks that centerline as the axis of revolution when the sketch
    alone is selected -- matches the native Insert > Revolved Boss workflow
    and verified GREEN in Spike X (2026-05-19).

    20-arg FeatureRevolve2 signature is CHM-verified; no parametric angle
    binding in v1 (angle is a literal degrees number in the spec)."""
    return _call_feature_revolve(ctx, feat, is_cut=False)


def _build_revolve_cut(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Revolve-cut: subtractive sibling of revolve_boss.

    Same centerline-in-sketch axis pattern. The profile must, on revolution,
    intersect existing body material -- if it sweeps through empty space,
    FeatureRevolve2 silently returns None (the handler surfaces this with a
    diagnostic that points the human at the most common cause).

    The first attempt at this primitive on 2026-05-21 produced 8 spikes of
    silent-None failures (ZG-ZN) before Spike ZP/ZQ traced the root cause to
    a Right Plane sketch-coordinate-mapping bug in the spike harness, not a
    bridge or pywin32 issue. The actual handler is structurally identical to
    revolve_boss with one bit flipped (IsCut=True at FeatureRevolve2 arg 4)."""
    return _call_feature_revolve(ctx, feat, is_cut=True)


def _call_feature_revolve(
    ctx: BuildContext, feat: dict[str, Any], *, is_cut: bool
) -> BuiltFeature:
    """Shared implementation for revolve_boss / revolve_cut."""
    import math

    sketch_name = feat["sketch"]
    _select_sketch(ctx, sketch_name)

    angle_deg = float(feat.get("angle", 360.0))
    angle_rad = math.radians(angle_deg)
    flip = bool(feat.get("flip", False))

    args = (
        True,  # 1  SingleDir
        True,  # 2  IsSolid
        False,  # 3  IsThin
        is_cut,  # 4  IsCut (False=boss, True=cut)
        flip,  # 5  ReverseDir
        False,  # 6  BothDirectionUpToSameEntity
        SW_END_COND_BLIND,  # 7  Dir1Type (blind = explicit angle)
        0,  # 8  Dir2Type (ignored)
        angle_rad,  # 9  Dir1Angle (radians)
        0.0,  # 10 Dir2Angle
        False,  # 11 OffsetReverse1
        False,  # 12 OffsetReverse2
        0.0,  # 13 OffsetDistance1
        0.0,  # 14 OffsetDistance2
        SW_THIN_WALL_ONE_DIRECTION,  # 15 ThinType (ignored when IsThin=False)
        0.0,  # 16 ThinThickness1
        0.0,  # 17 ThinThickness2
        True,  # 18 Merge
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
    )
    assert_args("IFeatureManager.FeatureRevolve2", args)
    f = ctx.doc.FeatureManager.FeatureRevolve2(*args)
    if f is None:
        if is_cut:
            raise RuntimeError(
                f"FeatureRevolve2(IsCut=True) returned None for "
                f"'{feat['name']}'. Most common cause: the swept profile "
                f"doesn't intersect any existing body material -- SW "
                f"silently produces no geometry rather than erroring. "
                f"Other causes: profile sketch contains no centerline, "
                f"profile not closed, profile crosses the centerline, "
                f"or sketch coords land in empty space due to a "
                f"plane-axis mapping bug in the spec."
            )
        raise RuntimeError(
            f"FeatureRevolve2 returned None for '{feat['name']}'. "
            f"Common causes: profile sketch contains no centerline, "
            f"profile not closed, or profile crosses the centerline."
        )
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)


def _build_simple_hole(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Drill a straight-bore hole through an existing face.

    No sketch needed -- the (u, v) center positions the hole on the face,
    and the hole is automatically normal to that face. Uses
    IFeatureManager.SimpleHole2 (23 args, SW 2017+). Selection state on
    entry: just the FACE, selected at the desired hole-center point
    (SimpleHole2 uses the SelectByID hit point as the hole center).

    Pre-fix attempt (Spike W) tried also pre-selecting a SKETCHPOINT but
    SimpleHole2 returned None. The simpler "face only, picked at the
    hole center" approach works and matches what the SW UI does
    internally.
    """
    parent_name = feat["of_feature"]
    parent = ctx.features_by_name.get(parent_name)
    if parent is None:
        raise RuntimeError(f"simple_hole: '{parent_name}' not built yet")
    if parent.extrude_axis is None:
        raise RuntimeError(f"'{parent_name}' is not an extrusion with known axis")

    face = feat["face"]
    _warn_face_sketch_offset(parent, face, feat, ("u", "v"))
    _frame = _face_frame(parent, face)

    # Compute the hole's intended (u, v) in sketch coords, then transform
    # to part-frame for SelectByID. We want the face-select to hit at the
    # hole center (not just somewhere on the face) because SimpleHole2
    # uses the pick point as the hole position.
    c = feat.get("center", {})
    u_m = float(c.get("u", 0.0)) / 1000.0
    v_m = float(c.get("v", 0.0)) / 1000.0
    px, py, pz = _sketch_uv_to_part(_frame, u_m, v_m)

    ctx.doc.ClearSelection2(True)
    ok = ctx.doc.SelectByID("", "FACE", px, py, pz)
    if not ok:
        # Fall back to the same normal-verified spiral _select_extrude_face
        # uses, then re-pick exactly at the hole center via the body face.
        # Most parts only need the direct pick.
        ok2, _, _, _ = _select_extrude_face(ctx, parent, face)
        if not ok2:
            raise RuntimeError(
                f"simple_hole '{feat['name']}': could not select {face} face "
                f"of '{parent_name}' at hole center "
                f"({px*1000:.2f}, {py*1000:.2f}, {pz*1000:.2f}) mm"
            )
        # _select_extrude_face leaves a face selected, but possibly at the
        # face center (not the hole center). Re-pick at the hole center
        # since SimpleHole2 needs the position.
        ctx.doc.ClearSelection2(True)
        if not ctx.doc.SelectByID("", "FACE", px, py, pz):
            raise RuntimeError(
                f"simple_hole '{feat['name']}': SelectByID('','FACE',...) "
                f"at hole center failed even after _select_extrude_face "
                f"confirmed face existence"
            )

    # Verify the selected face has the expected normal -- guards against
    # the same multi-boss face-pick gotcha _select_extrude_face guards.
    face_obj = ctx.doc.SelectionManager.GetSelectedObject6(1, -1)
    try:
        n = face_obj.Normal
        nx_e, ny_e, nz_e = _frame.out_normal
        if not (
            abs(n[0] - nx_e) < 0.1 and abs(n[1] - ny_e) < 0.1 and abs(n[2] - nz_e) < 0.1
        ):
            raise RuntimeError(
                f"simple_hole '{feat['name']}': SelectByID picked a face with "
                f"normal ({n[0]:+.2f},{n[1]:+.2f},{n[2]:+.2f}) but expected "
                f"({nx_e:+.2f},{ny_e:+.2f},{nz_e:+.2f}) for {face} face"
            )
    except AttributeError:
        # If the selected object doesn't have .Normal we can't verify;
        # let SimpleHole2 fail naturally if the wrong thing is selected.
        pass

    diameter_m = _literal_or_default(feat["diameter"], PLACEHOLDER_MM["hole_diameter"])
    end_condition = feat.get("end_condition", "blind")
    if end_condition == "blind":
        depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["hole_depth"])
        end_cond = SW_END_COND_BLIND
    else:  # through_all
        depth_m = 0.0
        end_cond = SW_END_COND_THROUGH_ALL

    fm = ctx.doc.FeatureManager
    args = (
        diameter_m,  # 1  Dia
        True,  # 2  Sd
        False,  # 3  Flip
        False,  # 4  Dir
        end_cond,  # 5  T1
        0,  # 6  T2
        depth_m,  # 7  D1
        0.0,  # 8  D2
        False,  # 9  Dchk1
        False,  # 10 Dchk2
        False,  # 11 Ddir1
        False,  # 12 Ddir2
        0.0,  # 13 Dang1
        0.0,  # 14 Dang2
        False,  # 15 OffsetReverse1
        False,  # 16 OffsetReverse2
        False,  # 17 TranslateSurface1
        False,  # 18 TranslateSurface2
        True,  # 19 UseFeatScope
        True,  # 20 UseAutoSelect
        False,  # 21 AssemblyFeatureScope
        False,  # 22 AutoSelectComponents
        False,  # 23 PropagateFeatureToParts
    )
    assert_args("IFeatureManager.SimpleHole2", args)
    f = fm.SimpleHole2(*args)
    if f is None:
        raise RuntimeError(
            f"simple_hole '{feat['name']}': SimpleHole2 returned None "
            f"(face={face}, hole-center=({px*1000:.2f},{py*1000:.2f},"
            f"{pz*1000:.2f})mm, dia={diameter_m*1000:.2f}mm)"
        )
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


# ---------------------------------------------------------------------------
# P1.7s — sketch primitive handlers (function-style, no_dim literal geometry).
#
# Seat-validated 2026-05-31 on SW 2024 (rev 32.1.0) by
# spikes/v0_16/spike_sketch_primitives.py (+ spike_slot_v2.py for the
# CreateSketchSlot 14-scalar signature). Each handler runs the literal-size
# life-cycle: select reference plane -> InsertSketch -> call the proven
# ISketchManager.Create* (or IModelDoc2.InsertSketchText) -> close sketch ->
# rename the new sketch feature -> return BuiltFeature. Coordinates are
# interpreted SKETCH-LOCAL 2D (the spec gives 2D x/y on a named plane), so no
# part-frame projection is applied (unlike circle_on_plane, whose `center` is
# part-frame). Parametric ({rhs}) dimensioning is deferred to a later pass;
# {rhs} fields resolve to literal numbers before any handler runs in no_dim.
#
# Proven live signatures (all confirmed materialising a segment on the seat):
#   line     sm.CreateLine(x1,y1,z1, x2,y2,z2)
#   arc      sm.CreateArc(cx,cy,cz, sx,sy,sz, ex,ey,ez, direction)  dir +1 ccw / -1 cw
#   ellipse  sm.CreateEllipse(cx,cy,cz, majX,majY,majZ, minX,minY,minZ)
#   polygon  sm.CreatePolygon(cx,cy,cz, px,py,pz, sides:int, inscribed:bool)
#   spline   sm.CreateSpline2(VARIANT(VT_ARRAY|VT_R8)[flat x,y,z triples], False)
#   slot     sm.CreateSketchSlot(ct:int, lt:int, width, x1,y1,z1, x2,y2,z2,
#                                x3,y3,z3, addDim:bool, centerline:bool)
#   text     doc.InsertSketchText(x,y,z, content, alignment:int, flip:int,
#                                hmirror:int, widthFactor:int, spaceChars:int)
#            then height/font via ISketchText.GetTextFormat -> SetTextFormat(0,tf)
#
# Full-fidelity flags (P1.7-fidelity): `construction` marks the created
# segment(s) via ISketchSegment.ConstructionGeometry (line/arc/spline/polygon/
# ellipse — seat-proven). Unsupported-on-seat requests are rejected loudly, not
# faked: spline `closed`, slot `construction`, text `construction`/`angle_deg`.
# ---------------------------------------------------------------------------


def _mm_to_m(value: Any) -> float:
    """Convert a LENGTH_SCHEMA field (mm literal or `{rhs}` dict) to metres.

    For `{rhs}` bindings the live handler substitutes the resolved numeric
    value; here we just return a placeholder so the arg tuple has the right
    shape for the seat pass to verify.
    """
    if isinstance(value, dict):
        return 0.0  # placeholder; live path resolves via EquationMgr
    return float(value) / 1000.0


def _r8_safearray(values: list[float]) -> Any:
    """Wrap a flat list of doubles as a ``VT_ARRAY|VT_R8`` VARIANT SAFEARRAY.

    The point buffer shape ``ISketchManager.CreateSpline2`` requires. The
    pywin32 import is function-local so this module stays importable (and
    unit-testable) without SOLIDWORKS / pywin32 present — tests monkeypatch
    this seam. Seat-proven 2026-05-31 (spline materialised first try).
    """
    import pythoncom
    from win32com.client import VARIANT

    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(values))


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

    Seat-proven on line/arc/spline/polygon/ellipse — every returned segment
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
        _mm_to_m(start["x"]), _mm_to_m(start["y"]), 0.0,
        _mm_to_m(end["x"]), _mm_to_m(end["y"]), 0.0,
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
        _mm_to_m(c["x"]), _mm_to_m(c["y"]), 0.0,
        _mm_to_m(s["x"]), _mm_to_m(s["y"]), 0.0,
        _mm_to_m(e["x"]), _mm_to_m(e["y"]), 0.0,
        direction,
    )
    _apply_construction(seg, feat)
    return _close_plane_sketch_and_build(ctx, feat)


def _build_sketch_spline(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    """Sketch a spline through a sequence of control points.

    Seat-proven: ``ISketchManager.CreateSpline2(pointBuffer, b3D=False)`` where
    ``pointBuffer`` is a ``VT_ARRAY|VT_R8`` SAFEARRAY of flat ``x,y,z`` triples
    (z=0 on a plane). Open splines only — a point-based periodic (C2) closed
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
    centerline:bool)`` — 14 scalars (NOT a point SAFEARRAY). ``creationType``/
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
        0, 0, width,
        x1, y1, 0.0,
        x2, y2, 0.0,
        x3, y3, 0.0,
        False, True,
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

    Seat-proven: text is a document-level op — ``IModelDoc2.InsertSketchText(
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
        _mm_to_m(pos["x"]), _mm_to_m(pos["y"]), 0.0,
        str(feat["content"]),
        0, 0, 0, 1, 1,
    )
    _apply_text_format(raw_text, feat)
    return _close_plane_sketch_and_build(ctx, feat)


# THE registry of feature descriptors (X3, FR-X-03): the single source of
# truth per primitive. To add a new feature type, append one descriptor here
# and a handler function; its JSON-Schema fragment is assembled from the
# descriptor's `fields` (no separate hand-written dict in `schema.py`).
DESCRIPTORS: dict[str, FeatureDescriptor] = {
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
    "cut_extrude_midplane": FeatureType(
        name="cut_extrude_midplane",
        handler=None,
        dim_fields={"depth": "D1"},
    ),
    "cut_extrude_two_direction": FeatureType(
        name="cut_extrude_two_direction",
        handler=None,
        dim_fields={"depth": "D1", "depth2": "D2"},
    ),
    "revolve_boss": FeatureType(
        name="revolve_boss",
        handler=None,
        # `angle` is a plain number in the spec (degrees), not a length;
        # no {rhs} object form yet. Parametric angle is a v1.1 candidate
        # (would need an angle-type LENGTH_SCHEMA variant).
        dim_fields={},
    ),
    "revolve_cut": FeatureType(
        name="revolve_cut",
        handler=None,
        # Same as revolve_boss -- no parametric angle in v1.
        dim_fields={},
    ),
    "simple_hole": FeatureType(
        name="simple_hole",
        handler=None,
        # SimpleHole2 emits TWO underlying SW objects:
        #   - the Hole feature itself, whose only driving dim is
        #     `D1@<HoleName>` = depth (and only when end_condition='blind';
        #     through_all holes have no depth dim).
        #   - an auto-created child sketch (named Sketch<N> where N is the
        #     next free index in the part) that carries the DIAMETER dim
        #     as `D1@Sketch<N>`. The child sketch's index is unpredictable,
        #     so the diameter can't be parametrically rebound by name in v1.
        # v1 dim-mode therefore binds depth only; diameter is baked in as
        # a literal at build time. Parametric diameter is a v1.1 candidate
        # (would need the handler to rename the child sketch to a
        # deterministic name like `<HoleName>_HoleSketch` and the rhs
        # collector to allow per-field feature-name suffixes).
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
    # ---------------------------------------------------------------------------
    # P1.7s — sketch primitives (stub handlers, flagged 🔴 SEAT for P1.7-seat/W0).
    # `dim_fields` is empty: these are sketch primitives whose dimensions (length,
    # radius, width, height) are plain numbers in the spec, not yet parametric
    # `{rhs}` bindings that Equation Manager would consume. Once the seat pass
    # GREEN-lights the COM signatures, the parametric pathway can be wired per
    # field (same mechanism as sketch_rectangle_on_plane's width/height).
    # ---------------------------------------------------------------------------
    "sketch_line": FeatureType(name="sketch_line", handler=None, dim_fields={}),
    "sketch_arc": FeatureType(name="sketch_arc", handler=None, dim_fields={}),
    "sketch_spline": FeatureType(name="sketch_spline", handler=None, dim_fields={}),
    "sketch_slot": FeatureType(name="sketch_slot", handler=None, dim_fields={}),
    "sketch_polygon": FeatureType(name="sketch_polygon", handler=None, dim_fields={}),
    "sketch_ellipse": FeatureType(name="sketch_ellipse", handler=None, dim_fields={}),
    "sketch_text": FeatureType(name="sketch_text", handler=None, dim_fields={}),
}


# Wire handlers into the registry (done at module-load time, after all
# handler functions are defined above).
def _wire_handlers() -> None:
    handlers = {
        "sketch_rectangle_on_plane": RectangleOnPlaneHandler().build,
        "sketch_rectangle_on_face": RectangleOnFaceHandler().build,
        "sketch_circle_on_plane": CircleOnPlaneHandler().build,
        "sketch_circle_on_face": CircleOnFaceHandler().build,
        "sketch_circles_on_face": CirclesOnFaceHandler().build,
        "boss_extrude_blind": _build_boss_extrude_blind,
        "cut_extrude_through_all": _build_cut_extrude_through_all,
        "cut_extrude_blind": _build_cut_extrude_blind,
        "cut_extrude_midplane": _build_cut_extrude_midplane,
        "cut_extrude_two_direction": _build_cut_extrude_two_direction,
        "revolve_boss": _build_revolve_boss,
        "revolve_cut": _build_revolve_cut,
        "simple_hole": _build_simple_hole,
        "fillet_constant_radius": _build_fillet_constant_radius,
        "chamfer_edge": _build_chamfer_edge,
        "linear_pattern": _build_linear_pattern,
        "circular_pattern": _build_circular_pattern,
        "mirror_feature": _build_mirror_feature,
        # P1.7s — sketch primitives. Stubs that assemble the ISketchManager.Create*
        # arg tuple and raise NotImplementedError; the live COM call is flagged
        # 🔴 SEAT for the P1.7-seat/W0 seat pass.
        "sketch_line": _build_sketch_line,
        "sketch_arc": _build_sketch_arc,
        "sketch_spline": _build_sketch_spline,
        "sketch_slot": _build_sketch_slot,
        "sketch_polygon": _build_sketch_polygon,
        "sketch_ellipse": _build_sketch_ellipse,
        "sketch_text": _build_sketch_text,
    }
    from .descriptors import FEATURE_FIELDS, FEATURE_META

    for name, ft in DESCRIPTORS.items():
        # FeatureDescriptor is mutable; populate it in place (X3). Beyond the
        # handler, attach the declarative `fields` + coverage metadata from the
        # neutral descriptors module so each FeatureDescriptor is the complete
        # single source of truth (schema shape + docs + handler) at runtime.
        ft.handler = handlers[name]
        ft.fields = FEATURE_FIELDS.get(name, [])
        meta = FEATURE_META.get(name, {})
        ft.doc = meta.get("doc")
        ft.example_ref = meta.get("example_ref")
        ft.risk_tier = meta.get("risk_tier")
        ft.sw_min = meta.get("sw_min")
        ft.spike_id = meta.get("spike_id")


_wire_handlers()


def _collect_feature_bindings(feat: dict[str, Any]) -> list[tuple[str, str]]:
    """[(dim_name, rhs)] for one feature. Used for interleaved per-feature
    binding so downstream geometry sees target sizes, not placeholders."""
    ft = DESCRIPTORS.get(feat["type"])
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


# Back-compat aliases. FEATURE_REGISTRY was renamed to DESCRIPTORS in X3; the
# old name stays as an alias so the rename is non-breaking for any importer.
# Legacy code/tests may also import HANDLERS or DIM_FIELD_MAP.
FEATURE_REGISTRY = DESCRIPTORS
HANDLERS = {name: ft.handler for name, ft in DESCRIPTORS.items()}
DIM_FIELD_MAP = {name: ft.dim_fields for name, ft in DESCRIPTORS.items()}


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


def _apply_deferred_dims(
    ctx: BuildContext,
    entries: list[DeferredDim] | None = None,
    *,
    label_prefix: str = "Deferred-dim phase",
) -> None:
    """Replay a batch of deferred AddDimension2 calls, GROUPED by sketch.

    For each sketch_name in the input entries (group order = first-occurrence
    order), run a SINGLE EditSketch session that adds all of that sketch's
    deferred dims back-to-back before closing. This is REQUIRED -- not just
    an optimization. Empirically (Z6, 2026-05-19), closing the sketch and
    re-opening it between dims causes SW to treat the second+ dim as
    DRIVEN (reference) rather than DRIVING. A driven dim cannot be bound
    via EquationMgr.Add2 with a dependent variable. Keeping the sketch
    open across all of its dims preserves them as driving constraints.

    Cadence per sketch group:
      1. SelectByID(sketch_name, "SKETCH", 0,0,0)
      2. doc.EditSketch()  -- re-opens the closed sketch for editing
      3. For each DeferredDim in the group:
           a. ClearSelection2, then SelectByID(select_type, select_xyz)
           b. AddDimension2(*leader_xyz) -- popup fires; user ticks
      4. SketchManager.InsertSketch(True)  -- close sketch

    The Modify-Dimension popup still requires manual user ticking on SW
    2024 SP1 -- this method does NOT automate that. The benefit is that
    popups arrive in a predictable batch.

    `entries` defaults to all of ctx.deferred_dims if not provided. The
    per-sketch-deferred caller in build() passes just the entries that
    were appended by the most recent handler (sliced via a watermark).

    Errors from AddDimension2 (returning None) are recorded but don't abort
    the loop -- subsequent dims still get a chance. A RuntimeError is
    raised at the end if any failed."""
    items = entries if entries is not None else ctx.deferred_dims
    if not items:
        return

    # Group by sketch_name, preserving first-occurrence order. Within each
    # group, dims stay in their original recording order so D1, D2, ...
    # numbering matches the handler's expectations.
    groups: list[tuple[str, list[DeferredDim]]] = []
    group_by_name: dict[str, list[DeferredDim]] = {}
    for dd in items:
        if dd.sketch_name not in group_by_name:
            new_list: list[DeferredDim] = []
            group_by_name[dd.sketch_name] = new_list
            groups.append((dd.sketch_name, new_list))
        group_by_name[dd.sketch_name].append(dd)

    sm = ctx.doc.SketchManager
    failures: list[tuple[str, str]] = []  # (dim_name, reason)

    print(
        f"=== {label_prefix}: {len(items)} dim(s) across "
        f"{len(groups)} sketch(es). Each dim opens a Modify-Dimension popup. ===",
        file=__import__("sys").stderr,
    )

    dim_counter = 0
    for sketch_name, group in groups:
        # Open the sketch ONCE for all of its dims
        ctx.doc.ClearSelection2(True)
        ok_sk = ctx.doc.SelectByID(sketch_name, "SKETCH", 0.0, 0.0, 0.0)
        if not ok_sk:
            for dd in group:
                failures.append(
                    (dd.expected_dim_name, f"could not select sketch '{sketch_name}'")
                )
            continue
        try:
            ctx.doc.EditSketch()
        except Exception as e:
            for dd in group:
                failures.append(
                    (dd.expected_dim_name, f"EditSketch('{sketch_name}') failed: {e!r}")
                )
            continue

        # Add each dim while the sketch is in active edit mode -- this is
        # what keeps them all as driving dims rather than the 2nd+ being
        # demoted to driven.
        for dd in group:
            dim_counter += 1
            print(
                f"  [{dim_counter}/{len(items)}] {dd.field_label} "
                f"({dd.expected_dim_name}) -- tick the popup to continue",
                file=__import__("sys").stderr,
            )
            ctx.doc.ClearSelection2(True)
            sx, sy, sz = dd.select_xyz
            ok_seg = ctx.doc.SelectByID("", dd.select_type, sx, sy, sz)
            if not ok_seg:
                failures.append(
                    (
                        dd.expected_dim_name,
                        f"could not select {dd.select_type} at {dd.select_xyz}",
                    )
                )
                continue

            lx, ly, lz = dd.leader_xyz
            dim = ctx.doc.AddDimension2(lx, ly, lz)
            if dim is None:
                failures.append((dd.expected_dim_name, "AddDimension2 returned None"))

        # Close the sketch only after all of its dims are added
        sm.InsertSketch(True)

    if failures:
        msg = "; ".join(f"{n}: {r}" for n, r in failures)
        raise RuntimeError(f"deferred-dim phase: {len(failures)} dim(s) failed: {msg}")


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------


def _write_brep_sidecar(
    brep_manifest: Any,
    *,
    save_as: str | None,
) -> str | None:
    """Write build_brep.json alongside the saved part (or cwd).

    Returns the sidecar path string on success, ``None`` on write
    failure (the build still succeeds — the brep block rides on
    BuildResult.to_dict() as a fallback).
    """
    import json as _json

    if save_as is not None:
        sidecar = Path(save_as).with_name("build_brep.json")
    else:
        sidecar = Path.cwd() / "build_brep.json"
    try:
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(
            _json.dumps(brep_manifest.to_dict(), indent=2),
            encoding="utf-8",
        )
        return str(sidecar)
    except OSError as e:
        logger.warning("brep sidecar write failed at %s: %s", sidecar, e)
        return None


def _save_as_with_verification(
    doc: Any, out_path: Path, save_version: int = 0
) -> tuple[str, bool]:
    """Drive doc.SaveAs3 and verify three independent postconditions.

    Why this is not a one-liner: SaveAs3 has shipped silent-failure modes
    on this build that the return code alone does NOT catch.

    - 2026-05 DriveRoller session: build reported `ok=True` with a
      `save_as` path, but `doc.GetSaveFlag` was True and the .sldprt was
      absent on disk. A manual `doc.SaveAs3(path, 0, 0)` afterwards did
      persist the file. Root cause: OneDrive sync client held an
      exclusive handle on the parent directory just long enough that
      SW's write was queued but not flushed by the time `out_path.exists`
      was probed. The prior verification (`out_path.exists()` only)
      bounced True for a few ms then went False.

    Three independent checks, each catches a failure mode the others
    miss:
      1. swFileSaveError_e return code (0 == NoError).
      2. doc.GetSaveFlag must be False (= SW thinks the file is clean).
      3. File exists on disk with non-zero size.

    Retry (3 attempts, 200/400/600 ms backoff) absorbs the OneDrive /
    Dropbox post-write handle hold. If all retries fail, raise loudly --
    callers should treat this as a hard error, not a warning.

    Returns (resolved_path_string, True) on verified success. Raises
    RuntimeError otherwise. The bool in the return type leaves room for
    a future "soft-verify" mode that returns False instead of raising;
    today it is always True when the function returns.
    """
    err = doc.SaveAs3(str(out_path), 0, save_version)
    err_code = int(err) if err is not None else 0
    if err_code != 0:
        raise RuntimeError(
            f"doc.SaveAs3({out_path}) returned swFileSaveError={err_code} "
            f"(0 == NoError); file not written"
        )

    dirty: bool = True
    size: int = 0
    for attempt in range(3):
        try:
            dirty = bool(doc.GetSaveFlag)
        except Exception:
            dirty = True
        size = out_path.stat().st_size if out_path.exists() else 0
        if not dirty and size > 0:
            return str(out_path), True
        time.sleep(0.2 * (attempt + 1))

    raise RuntimeError(
        f"doc.SaveAs3({out_path}) returned NoError but postconditions "
        f"unsatisfied after 3 retries: dirty={dirty}, "
        f"exists={out_path.exists()}, size_bytes={size}. "
        f"This commonly indicates a cloud-sync client (OneDrive, Dropbox) "
        f"holding an exclusive handle on the target -- try a non-synced "
        f"path or wait for sync to complete."
    )


@dataclass
class Binding:
    """One EquationMgr.Add2 binding applied during a build."""

    dim: str  # e.g. "D1@SK_Body"
    rhs: str  # the RHS pasted into Add2 (verbatim from spec)
    add2_index: int  # value returned by EquationMgr.Add2; -1 = silent failure


@dataclass
class MassCheck:
    """One feature's mass-verification result (populated when verify_mass=True)."""

    feature: str
    actual_mm3: float
    expected_mm3: float | None = None
    tolerance_mm3: float = 1.0
    passed: bool = True


@dataclass
class BuildResult:
    ok: bool
    features_built: list[str]
    bindings_added: list[Binding]
    error: str | None = None
    error_feature: str | None = None
    # X2 success-gate (FR-X-02): which stage produced `error`. "post_rebuild"
    # when the part built without the feature loop raising but carries SW
    # rebuild errors. None when ok, or when `error` is a feature-loop
    # exception (those leave error_tier unset for v0.x wire-compat).
    error_tier: str | None = None
    save_as: str | None = None
    save_as_verified: bool | None = None
    save_format: str | None = None  # W2.4: "current", "2021".."2024"
    traceback: str | None = None
    # Populated when verify_mass=True. None otherwise. Each entry records
    # the actual volume delta for one feature; entries with expected_mm3
    # also record pass/fail against the _expect block.
    mass_verification: list[dict[str, Any]] | None = None
    build_time_s: float | None = None
    mode: str | None = None  # "no_dim", "deferred_dim", or "parametric"
    # Per-feature build timings (observability triad, P3.1). Each entry:
    # {"name": ..., "type": ..., "build_time_s": ...}. None until populated.
    feature_metrics: list[dict[str, Any]] | None = None
    trace_id: str | None = None
    # X2 success-gate (FR-X-02): per-feature post-rebuild error state. Each
    # entry {name, code, message}; only non-OK (code 1=warning / 2=error)
    # features are listed. None/empty -> omitted from to_dict() so a clean
    # build keeps the v0.x wire format. A code-2 entry forces ok=False with
    # error_tier="post_rebuild"; code-1 fails only under --strict.
    feature_health: list[dict[str, Any]] | None = None
    # Populated when flags.brep_interrogation is ON. The manifest dict
    # (schema_version + features[]) mirrors the build_brep.json sidecar
    # file. None when the flag is OFF — in which case the field is
    # omitted from to_dict() output so the v0.11 wire format is preserved.
    brep_manifest: dict[str, Any] | None = None

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
            "save_as_verified": self.save_as_verified,
        }
        if self.save_format is not None:
            out["save_format"] = self.save_format
        if self.trace_id is not None:
            out["trace_id"] = self.trace_id
        if self.error is not None:
            out["error"] = self.error
        if self.error_feature is not None:
            out["error_feature"] = self.error_feature
        if self.error_tier is not None:
            out["error_tier"] = self.error_tier
        if self.traceback is not None:
            out["traceback"] = self.traceback
        if self.mass_verification is not None:
            out["mass_verification"] = self.mass_verification
        if self.build_time_s is not None:
            out["build_time_s"] = round(self.build_time_s, 3)
        if self.mode is not None:
            out["mode"] = self.mode
        if self.feature_metrics is not None:
            out["feature_metrics"] = self.feature_metrics
        if self.feature_health:
            out["feature_health"] = self.feature_health
        if self.brep_manifest is not None:
            out["brep_manifest"] = self.brep_manifest
        return out


@dataclass
class StepOptions:
    """Immutable per-build settings threaded into :func:`run_feature_step`.

    Bundles the ``build()`` flags and lazily-initialized collaborators so the
    per-feature step has a stable, testable signature instead of a long
    positional argument list. Constructed once per build, before the loop.
    """

    spec: dict[str, Any]
    mode: str
    no_dim: bool
    deferred_dim: bool
    verify_mass: bool
    reconnect: bool
    brep_enabled: bool
    brep_manifest: Any | None
    cp_store: Any | None
    cp_locals_dict: dict[str, Any] | None


@dataclass
class StepResult:
    """Per-feature outputs of one :func:`run_feature_step` call.

    ``build()`` folds these into its run-level accumulators. The cross-feature
    running values (``prev_volume_mm3``, ``deferred_watermark``) are returned
    with their post-feature values so the next step can be threaded from them.
    """

    bf: BuiltFeature
    feature_metric: dict[str, Any]
    bindings: list[Binding]
    mass_entry: dict[str, Any] | None
    prev_volume_mm3: float
    deferred_watermark: int


def run_feature_step(
    ctx: BuildContext,
    feat: dict[str, Any],
    *,
    opts: StepOptions,
    feature_index: int,
    prev_volume_mm3: float,
    deferred_watermark: int,
    built: list[str],
    cp_built: list[dict[str, Any]],
) -> StepResult:
    """Build one feature end-to-end (FR-X-06).

    handler -> brep-interrogate -> verify_mass -> deferred-dim replay ->
    L4 checkpoint -> parametric bindings. Extracted verbatim from ``build()``'s
    feature loop so each per-feature error path (handler raises, mass-delta
    miss, stale-handle reconnect) is directly unit-testable against the mock
    adapter. Behavior is identical to the inline loop: same call order, same
    fail-fast on a mass ``_expect`` miss, same per-sketch deferred-dim cadence,
    same checkpoint pending/committed/failed transitions.

    Mutates ``ctx`` (``features_by_name``, ``deferred_dims``), ``built`` (the
    name appended the instant the handler succeeds), and ``cp_built`` (appended
    on commit) in place, exactly as the inline loop did. Raises on
    handler / binding / mass-verify failure after marking the in-flight
    checkpoint row failed; ``build()`` turns that into a failed ``BuildResult``.
    """
    current_feat_name = feat.get("name")
    logger.debug("feature: %s (%s)", current_feat_name, feat["type"])
    handler = HANDLERS[feat["type"]]

    # L4 checkpoint: open a pending row BEFORE the handler runs so a
    # mid-handler failure leaves a rollback target at the prior
    # post_tree_hash. Transitions to committed after all per-feature work
    # succeeds, or to failed on exception (the except clause below).
    cp_row_id: int | None = None
    if opts.cp_store is not None:
        try:
            from ..checkpoint.snapshot import write_pre_feature as _cp_write

            cp_row_id = _cp_write(
                opts.cp_store,
                spec=opts.spec,
                feature=feat,
                feature_index=len(cp_built),
                already_built=cp_built,
                build_mode=opts.mode,
                locals_snapshot=opts.cp_locals_dict,
            )
        except Exception as e:
            logger.warning("checkpoint pre-write failed: %s", e)
            cp_row_id = None

    try:
        _feat_t0 = time.time()
        try:
            with com_error_boundary(
                feature_name=current_feat_name or "unknown",
                json_path=f"features[{feature_index}]",
                iface_method=f"HANDLERS[{feat['type']}]",
                feature_type=feat["type"],
            ):
                bf = with_reconnect(handler, ctx, feat, reconnect=opts.reconnect)
        except BuildError as be:
            emit_envelope_to_stderr(be)
            raise RuntimeError(be.diagnosis) from be
        feature_metric = {
            "name": current_feat_name,
            "type": feat["type"],
            "build_time_s": round(time.time() - _feat_t0, 3),
        }

        # Stash plane info for plane-based sketches so child extrudes
        # can inherit the parent plane's outward normal as their axis.
        # sketch_ellipse rides the same `plane`+`center` mechanism as the
        # rectangle/circle on-plane primitives, so it stashes identically.
        if bf.type in (
            "sketch_rectangle_on_plane",
            "sketch_circle_on_plane",
            "sketch_ellipse",
        ):
            bf.parent_plane_normal = PLANE_NORMALS[feat["plane"]]

        ctx.features_by_name[bf.name] = bf
        # Record the name the instant the handler succeeds -- BEFORE brep /
        # mass-verify / bindings -- so a failure in any of those still leaves
        # this feature in build()'s ``features_built`` list (the failed
        # BuildResult reports it). Matches the pre-extraction loop exactly.
        built.append(bf.name)

        # W39 — sketch relations: if the feature spec declares relations
        # and this is a sketch-type feature, apply them by re-opening the
        # sketch (EditSketch), selecting segments, and calling
        # SketchAddConstraints. Fail-closed: a relation error raises so
        # the build fails rather than shipping a broken sketch.
        if feat.get("relations") and bf.type in SKETCH_TYPES:
            from ._sketch_relations import apply_relations_to_sketch

            rel_result = apply_relations_to_sketch(
                ctx.doc, bf.name, feat["relations"]
            )
            if not rel_result.get("ok"):
                errors = rel_result.get("errors", [])
                raise RuntimeError(
                    f"sketch relations failed for '{bf.name}': "
                    f"{'; '.join(errors)}"
                )

        # B-rep interrogation (E2.6): walk the feature's faces and
        # accumulate into the manifest. Flag-gated; fail-soft.
        if opts.brep_enabled and opts.brep_manifest is not None:
            try:
                from ..brep import interrogate as _brep_interrogate

                result = _brep_interrogate(bf.sw_object, ctx)
                if result is not None:
                    opts.brep_manifest.add_feature(result, feature_type=bf.type)
            except Exception as e:
                logger.warning(
                    "brep interrogation failed for '%s': %s", bf.name, e
                )

        # Mass verification: read volume after this feature and compare
        # delta against _expect if declared. Runs in ALL modes (the volume
        # delta is mode-independent). A failed _expect fails the build.
        mass_entry: dict[str, Any] | None = None
        if opts.verify_mass:
            _ = ctx.doc.EditRebuild3  # ensure geometry is up to date
            # CreateMassProperty is a zero-arg COM method: pywin32
            # late-binding auto-invokes it on attribute access. Adding ()
            # would call the *returned* IMassProperty and raise.
            mp = ctx.doc.Extension.CreateMassProperty
            vol_mm3 = mp.Volume * 1e9  # SW returns m³
            delta_mm3 = vol_mm3 - prev_volume_mm3
            expect = feat.get("_expect")
            entry: dict[str, Any] = {
                "feature": bf.name,
                "actual_mm3": round(delta_mm3, 2),
            }
            if expect and "mass_delta_mm3" in expect:
                expected = expect["mass_delta_mm3"]
                tol = expect.get("tolerance_mm3", 1.0)
                passed = abs(delta_mm3 - expected) <= tol
                entry["expected_mm3"] = expected
                entry["tolerance_mm3"] = tol
                entry["pass"] = passed
                if not passed:
                    raise RuntimeError(
                        f"mass verification failed for '{bf.name}': "
                        f"actual delta {delta_mm3:.2f} mm³ vs "
                        f"expected {expected} mm³ "
                        f"(tolerance ±{tol} mm³)"
                    )
            mass_entry = entry
            prev_volume_mm3 = vol_mm3

        if not opts.no_dim and opts.deferred_dim:
            # Per-sketch deferred: replay just THIS handler's new DeferredDim
            # entries (popup batch for this sketch only), then apply this
            # feature's bindings + rebuild. NECESSARY because end-of-build
            # replay either fails on cuts against placeholder-size hosts or
            # produces driven (reference) dims that Add2 rejects. Per-sketch
            # replay keeps the dim driving AND resizes geometry before
            # downstream features.
            new_dims = ctx.deferred_dims[deferred_watermark:]
            if new_dims:
                _apply_deferred_dims(
                    ctx,
                    new_dims,
                    label_prefix=f"Deferred dims for {bf.name}",
                )
                deferred_watermark = len(ctx.deferred_dims)

        # L4 checkpoint: transition the pending row to committed now that
        # handler + deferred dims + mass verification succeeded. cp_built
        # grows by one; the post_tree_hash covers the list INCLUDING this
        # feature.
        cp_built.append({"name": bf.name, "type": bf.type})
        if opts.cp_store is not None and cp_row_id is not None:
            try:
                from ..checkpoint.snapshot import commit_post_feature as _cp_commit

                _cp_commit(opts.cp_store, cp_row_id, already_built=cp_built)
            except Exception as e:
                logger.warning("checkpoint post-commit failed: %s", e)

        # Apply this feature's parametric bindings BEFORE the next feature.
        # Without this, a downstream cut may operate on a sketch still at
        # placeholder size (the original MMP Cut_FlangeRecess failure mode).
        bindings: list[Binding] = []
        feat_bindings = _collect_feature_bindings(feat)
        if feat_bindings:
            try:
                with com_error_boundary(
                    feature_name=current_feat_name or "unknown",
                    json_path=f"features[{feature_index}].bindings",
                    iface_method="IEquationMgr.Add2",
                    feature_type=feat["type"],
                ):
                    indices = _apply_bindings(ctx.doc, feat_bindings)
            except BuildError as be:
                emit_envelope_to_stderr(be)
                raise RuntimeError(be.diagnosis) from be
            for (d, r), i in zip(feat_bindings, indices):
                bindings.append(Binding(dim=d, rhs=r, add2_index=i))
            # Force a rebuild so subsequent geometry sees the updated dim
            # values, not the placeholder.
            _ = ctx.doc.EditRebuild3

        return StepResult(
            bf=bf,
            feature_metric=feature_metric,
            bindings=bindings,
            mass_entry=mass_entry,
            prev_volume_mm3=prev_volume_mm3,
            deferred_watermark=deferred_watermark,
        )
    except Exception:
        # L4 checkpoint: mark the in-flight pending row failed so the history
        # records which feature was being attempted. Swallow store errors --
        # the build error is the primary signal. (Colocated with the row
        # creation; build()'s loop turns the re-raise into a failed result.)
        if opts.cp_store is not None and cp_row_id is not None:
            try:
                opts.cp_store.mark_failed(cp_row_id)
            except Exception:
                pass
        raise


def _health_gate(
    feature_health: list[dict[str, Any]], *, strict: bool
) -> tuple[bool, str | None]:
    """Apply the X2 success-gate policy to a post-rebuild feature-health list.

    Policy (FR-X-02): a code-2 (error) feature always fails the build; a
    code-1 (warning) fails only under ``strict``. Pure -- no COM, no I/O --
    so the gate decision is directly unit-testable without a seat.

    Returns ``(ok, error)``: ``(True, None)`` when nothing trips the gate, or
    ``(False, "<message naming the offenders>")`` otherwise.
    """
    offenders = [
        h
        for h in feature_health
        if h["code"] == 2 or (strict and h["code"] == 1)
    ]
    if not offenders:
        return True, None
    named = ", ".join(f"{h['name']} (code {h['code']})" for h in offenders)
    return False, f"post-rebuild feature errors: {named}"


def build(
    spec: dict[str, Any],
    no_dim: bool = False,
    deferred_dim: bool = False,
    save_as: str | None = None,
    save_format: str = "current",
    verify_mass: bool = False,
    reconnect: bool = False,
    checkpoint: bool = False,
    checkpoint_root: "Path | None" = None,
    checkpoint_key_source: Any = None,
    strict: bool = False,
) -> BuildResult:
    """Build the spec into a fresh blank part on the running SW session.

    Caller is responsible for validating the spec first via spec.validator.validate.

    Three modes (see PM/.../popup-suppression-notes for full rationale):

    1) Default (inline parametric, no_dim=False, deferred_dim=False):
       AddDimension2 calls fire inline as each feature builds; Add2 bindings
       run per-feature. ~16 Modify-Dimension popups scattered through the
       build. The resulting SLDPRT has a live equation link to locals.txt.

    2) --no-dim (no_dim=True): {rhs} refs are resolved against spec['locals']
       in Python upfront, geometry builds at literal target sizes, no
       AddDimension2 calls, no Add2 bindings. Zero popups but the SLDPRT
       has no link back to locals.txt; editing locals requires re-running.

    3) --deferred-dim (deferred_dim=True): each sketch builds at PLACEHOLDER
       sizes with NO inline AddDimension2 calls; immediately after the
       sketch handler returns, build() re-enters the sketch and replays
       just that sketch's deferred AddDimension2 calls in one EditSketch
       session, then applies the feature's Add2 bindings and rebuilds.

       The user-facing effect: instead of popups being scattered through
       long-running COM calls (inline mode), each feature's dim popups
       arrive together as a tight cluster right after that feature's
       geometry is built. Total popup count = same as inline; cadence
       is predictable. Verified GREEN on circle/hole specs like
       minimal_cylinder_v2.

       Rectangle sketches: previously --deferred-dim had a SW 2024 SP1
       limitation where D2 was demoted to DRIVEN. Root cause identified
       2026-05-20 (Spike ZF): API CreateCenterRectangle adds a Midpoint
       relation absent from UI version, collapsing 2-DOF to 1-DOF. Fix
       is in _strip_centerrectangle_midpoint_relation, called from both
       rectangle handlers. Rectangle specs now ship clean equation links
       in all three modes.

    `no_dim` and `deferred_dim` are mutually exclusive.

    If `save_as` is provided: after all features build successfully, the
    resulting part is saved to that absolute path via IModelDoc2.SaveAs3
    (version=0 i.e. current, save_options=0 i.e. default). The path must
    be absolute; missing parent directories are created. If the extension
    is not '.sldprt', it is appended.

    If `verify_mass` is True: after each feature's geometry settles
    (post-rebuild), the builder reads the part volume via
    CreateMassProperty, computes the delta vs the previous reading, and
    checks it against the feature's `_expect.mass_delta_mm3` (if any).
    A failed _expect check causes the build to fail-fast (matching the
    existing exception-handling style). Results are recorded in
    BuildResult.mass_verification. NOTE: this adds one COM call per
    feature (CreateMassProperty + Volume) which is typically <50ms but
    adds up on large specs.

    TRADE-OFF: SaveAs3 fires after build() returns from the feature loop
    AND (in --deferred-dim mode) after the deferred-dim phase. So in
    --deferred-dim, the user must tick all popups before SaveAs3 fires.
    To save without any popups, combine `save_as` with `no_dim=True`.

    If `reconnect` is True: when a feature handler raises a stale-handle
    COM error (RPC_S_SERVER_UNAVAILABLE or RPC_E_DISCONNECTED), the build
    tears down the old SW Application proxy, re-acquires it, and retries
    the current handler once. WARNING: the new SW session has no knowledge
    of the partially-built part; the resulting model state is undefined.
    Without `reconnect`, stale-handle errors propagate as normal Tier-B
    failures. Per spec.md §6.9 ComExecutor death-recovery and audit §6.5.

    If `checkpoint` is True: after every feature handler returns (and
    after any deferred-dim / binding / mass-verification work), the
    builder writes a ``committed`` checkpoint row capturing the spec's
    locals snapshot, the feature name/type, and canonical tree hashes
    over the already-built feature dicts. Uses
    :class:`ai_sw_bridge.checkpoint.store.CheckpointStore` scoped to
    the spec name. Gated by ``flags.checkpoint`` at the CLI layer;
    this kwarg is the direct hook for in-process callers and tests.
    `checkpoint_root` overrides the default ``./.checkpoints`` location
    (tests pass ``tmp_path``).
    """
    if no_dim and deferred_dim:
        raise ValueError("no_dim and deferred_dim are mutually exclusive")

    new_trace_id()
    t0 = time.time()
    mode = "no_dim" if no_dim else ("deferred_dim" if deferred_dim else "parametric")
    spec_name = spec.get("name", "unnamed")
    feature_count = len(spec.get("features", []))
    logger.info(
        "build start: name=%s mode=%s features=%d", spec_name, mode, feature_count
    )

    # --no-dim resolves {rhs} upfront so geometry builds at correct sizes
    # (no AddDimension2 ever called, no equation links applied).
    #
    # --deferred-dim does NOT resolve upfront. Each handler builds its
    # sketch at PLACEHOLDER sizes (under-constrained for size), records
    # DeferredDim entries describing the dims to add, and returns. The
    # build() loop then immediately replays just that handler's new
    # entries (popup batch for THIS sketch), applies the feature's
    # bindings, and rebuilds. This per-sketch cadence is required for
    # two reasons -- see the in-loop comment for the full rationale.
    #
    # L4 checkpoint: capture the locals name->value dict BEFORE rhs
    # resolution rewrites spec['locals'] into the resolved spec. The
    # snapshot needs the equation content, not the absolute path.
    cp_locals_dict: dict[str, Any] | None = None
    if checkpoint and isinstance(spec.get("locals"), str):
        try:
            cp_locals_dict = _load_locals_map(spec["locals"])
        except Exception as e:
            logger.warning("checkpoint locals capture failed: %s", e)
            cp_locals_dict = None
    if no_dim:
        spec = _resolve_rhs_in_spec(spec)
        # Unit chokepoint (spec.md §6 / FR-1-02): if the spec declares a
        # non-default length unit, normalize every length field to mm once,
        # here, after rhs resolution has produced numeric values. mm-authored
        # specs (the default, and the only unit v1 accepts) pass through
        # without a copy. Document-display pref-set is a separate SEAT-gated
        # concern in the v2 orchestrator — not this call.
        spec = convert_spec_units(spec, spec.get("units", SpecUnit.MM))

    # B-rep interrogation (E2.6) is gated by flags.brep_interrogation.
    # The manifest is allocated only when the flag is ON so v0.11
    # builds (flag OFF) pay no import or memory cost.
    from ..flags import resolve as _resolve_flags

    brep_enabled = bool(_resolve_flags().get("brep_interrogation", False))
    brep_manifest = None
    if brep_enabled:
        from ..brep.manifest import Manifest as _BrepManifest

        brep_manifest = _BrepManifest()

    sw = get_sw_app()
    doc = create_blank_part(sw)
    ctx = BuildContext(sw=sw, doc=doc, no_dim=no_dim, deferred_dim=deferred_dim)

    # Lazy B-rep interrogation (spec.md §2.11): compute the referenced-face
    # set so the interrogator can skip unreferenced features.
    if brep_enabled:
        from .validator import compute_referenced_face_roles

        ctx.referenced_face_roles = compute_referenced_face_roles(spec)

    # Record the active SW configuration on the brep manifest so any
    # consumer re-running this spec against a different configuration
    # knows the manifest is invalid (audit §6.2). Fail-soft: a missing
    # configuration name leaves it None and the build continues.
    if brep_manifest is not None:
        try:
            cfg = doc.IGetActiveConfiguration
            if callable(cfg):
                cfg = cfg()
            if cfg is not None:
                name = cfg.Name
                if callable(name):
                    name = name()
                if name:
                    brep_manifest.active_configuration = str(name)
        except Exception as _cfg_exc:
            logger.debug("could not read active configuration: %s", _cfg_exc)

    # L4 checkpoint store (spec.md §5.2). Lazy-imported so flag-OFF builds
    # don't pay the import cost. None when checkpoint=False.
    cp_store: Any | None = None
    if checkpoint:
        try:
            from ..checkpoint.store import CheckpointStore as _CpStore
        except Exception as e:
            logger.warning("checkpoint init failed: %s", e)
            cp_store = None
        else:
            try:
                cp_store = _CpStore(
                    part_name=spec_name,
                    root=checkpoint_root,
                    key_source=checkpoint_key_source,
                )
            except Exception as e:
                logger.warning("checkpoint store init failed: %s", e)
                cp_store = None
    cp_built: list[dict[str, Any]] = []

    # Bundle the immutable per-build settings once; run_feature_step (FR-X-06)
    # reads them for every feature so the per-feature body is unit-testable.
    step_opts = StepOptions(
        spec=spec,
        mode=mode,
        no_dim=no_dim,
        deferred_dim=deferred_dim,
        verify_mass=verify_mass,
        reconnect=reconnect,
        brep_enabled=brep_enabled,
        brep_manifest=brep_manifest,
        cp_store=cp_store,
        cp_locals_dict=cp_locals_dict,
    )

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
        # In deferred-dim mode we DO need the link, since per-feature
        # bindings still fire inside the loop and reference locals.
        if spec.get("locals") and not no_dim:
            link_locals(doc, spec["locals"])

        built: list[str] = []
        binding_results: list[Binding] = []
        mass_results: list[dict[str, Any]] = []
        feature_metrics: list[dict[str, Any]] = []  # per-feature timing (P3.1)
        prev_volume_mm3: float = 0.0  # 0 before any feature
        # Track the most recent feature we touched, so a mid-loop exception
        # can report which one failed. Separated from the loop variable so
        # the typechecker can see it's always a string (or None).
        current_feat_name: str | None = None
        # Watermark into ctx.deferred_dims: each handler may append entries;
        # we replay only the new entries (slice [watermark:]) after the
        # handler returns. This is the per-sketch-deferred flow.
        deferred_watermark = 0
        try:
            for feat in spec["features"]:
                # current_feat_name is tracked at this scope so a mid-loop
                # exception's failed BuildResult can name the offending feature.
                current_feat_name = feat.get("name")
                step = run_feature_step(
                    ctx,
                    feat,
                    opts=step_opts,
                    feature_index=len(built),
                    prev_volume_mm3=prev_volume_mm3,
                    deferred_watermark=deferred_watermark,
                    built=built,
                    cp_built=cp_built,
                )
                # run_feature_step appends to ``built`` itself (right after the
                # handler), so the name is present even on a later failure.
                feature_metrics.append(step.feature_metric)
                if step.mass_entry is not None:
                    mass_results.append(step.mass_entry)
                binding_results.extend(step.bindings)
                # Thread the running values forward to the next feature.
                prev_volume_mm3 = step.prev_volume_mm3
                deferred_watermark = step.deferred_watermark
        except Exception as e:
            # run_feature_step has already marked its in-flight checkpoint row
            # failed before re-raising; here we just record the build outcome.
            elapsed = time.time() - t0
            telemetry_counter("builds_total", mode=mode, outcome="fail")
            telemetry_histogram("build_duration_seconds", elapsed, mode=mode)
            logger.info(
                "build fail: name=%s error=%s elapsed=%.1fs",
                spec_name,
                str(e)[:80],
                elapsed,
            )
            return BuildResult(
                ok=False,
                features_built=built,
                bindings_added=binding_results,
                error=str(e),
                error_feature=current_feat_name,
                traceback=traceback.format_exc(),
                mass_verification=mass_results if verify_mass else None,
                build_time_s=elapsed,
                mode=mode,
                feature_metrics=feature_metrics,
                trace_id=trace_id(),
                brep_manifest=(
                    brep_manifest.to_dict() if brep_manifest is not None else None
                ),
            )

        # Final rebuild for good measure
        _ = doc.EditRebuild3

        # P1.2 material: write the spec's material string as a custom
        # property on the part doc (BOM / title-block path). The SW
        # material-library assignment (SetMaterialPropertyName2) is
        # SEAT-gated and deferred — see ai_sw_bridge.material docstring.
        from ..material import apply_material as _apply_material

        mat_result = _apply_material(doc, spec)
        if mat_result is False:
            logger.warning("material custom-property write failed (non-fatal)")

        # X2 build success-gate (FR-X-02): "built" != "manufacturable". The
        # feature loop not raising only means each COM call returned; the part
        # can still carry rebuild errors / over-defined sketches that SW marks
        # post-rebuild. Sweep per-feature GetErrorCode and gate ok on it.
        # Fail-soft: a sweep failure must never sink an otherwise-good build,
        # so a degraded sweep yields an empty health list (gate passes).
        feature_health: list[dict[str, Any]] = []
        try:
            from ..observe import collect_feature_health

            sweep = collect_feature_health(doc)
            for issue in sweep["issues"]:
                feature_health.append(
                    {
                        "name": issue["name"],
                        "code": issue["state_code"],
                        "message": issue["description"],
                    }
                )
            if sweep["error"]:
                logger.debug("feature-health sweep degraded: %s", sweep["error"])
        except Exception as e:
            logger.warning("feature-health sweep failed: %s", e)
            feature_health = []
        health_ok, health_error = _health_gate(feature_health, strict=strict)

        saved_path: str | None = None
        save_as_verified: bool | None = None
        if save_as is not None:
            # Resolve to absolute (SW requires absolute paths for SaveAs)
            # and force the .sldprt extension. Create the parent dir if
            # missing so SaveAs3 doesn't fail on a fresh output tree.
            out_path = Path(save_as)
            if out_path.suffix.lower() != ".sldprt":
                out_path = out_path.with_suffix(".sldprt")
            out_path = out_path.resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            save_version = SAVE_FORMAT_VERSIONS.get(save_format, 0)
            saved_path, save_as_verified = _save_as_with_verification(
                doc, out_path, save_version=save_version
            )

        # B-rep sidecar (E2.6): write build_brep.json alongside the
        # saved part (or in cwd if no save_as). Only when the flag is ON.
        brep_sidecar_path: str | None = None
        if brep_manifest is not None:
            brep_sidecar_path = _write_brep_sidecar(brep_manifest, save_as=saved_path)

        elapsed = time.time() - t0
        outcome = "ok" if health_ok else "fail"
        telemetry_counter("builds_total", mode=mode, outcome=outcome)
        telemetry_histogram("build_duration_seconds", elapsed, mode=mode)
        if health_ok:
            logger.info(
                "build ok: name=%s features=%d elapsed=%.1fs brep=%s",
                spec_name,
                len(built),
                elapsed,
                brep_sidecar_path or "off",
            )
        else:
            logger.info(
                "build fail (post-rebuild): name=%s %s elapsed=%.1fs",
                spec_name,
                health_error,
                elapsed,
            )
        return BuildResult(
            ok=health_ok,
            features_built=built,
            bindings_added=binding_results,
            error=health_error,
            error_tier="post_rebuild" if not health_ok else None,
            save_as=saved_path,
            save_as_verified=save_as_verified,
            save_format=save_format if save_as is not None else None,
            mass_verification=mass_results if verify_mass else None,
            build_time_s=elapsed,
            mode=mode,
            feature_metrics=feature_metrics,
            trace_id=trace_id(),
            feature_health=feature_health or None,
            brep_manifest=(
                brep_manifest.to_dict() if brep_manifest is not None else None
            ),
        )
    finally:
        # Always restore the user's preference, even on exception. Swallow
        # COM errors: a transient RPC disconnect here would otherwise mask
        # a successful build (the BuildResult on the stack is lost when the
        # finally raises). The user's preference toggle is session state,
        # not part of the build contract.
        try:
            sw.SetUserPreferenceToggle(SW_PREF_INPUT_DIM_VAL_ON_CREATE, prev_input_dim)
        except Exception as exc:
            logger.warning(
                "failed to restore SW_PREF_INPUT_DIM_VAL_ON_CREATE: %s",
                exc,
            )
        # L4 checkpoint: release the SQLite handle. Swallow close errors
        # so they don't mask the primary build result.
        if cp_store is not None:
            try:
                cp_store.close()
            except Exception:
                pass
