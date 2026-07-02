"""Revolve-family handlers, relocated from builder.py (Phase 3 Move 2).

revolve_boss / revolve_cut and the shared `_call_feature_revolve`
implementation (the only caller of which are these two handlers). Leaf
module: imports only `.._build_context`, `._common`, and `...sw_types` --
never builder.py or a sibling handler module.
"""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext, BuiltFeature
from ...sw_types import SW_END_COND_BLIND, SW_THIN_WALL_ONE_DIRECTION, assert_args
from ._common import _select_sketch


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
