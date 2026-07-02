"""Pattern-family handlers, relocated from builder.py (Phase 3 Move 1).

linear_pattern / circular_pattern / mirror_feature and the shared
`_mark_first_selection` selection-mark workaround (the only caller of which
are these three handlers). Leaf module: imports only `.._build_context`,
`.._face_geometry`, `.._sketch_primitives`, and `...sw_types` -- never
builder.py or a sibling handler module.
"""

from __future__ import annotations

from typing import Any

from .._build_context import BuildContext, BuiltFeature
from .._face_geometry import PLANE_FULL_NAME
from .._sketch_primitives import _literal_or_default
from ...sw_types import SW_FEATURE_SCOPE_ALL_BODIES, assert_args


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
