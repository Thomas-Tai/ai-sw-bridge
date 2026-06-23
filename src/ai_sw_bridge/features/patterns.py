"""Recipe-C strangler relocation of the W21 pattern family (linear/circular/mirror)
from ``mutate.py`` into the HANDLER_REGISTRY.

Handler bodies are byte-identical to the originals in ``mutate.py`` (lines
2020-2264 at the time of relocation, commit on ``feat/w67-phase3``); only the
``def`` names have the leading underscore removed (public registry contract).
Seat-proven W21 (spike 5a94b05, SW2024 SP1). GREEN.
"""

from __future__ import annotations

from typing import Any

from ..com.earlybind import typed
from ..com.sw_type_info import wrapper_module
from .verify import find_feature_by_name as _find_feature_by_name
from .verify import materialized as _materialized

# W21 pattern family — seat-proven (spike 5a94b05, SW2024 SP1). Relocated from
# mutate.py into the registry (Recipe-C strangler). GREEN.
SPIKE_STATUS = "GREEN"


def create_linear_pattern(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a linear pattern of a seed feature along a direction edge.

    Seat-validated recipe (W21 S1, spike ``5a94b05``, SW 2024 SP1):
    ``fm.FeatureLinearPattern5(22 args)`` with marked selections:
      direction edge = mark 1 (SelectByID(EDGE) + SetSelectedObjectMark)
      seed feature   = mark 4 (IFeature.Select2(append=True, mark=4))

    SEED COMPATIBILITY (S1↔S4 unreconciled): S1 saw an ICE (Instant3D)
    seed NO-GO, but S4 patterned an ICE seed to N=3 — so ICE-ness alone is
    NOT a reliable predictor of rejection. The handler is fail-closed
    either way: if FeatureLinearPattern5 rejects the seed it returns None
    and we surface an error; a compatible seed materializes normally.

    ``target`` shape: ``{"seed": "<name>", "direction": {"x": mm, "y": mm,
    "z": mm}}`` where the point lies on the desired direction edge.
    ``feature.spacing_mm`` (positive number), ``feature.count`` (int >= 2),
    optional ``feature.flip`` (bool).

    **Direction-2 (optional, closed-form):** supply ``target.direction2``
    (a point on a second edge) + ``feature.count2`` (int >= 2) +
    ``feature.spacing2_mm`` (positive) + optional ``feature.flip2``.  The
    second edge is marked 2; ``FeatureLinearPattern5`` arg-3/4/6 (Num2/
    Spacing2/FlipDir2) carry it.  Omitted ⇒ Num2=1 (single direction, the
    W21 default — byte-identical).

    **Multi-seed (optional):** supply ``target.seeds`` (a list of feature
    names) to pattern several seeds together; each is marked 4 (append).
    Omitted ⇒ the single ``target.seed`` (back-compat).
    """
    # seeds: list form wins; else single seed (back-compat)
    seeds = target.get("seeds") if isinstance(target, dict) else None
    if seeds is None:
        single = target.get("seed") if isinstance(target, dict) else None
        if not single:
            return False, "target.seed must be a non-empty feature name"
        seed_names = [single]
    else:
        if not isinstance(seeds, list) or not seeds or not all(
            isinstance(s, str) and s for s in seeds
        ):
            return False, "target.seeds must be a non-empty list of feature names"
        seed_names = seeds
    direction = target.get("direction") if isinstance(target, dict) else None
    if not isinstance(direction, dict):
        return False, "target.direction must be a dict with x, y, z (mm)"
    spacing_mm = feature.get("spacing_mm") if isinstance(feature, dict) else None
    if not isinstance(spacing_mm, (int, float)) or spacing_mm <= 0:
        return False, "feature.spacing_mm must be a positive number"
    count = feature.get("count") if isinstance(feature, dict) else None
    if not isinstance(count, int) or count < 2:
        return False, "feature.count must be an integer >= 2"
    flip = bool(feature.get("flip", False)) if isinstance(feature, dict) else False

    # --- optional direction 2 ------------------------------------------------
    direction2 = target.get("direction2") if isinstance(target, dict) else None
    num2 = 1
    spacing2_m = 0.0
    flip2 = False
    if direction2 is not None:
        if not isinstance(direction2, dict):
            return False, "target.direction2 must be a dict with x, y, z (mm)"
        count2 = feature.get("count2") if isinstance(feature, dict) else None
        if not isinstance(count2, int) or count2 < 2:
            return False, "feature.count2 must be an integer >= 2 when direction2 is set"
        spacing2_mm = feature.get("spacing2_mm") if isinstance(feature, dict) else None
        if not isinstance(spacing2_mm, (int, float)) or spacing2_mm <= 0:
            return False, "feature.spacing2_mm must be a positive number when direction2 is set"
        num2 = count2
        spacing2_m = float(spacing2_mm) / 1000.0
        flip2 = bool(feature.get("flip2", False)) if isinstance(feature, dict) else False

    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        seed_feats = []
        for name in seed_names:
            sf = _find_feature_by_name(doc, name)
            if sf is None:
                return False, f"seed feature {name!r} not found in feature tree"
            seed_feats.append((name, sf))

        sel_mgr = doc.SelectionManager
        doc.ClearSelection2(True)

        # 1. Direction edge (mark=1)
        dx = float(direction["x"]) / 1000.0
        dy = float(direction["y"]) / 1000.0
        dz = float(direction["z"]) / 1000.0
        if not doc.SelectByID("", "EDGE", dx, dy, dz):
            return False, (
                f"could not select direction edge at ({direction['x']}, "
                f"{direction['y']}, {direction['z']}) mm"
            )
        if not sel_mgr.SetSelectedObjectMark(1, 1, 0):
            return False, "SetSelectedObjectMark(1, 1, 0) failed for direction"

        # 1b. Direction-2 edge (mark=2), if requested. Appending coordinate
        # selection needs the TYPED IModelDocExtension.SelectByID2 (the raw
        # late-bound doc has no SelectByID2, and a bare-None callout only
        # walls on the raw proxy — the typed proxy coerces it correctly).
        if direction2 is not None:
            ext = typed(doc.Extension, "IModelDocExtension")
            d2x = float(direction2["x"]) / 1000.0
            d2y = float(direction2["y"]) / 1000.0
            d2z = float(direction2["z"]) / 1000.0
            if not ext.SelectByID2("", "EDGE", d2x, d2y, d2z, True, 2, None, 0):
                return False, (
                    f"could not select direction2 edge at ({direction2['x']}, "
                    f"{direction2['y']}, {direction2['z']}) mm"
                )

        # 2. Seed(s) (mark=4, append)
        for name, sf in seed_feats:
            if not sf.Select2(True, 4):
                return False, f"IFeature.Select2 on seed {name!r} returned False"

        # 3. FeatureLinearPattern5 (22 args)
        spacing_m = float(spacing_mm) / 1000.0
        feat = fm.FeatureLinearPattern5(
            count, spacing_m, num2, spacing2_m,
            flip, flip2, "", "",
            False, False, False, False,
            False, False, False, False,
            False, False, 0.0, 0.0, False, False,
        )
        if _materialized(feat):
            return True, None
        return False, "FeatureLinearPattern5 returned None (the seed feature was rejected by the API — e.g. an incompatible seed type)"
    except Exception as exc:
        return False, f"linear pattern pipeline failed: {exc!r}"


def create_circular_pattern(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a circular pattern of a seed feature around an axis.

    Seat-validated recipe (W21 S1, spike ``5a94b05``, SW 2024 SP1):
    ``fm.FeatureCircularPattern5(14 args)`` with marked selections:
      axis = mark 1 (SelectByID2(AXIS, mark=1))
      seed = mark 4 (IFeature.Select2(append=True, mark=4))

    ``target`` shape: ``{"seed": "<name>", "axis": "<axis name>"}``.
    ``feature.count`` (int >= 2), ``feature.angle_deg`` (positive number,
    default 360) OR ``feature.equal_spacing`` (bool, default True),
    optional ``feature.flip`` (bool).
    """
    seed_name = target.get("seed") if isinstance(target, dict) else None
    if not seed_name:
        return False, "target.seed must be a non-empty feature name"
    axis_name = target.get("axis") if isinstance(target, dict) else None
    if not axis_name:
        return False, "target.axis must be a non-empty axis name"
    count = feature.get("count") if isinstance(feature, dict) else None
    if not isinstance(count, int) or count < 2:
        return False, "feature.count must be an integer >= 2"
    equal_spacing = bool(feature.get("equal_spacing", True)) if isinstance(feature, dict) else True
    angle_deg = feature.get("angle_deg", 360.0) if isinstance(feature, dict) else 360.0
    if not isinstance(angle_deg, (int, float)) or angle_deg <= 0:
        return False, "feature.angle_deg must be a positive number"
    flip = bool(feature.get("flip", False)) if isinstance(feature, dict) else False

    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        mod = wrapper_module()
        seed_feat = _find_feature_by_name(doc, seed_name)
        if seed_feat is None:
            return False, f"seed feature {seed_name!r} not found in feature tree"

        # 1. Axis (mark=1)
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        doc.ClearSelection2(True)
        if not ext.SelectByID2(axis_name, "AXIS", 0, 0, 0, False, 1, None, 0):
            return False, f"could not select axis {axis_name!r}"

        # 2. Seed (mark=4)
        if not seed_feat.Select2(True, 4):
            return False, f"IFeature.Select2 on seed {seed_name!r} returned False"

        # 3. FeatureCircularPattern5 (14 args)
        # NOTE: Spacing is in DEGREES (not radians) — seat-proven W21 S4.
        feat = fm.FeatureCircularPattern5(
            count, float(angle_deg), flip, "",
            False, equal_spacing, False, False,
            False, False, 1, 0.0, "", False,
        )
        if _materialized(feat):
            return True, None
        return False, "FeatureCircularPattern5 returned None"
    except Exception as exc:
        return False, f"circular pattern pipeline failed: {exc!r}"


def create_mirror_feature(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Mirror a seed feature about a named plane.

    Seat-validated recipe (W21 S1, spike ``5a94b05``, SW 2024 SP1):
    ``fm.InsertMirrorFeature2(False, False, False, False, 0)`` (5 args)
    with marked selections:
      plane = mark 2 (SelectByID(PLANE) + SetSelectedObjectMark)
      seed  = mark 1 (IFeature.Select2(append=True, mark=1))

    ``target`` shape: ``{"seed": "<name>", "plane": "<plane name>"}``.
    Plane can be a standard plane name ("Front Plane", "Top Plane",
    "Right Plane") or a user-created ref_plane name.
    """
    seed_name = target.get("seed") if isinstance(target, dict) else None
    if not seed_name:
        return False, "target.seed must be a non-empty feature name"
    plane_name = target.get("plane") if isinstance(target, dict) else None
    if not plane_name:
        return False, "target.plane must be a non-empty plane name"

    doc.ForceRebuild3(False)
    try:
        fm = doc.FeatureManager
        seed_feat = _find_feature_by_name(doc, seed_name)
        if seed_feat is None:
            return False, f"seed feature {seed_name!r} not found in feature tree"

        # 1. Plane (mark=2)
        doc.ClearSelection2(True)
        if not doc.SelectByID(plane_name, "PLANE", 0.0, 0.0, 0.0):
            return False, f"could not select plane {plane_name!r}"
        sel_mgr = doc.SelectionManager
        if not sel_mgr.SetSelectedObjectMark(1, 2, 0):
            return False, "SetSelectedObjectMark(1, 2, 0) failed for plane"

        # 2. Seed (mark=1)
        if not seed_feat.Select2(True, 1):
            return False, f"IFeature.Select2 on seed {seed_name!r} returned False"

        # 3. InsertMirrorFeature2 (5 args)
        feat = fm.InsertMirrorFeature2(False, False, False, False, 0)
        if _materialized(feat):
            return True, None
        return False, "InsertMirrorFeature2 returned None"
    except Exception as exc:
        return False, f"mirror feature pipeline failed: {exc!r}"
