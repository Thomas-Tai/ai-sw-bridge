"""Extrude-family build handlers (boss + cut), relocated from builder.py.

Phase 3 Move 6 (the final family): a pure, byte-identical relocation of the
boss and cut extrude handlers, their FeatureExtrusion2/FeatureCut4 call
wrappers, and the version-dispatched FeatureCut4 arg-builders. The two
``@versioned`` arg-builders self-register into the version resolver at import
time, so builder.py re-imports this module to keep that registration live.
"""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext, BuiltFeature
from .._face_geometry import _select_extrude_face
from .._sketch_primitives import PLACEHOLDER_MM, _literal_or_default
from .._version_resolver import DEFAULT_KEY, SW_2025_MAJOR, resolve_op, versioned
from ...sw_types import (
    SW_END_COND_BLIND,
    SW_END_COND_MID_PLANE,
    SW_END_COND_THROUGH_ALL,
    SW_END_COND_UP_TO_SURFACE,
    SW_START_SKETCH_PLANE,
    assert_args,
)
from ._common import _select_sketch


def _call_feature_extrusion(
    ctx: BuildContext,
    *,
    end_cond: int,
    depth_m: float,
    flip: bool,
    merge: bool = True,
    end_cond2: int | None = None,
    depth2_m: float = 0.0,
) -> Any:
    """Boss-only extrusion. For cuts use _call_feature_cut (FeatureCut4).

    ``merge`` is the modeling-time boolean: True (default) fuses this boss into
    any solid body it overlaps (UNION); False keeps it as a separate body
    (multi-body). This is the invariant-clean stand-in for the walled post-hoc
    ``combine`` — see docs/decisions.md (no in-process macro/add-in).

    ``end_cond2``/``depth2_m`` opt into a second (reverse) direction
    (two-direction boss): when given, ``Sd`` flips False and ``T2``/``D2`` carry
    the second direction. When ``None`` (default) the tuple is byte-for-byte the
    single-direction shape (W67 P5: additive).

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
    single_dir = end_cond2 is None
    args = (
        single_dir,  # 1  Sd (single-ended unless a 2nd direction is requested)
        flip,  # 2  Flip
        False,  # 3  Dir (use sketch normal)
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
        merge,  # 18 Merge (True=union into existing body, False=separate body)
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
        end_cond=end_cond,
        depth_m=depth_m,
        flip=flip,
        end_cond2=end_cond2,
        depth2_m=depth2_m,
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
        end_cond=end_cond,
        depth_m=depth_m,
        flip=flip,
        end_cond2=end_cond2,
        depth2_m=depth2_m,
    )
    assert_args("IFeatureManager.FeatureCut4", args)
    fm = ctx.doc.FeatureManager
    feature = fm.FeatureCut4(*args)
    if feature is None:
        raise RuntimeError("FeatureCut4 returned None")
    return feature


def _build_boss_extrude_blind(ctx: BuildContext, feat: dict[str, Any]) -> BuiltFeature:
    sketch_name = feat["sketch"]
    sketch = ctx.features_by_name[sketch_name]

    _select_sketch(ctx, sketch_name)
    depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["extrude_depth"])
    flip = bool(feat.get("flip", False))
    merge = bool(feat.get("merge", True))

    f = _call_feature_extrusion(
        ctx, end_cond=SW_END_COND_BLIND, depth_m=depth_m, flip=flip, merge=merge
    )
    f.Name = feat["name"]
    return _boss_built_feature(feat, sketch, sketch_name, f, depth_m, flip)


def _boss_built_feature(
    feat: dict[str, Any],
    sketch: Any,
    sketch_name: str,
    f: Any,
    depth_m: float | None,
    flip: bool,
) -> BuiltFeature:
    """Build the rich BuiltFeature shared by every boss-extrude variant — the
    extrude axis/origin derivation downstream face-selects depend on.

    ``depth_m`` is the +normal extent recorded for that derivation: full depth
    for blind/two-direction, depth/2 for midplane (the +normal half), and
    ``None`` for through-all (terminus is geometry-dependent — no fixed extent).
    """
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


def _build_boss_extrude_midplane(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Mid-plane boss: adds ``depth`` of material centred on the sketch plane
    (depth/2 each side). One arg-shape change vs blind — T1 = mid-plane. The
    +normal half-extent (depth/2) is recorded for downstream face derivation."""
    sketch_name = feat["sketch"]
    sketch = ctx.features_by_name[sketch_name]
    _select_sketch(ctx, sketch_name)
    depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["extrude_depth"])
    flip = bool(feat.get("flip", False))
    merge = bool(feat.get("merge", True))
    f = _call_feature_extrusion(
        ctx, end_cond=SW_END_COND_MID_PLANE, depth_m=depth_m, flip=flip, merge=merge
    )
    f.Name = feat["name"]
    return _boss_built_feature(feat, sketch, sketch_name, f, depth_m / 2.0, flip)


def _build_boss_extrude_through_all(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Through-all boss: extrudes material until it terminates against existing
    geometry. T1 = through-all, no depth. NOTE: a through-all BOSS requires a
    pre-existing body to terminate against — SW errors on an empty part; the
    lint advisory flags a spec that places it without a prior solid. No fixed
    extent, so the rich metadata records ``None`` for extrude_depth_m."""
    sketch_name = feat["sketch"]
    sketch = ctx.features_by_name[sketch_name]
    _select_sketch(ctx, sketch_name)
    flip = bool(feat.get("flip", False))
    merge = bool(feat.get("merge", True))
    f = _call_feature_extrusion(
        ctx, end_cond=SW_END_COND_THROUGH_ALL, depth_m=0.0, flip=flip, merge=merge
    )
    f.Name = feat["name"]
    return _boss_built_feature(feat, sketch, sketch_name, f, None, flip)


def _build_boss_extrude_two_direction(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Two-direction boss: ``depth`` into +normal AND ``depth2`` into -normal
    from the sketch plane. Drives FeatureExtrusion2 with Sd=False and
    independent T1/D1, T2/D2 (both blind). +normal extent recorded for
    downstream derivation; the -normal (depth2) face is not in the metadata."""
    sketch_name = feat["sketch"]
    sketch = ctx.features_by_name[sketch_name]
    _select_sketch(ctx, sketch_name)
    depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["extrude_depth"])
    depth2_m = _literal_or_default(feat["depth2"], PLACEHOLDER_MM["extrude_depth"])
    flip = bool(feat.get("flip", False))
    merge = bool(feat.get("merge", True))
    f = _call_feature_extrusion(
        ctx,
        end_cond=SW_END_COND_BLIND,
        depth_m=depth_m,
        flip=flip,
        merge=merge,
        end_cond2=SW_END_COND_BLIND,
        depth2_m=depth2_m,
    )
    f.Name = feat["name"]
    return _boss_built_feature(feat, sketch, sketch_name, f, depth_m, flip)


def _build_boss_extrude_up_to_surface(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Up-to-surface boss: extrudes the profile until it terminates on a durable
    reference surface (``target_ref`` = a face of an earlier extrusion).

    Seat-proven OOP recipe (W67 P5 Tier 2,
    ``spikes/v0_2x/spike_extrude_up_to_surface.py``):

      * T1 = ``swEndCondUpToSurface`` (4) — NOT ``swEndCondUpToSelection`` (10).
        The "modern" UpToSelection constant the API docs steer you toward
        SILENTLY NO-OPS out-of-process (feature never materialises); the
        formally-deprecated UpToSurface is the only functional OOP path. See
        the memory note / DEFERRED.md — do not "fix" this to 10.
      * The up-to target is read off the SELECTION STACK (FeatureExtrusion2 has
        no explicit reference-entity arg). Stack order (hygiene): profile sketch
        first (Mark 0), target surface second. The selection MARK is irrelevant
        (0/1/2 all proven) — what gates is T1=4 + the reference being present.

    No fixed +normal extent (terminus is the target surface), so the rich
    metadata records ``None`` for extrude_depth_m (same as through-all)."""
    sketch_name = feat["sketch"]
    sketch = ctx.features_by_name[sketch_name]

    target = feat["target_ref"]
    target_name = target["of_feature"]
    target_parent = ctx.features_by_name.get(target_name)
    if target_parent is None:
        raise RuntimeError(
            f"boss_extrude_up_to_surface '{feat['name']}': target_ref "
            f"'{target_name}' not built yet"
        )
    if target_parent.extrude_axis is None:
        raise RuntimeError(
            f"boss_extrude_up_to_surface '{feat['name']}': target_ref "
            f"'{target_name}' is not an extrusion with known faces"
        )

    # 1) Resolve the up-to target face -> durable IFace2 pointer (the normal-
    #    verified face-center selection the stacked-extrude path already uses).
    target_face = target["face"]
    ok, *_ = _select_extrude_face(ctx, target_parent, target_face)
    if not ok:
        raise RuntimeError(
            f"boss_extrude_up_to_surface '{feat['name']}': could not select "
            f"up-to target face '{target_face}' of '{target_name}'"
        )
    target_face_obj = ctx.doc.SelectionManager.GetSelectedObject6(1, -1)
    if target_face_obj is None:
        raise RuntimeError(
            f"boss_extrude_up_to_surface '{feat['name']}': up-to target face "
            f"selected but GetSelectedObject6 returned None"
        )

    # 2) Select the profile sketch (Mark 0) — clears the target selection.
    _select_sketch(ctx, sketch_name)

    # 3) Re-append the target surface (callout-free IEntity.Select2, immune to
    #    the SelectByID2 ICallout OOP wall; mark-agnostic per the seat proof).
    if not target_face_obj.Select2(True, 0):
        raise RuntimeError(
            f"boss_extrude_up_to_surface '{feat['name']}': could not append the "
            f"up-to target surface to the selection stack"
        )

    flip = bool(feat.get("flip", False))
    merge = bool(feat.get("merge", True))
    f = _call_feature_extrusion(
        ctx, end_cond=SW_END_COND_UP_TO_SURFACE, depth_m=0.0, flip=flip, merge=merge
    )
    f.Name = feat["name"]
    return _boss_built_feature(feat, sketch, sketch_name, f, None, flip)


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


def _build_cut_extrude_midplane(
    ctx: BuildContext, feat: dict[str, Any]
) -> BuiltFeature:
    """Mid-plane cut: removes ``depth`` of material centred on the sketch plane
    (``depth/2`` each side). One arg-shape change vs blind -- T1 = mid-plane.
    Like the other cuts it emits a bare BuiltFeature (no extrude_origin/axis
    metadata; cuts don't feed the downstream face-geometry derivation)."""
    sketch_name = feat["sketch"]
    _select_sketch(ctx, sketch_name)
    depth_m = _literal_or_default(feat["depth"], PLACEHOLDER_MM["cut_depth"])
    flip = bool(feat.get("flip", False))
    f = _call_feature_cut(
        ctx, end_cond=SW_END_COND_MID_PLANE, depth_m=depth_m, flip=flip
    )
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
        ctx,
        end_cond=SW_END_COND_BLIND,
        depth_m=depth_m,
        flip=flip,
        end_cond2=SW_END_COND_BLIND,
        depth2_m=depth2_m,
    )
    f.Name = feat["name"]
    return BuiltFeature(name=feat["name"], type=feat["type"], sw_object=f)
