"""W68 - ``sketch_driven_pattern`` feature-add handler (registry seam).

Replicates a seed feature at locations defined by points in a reference
sketch, via legacy ``IFeatureManager.FeatureSketchDrivenPattern``.

  **Mode-B only (operative path)**: pre-select the SEED feature to
  pattern (pattern-family seed mark = 4) and the reference SKETCH that
  holds the pattern points (mark UNKNOWN -- try 1, fall back to 2). Then::

      feat = fm.FeatureSketchDrivenPattern(UseCentroid=True, BGeomPatt=False)

  The method signature is 2-arg (both Boolean) per DLL reflection.

  Sibling to ``FeatureLinearPattern5`` / ``FeatureCircularPattern5``
  (shipped in the W21 patterns spike) -- the sketch-driven variant is
  the 4th pattern family (linear / circular / mirror / sketch).

Verify-the-EFFECT (W21/W42 doctrine): success = face count UP AND volume
delta > 0 (the pattern replicates the additive seed).  A non-None
Feature return ALONE is the W21/W42 ghost trap.
"""

from __future__ import annotations

import logging
from typing import Any

from ..selection.live import select_entity
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.sketch_driven_pattern")

# seat-proven 2026-06-21: FeatureSketchDrivenPattern(use_centroid, geom_patt) on
# seed(mark 4) + ref-sketch(mark 1) -> 'SketchPattern' node, +5 faces/+423mm³ on
# a 3-point sketch, survives reopen. Ref-sketch mark UNKNOWN resolved to 1.
SPIKE_STATUS = "GREEN"

VERIFY_CLASS = verify.FeatureClass.ADDITIVE_SOLID


def _metrics(doc: Any) -> tuple[int, float]:
    """(face_count, volume_mm3) over solid bodies. Delegates to the W67 verify
    substrate (``visible_only=False`` -- Phase-3 normalized)."""
    return verify.solid_metrics(doc)


def _select_seed(doc: Any, seed_name: str) -> bool:
    """Select the seed feature by name with mark=4 (pattern-family seed).

    Uses ``FeatureByName`` + ``select_entity`` (the proven post-resolve
    selection path). Returns ``True`` if selection succeeded.
    """
    try:
        seed_feat = doc.FeatureByName(seed_name)
    except Exception as e:
        logger.warning("[select_seed] FeatureByName(%r) RAISED: %r", seed_name, e)
        return False
    if seed_feat is None:
        logger.warning("[select_seed] FeatureByName(%r) -> None", seed_name)
        return False
    try:
        ok = select_entity(seed_feat, mark=4)
    except Exception as e:
        logger.warning("[select_seed] select_entity(seed) RAISED: %r", e)
        return False
    if not ok:
        logger.warning("[select_seed] select_entity(seed, mark=4) -> False")
    return ok


def _select_sketch(
    doc: Any, sketch_name: str, *, append: bool = True,
) -> tuple[bool, int]:
    """Select the reference sketch, trying mark=1 then mark=2.

    Returns ``(success, mark_used)``.
    """
    try:
        sketch_feat = doc.FeatureByName(sketch_name)
    except Exception as e:
        logger.warning("[select_sketch] FeatureByName(%r) RAISED: %r", sketch_name, e)
        return False, -1
    if sketch_feat is None:
        logger.warning("[select_sketch] FeatureByName(%r) -> None", sketch_name)
        return False, -1

    for mark in (1, 2):
        try:
            ok = select_entity(sketch_feat, append=append, mark=mark)
        except Exception as e:
            logger.warning("[select_sketch] select_entity(mark=%d) RAISED: %r", mark, e)
            continue
        if ok:
            logger.warning("[select_sketch] select_entity(mark=%d) -> True", mark)
            return True, mark
        logger.warning("[select_sketch] select_entity(mark=%d) -> False", mark)
    return False, -1


def _fire(doc: Any, use_centroid: bool, geom_patt: bool) -> Any | None:
    """Call ``FeatureSketchDrivenPattern`` with the callable-or-property guard."""
    try:
        fm = doc.FeatureManager
        method = fm.FeatureSketchDrivenPattern
        if callable(method):
            result = method(use_centroid, geom_patt)
        else:
            logger.warning("[fire] FeatureSketchDrivenPattern is not callable: %r", method)
            return None
        logger.warning(
            "[fire] FeatureSketchDrivenPattern(%r, %r) -> %r",
            use_centroid, geom_patt, result,
        )
        return result
    except Exception as e:
        logger.warning("[fire] FeatureSketchDrivenPattern RAISED: %r", e)
        return None


def create_sketch_driven_pattern(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Create a sketch-driven pattern from a seed feature + reference sketch.

    Fail-closed: returns ``(False, reason)`` on any failure; never raises.

    ``feature`` keys
        seed_name    : str  -- name of the seed feature to pattern
        sketch_name  : str  -- name of the reference sketch with pattern points
        use_centroid : bool -- anchor pattern instances at seed centroid (default True)
        geom_pattern : bool -- geometry pattern (default False)

    ``target`` keys
        (reserved for future seed/sketch ref resolution; not used yet)
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    seed_name = feature.get("seed_name")
    if not seed_name or not isinstance(seed_name, str):
        return False, "feature must include a non-empty 'seed_name' string"

    sketch_name = feature.get("sketch_name")
    if not sketch_name or not isinstance(sketch_name, str):
        return False, "feature must include a non-empty 'sketch_name' string"

    use_centroid = bool(feature.get("use_centroid", True))
    geom_patt = bool(feature.get("geom_pattern", False))

    faces_before, vol_before = _metrics(doc)
    if faces_before == 0:
        return False, "document has no solid bodies to pattern"

    try:
        doc.ClearSelection2(True)
    except Exception as e:
        logger.warning("[create] ClearSelection2 RAISED: %r", e)
        return False, f"ClearSelection2 raised: {e!r}"

    if not _select_seed(doc, seed_name):
        return False, f"failed to select seed feature {seed_name!r} (mark=4)"

    sketch_ok, mark_used = _select_sketch(doc, sketch_name, append=True)
    if not sketch_ok:
        return False, (
            f"failed to select reference sketch {sketch_name!r} "
            f"(tried marks 1 and 2)"
        )

    _fire(doc, use_centroid, geom_patt)

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    faces_after, vol_after = _metrics(doc)
    d_faces = faces_after - faces_before
    d_vol = vol_after - vol_before

    if verify.gate_additive_solid(d_faces, d_vol):
        return True, (
            f"sketch_driven_pattern created (seed={seed_name!r}, "
            f"sketch={sketch_name!r}, sketch_mark={mark_used}, "
            f"+{d_faces} faces, +{d_vol:.3f} mm3)"
        )

    return False, (
        f"sketch_driven_pattern did not replicate geometry "
        f"(delta_faces={d_faces}, delta_vol_mm3={d_vol:.3f}); "
        f"seed={seed_name!r}, sketch={sketch_name!r}, sketch_mark={mark_used}"
    )

# Registration is via the sanctioned ``_register_lane`` gate in
# ``features/__init__.py`` (W67 Phase-4 fail-loud path) — not a module-level
# self-register block.
