"""W62 - ``project_curve`` feature-add handler (registry seam).

Projects a sketch onto a face/surface -> 3D reference curve.

  **Mode-A (QUARANTINED -- documented unreachable for CREATION)**: the
  SW2024 swconst harvest exposes only ids 14/61 in the curve family.
  CreateDefinition(61) returns None; CreateDefinition(14) yields a generic
  ref-curve container whose runtime type rejects QI for ALL ref-curve
  FeatureData interfaces (IReferenceCurveFeatureData,
  IProjectedCurveFeatureData, IRefCurveFeatureData,
  ICompositeCurveFeatureData, ISplitLineFeatureData) -- every QI returned
  False on the live seat 2026-06-17. Same class as composite, helix,
  split_line. Mode-A is a no-op stub.

  **Mode-B (legacy, operative path)**: select sketch + face, then call
  ``IModelDoc2.InsertProjectedSketch2(Reverse: int)`` -- 1-arg, returns
  DISPATCH (the projected sketch feature). The spike's O1 typelib walk
  discovered this; the worker brief named only the WRONG candidates
  (InsertProjectCurve / InsertProjectedCurve / InsertRefCurve -- all
  ``not_found`` on IModelDoc2 and IFeatureManager). Fallback to the
  0-arg ``InsertProjectedSketch`` if 2-form misbehaves.

Verify-the-EFFECT: a new ref-curve feature node materialized via
``IFeatureManager.GetFeatures(False)`` with type-name matching
"ProjectedSketch" / "RefCurve" / "ProjectedCurve". No volume delta -- a
projected curve is a reference curve, not solid geometry.

Why GetFeatures(False) and not FirstFeature: proven on W62 composite seat
fire 2026-06-17 -- FirstFeature is unreachable on the raw late-bound doc
out-of-process; GetFeatures(False) is reachable.
"""

from __future__ import annotations

import logging
from typing import Any

from ..com.earlybind import typed_qi
from ..selection.live import select_entity
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.project_curve")

# Flipped to "GREEN" by W0 after the seat spike fires and a mode produces
# a reference-curve node surviving save->reopen. While "UNRUN", the
# handler exists but is NOT registered in HANDLER_REGISTRY.
SPIKE_STATUS = "GREEN"  # Mode-B-insert fired clean + survived save->reopen on live seat (W62)

# Verify class (W67): CURVE — witnessed by a ref-curve-node count delta. NOTE
# (Phase-3 finding): node presence is trusted without a geometric scalar;
# hardening the CURVE witness is W67 Phase 3.
VERIFY_CLASS = verify.FeatureClass.CURVE

_SW_FM_REF_CURVE = 14

_REF_CURVE_QI_IFACES = (
    "IReferenceCurveFeatureData",
    "IProjectedCurveFeatureData",
    "IRefCurveFeatureData",
)

_FEATURE_TREE_WALK_LIMIT = 500

# Type-name tokens for the verify gate (any ref-curve feature node counts).
_NODE_TYPE_TOKENS = ("refcurve", "projectedcurve", "projectedsketch", "ref_curve")


def _count_feature_nodes(doc: Any) -> int:
    """Count feature-tree nodes whose type matches a ref-curve token. Delegates
    to the W67 verify substrate (substring match over ``_NODE_TYPE_TOKENS``,
    walk bounded at ``_FEATURE_TREE_WALK_LIMIT``; ``GetFeatures(False)`` is the
    W62-canonical substrate — ``FirstFeature`` is unreachable out-of-process)."""
    return verify.count_nodes_by_type(
        doc, _NODE_TYPE_TOKENS, match="substring", limit=_FEATURE_TREE_WALK_LIMIT,
    )


def _curve_length_mm(node: Any) -> float | None:
    """Arc length (mm) of the new projected-curve node, or None if unreadable.
    Delegates to the W67 verify substrate — seat-proven that the projected node
    is a RefCurve reached via the same IReferenceCurve.GetSegments → IEdge.
    GetCurve → ICurve.GetLength head as helix/composite (project_curve 40.0 mm).
    Offline tests patch this shim."""
    return verify.curve_length_mm(node)


def _qi_ref_curve(data: Any) -> Any | None:
    """QI *data* for a ref-curve / projection FeatureData iface.

    Returns the first successfully QI'd typed wrapper, or ``None`` if
    every probe raises (E_NOINTERFACE / EarlyBindError / other). Retained
    for the historical Mode-A path -- the live seat proves no QI succeeds.
    """
    for iface in _REF_CURVE_QI_IFACES:
        try:
            return typed_qi(data, iface)
        except Exception:
            continue
    return None


def _try_mode_a(doc: Any, feature: dict) -> Any | None:
    """Mode-A: QUARANTINED -- documented unreachable for CREATION.

    The SW2024 swconst harvest + live-seat probe (2026-06-17) proved:
        * CreateDefinition(61=swFmReferenceCurve) returns None.
        * CreateDefinition(14=swFmRefCurve) returns a CDispatch whose
          runtime type rejects QI for ALL 5 candidate ref-curve
          FeatureData interfaces (the spike walked
          IReferenceCurveFeatureData, IProjectedCurveFeatureData,
          IRefCurveFeatureData, ICompositeCurveFeatureData,
          ISplitLineFeatureData -- every QI returned False).
    Same class as composite (W62 2a04542), helix (W62 057789a), and
    split_line. The ref-curve FeatureData ifaces are edit-only via
    IFeature.GetDefinition() on an existing node. Returning None here
    routes the handler to Mode-B without spending a CreateDefinition
    call every invocation.
    """
    return None


def _try_mode_b_insert(doc: Any, feature: dict, target: dict) -> Any | None:
    """Mode-B(a): select sketch + face, then InsertProjectedSketch2(Reverse).

    The spike's O1 typelib walk discovered the correct method:
    ``IModelDoc2.InsertProjectedSketch2(Reverse: VT_I4) -> VT_DISPATCH``
    (1-arg, returns the projected sketch feature). The InsertProject*
    /InsertRefCurve candidates the worker probed are not on the typelib.

    Falls back to the 0-arg ``InsertProjectedSketch`` if the 2-form
    misbehaves.
    """
    sketch_name = feature.get("sketch_name") or target.get("sketch_name")
    face_entity = target.get("face") or target.get("face_entity")
    if not sketch_name or face_entity is None:
        return None

    try:
        doc.ClearSelection2(True)
    except Exception as e:
        logger.warning("[B-insert] ClearSelection2 RAISED: %r", e)
        return None

    try:
        sketch_feat = doc.FeatureByName(sketch_name)
    except Exception as e:
        logger.warning("[B-insert] FeatureByName RAISED: %r", e)
        return None
    if sketch_feat is None:
        logger.warning("[B-insert] FeatureByName(%r) -> None", sketch_name)
        return None

    try:
        sk_ok = select_entity(sketch_feat, mark=0)
    except Exception as e:
        logger.warning("[B-insert] select_entity(sketch) RAISED: %r", e)
        return None
    logger.warning("[B-insert] select_entity(sketch) -> %r", sk_ok)
    if not sk_ok:
        return None

    try:
        fc_ok = select_entity(face_entity, append=True, mark=0)
    except Exception as e:
        logger.warning("[B-insert] select_entity(face) RAISED: %r", e)
        return None
    logger.warning("[B-insert] select_entity(face, append=True) -> %r", fc_ok)
    if not fc_ok:
        return None

    reverse = bool(feature.get("reverse", False))
    reverse_int = 1 if reverse else 0

    # First-choice: InsertProjectedSketch2(Reverse:int) -> Dispatch
    try:
        ips2 = doc.InsertProjectedSketch2
        result = ips2(reverse_int) if callable(ips2) else None
        logger.warning(
            "[B-insert] InsertProjectedSketch2(%d) callable=%s -> %r",
            reverse_int, callable(ips2), result,
        )
        if result:
            return result
    except Exception as e:
        logger.warning("[B-insert] InsertProjectedSketch2 RAISED: %r", e)

    # Fallback: 0-arg InsertProjectedSketch (returns void)
    try:
        ips = doc.InsertProjectedSketch
        if callable(ips):
            ips()
            logger.warning("[B-insert] InsertProjectedSketch() called (void)")
            return object()  # sentinel -- verify gate decides real success
        else:
            logger.warning(
                "[B-insert] InsertProjectedSketch resolved as non-callable %r",
                ips,
            )
    except Exception as e:
        logger.warning("[B-insert] InsertProjectedSketch RAISED: %r", e)

    return None


def _try_mode_b_convert(doc: Any, feature: dict, target: dict) -> bool:
    """Mode-B(b): convert-on-face fallback (W60 convert recipe, corrected sig).

    Opens a sketch on the target face, selects the source sketch, and
    calls ``SketchUseEdge3``. The first spike fire crashed
    SketchUseEdge3 with "Invalid number of parameters" -- the gen_py
    wrapper exposes it as ``SketchUseEdge3(IsChain:bool)`` (1-arg, not
    3-arg). Returns ``True`` if the convert pipeline ran without error
    (the verify gate decides final success).
    """
    sketch_name = feature.get("sketch_name") or target.get("sketch_name")
    face_entity = target.get("face") or target.get("face_entity")
    if not sketch_name or face_entity is None:
        return False
    try:
        # Open sketch on the target face.
        doc.ClearSelection2(True)
        if hasattr(face_entity, "Select2"):
            face_entity.Select2(False, 0)
        doc.SketchManager.InsertSketch(True)
        # Select the source sketch.
        source_feat = doc.FeatureByName(sketch_name)
        if source_feat is None:
            doc.SketchManager.InsertSketch(True)
            return False
        source_feat.Select2(False, 0)
        # Convert. Try 1-arg form first (the SW2024 SketchUseEdge3 sig).
        sue3 = doc.SketchManager.SketchUseEdge3
        try:
            sue3(False)  # IsChain=False
            logger.warning("[B-convert] SketchUseEdge3(False) OK")
        except Exception as e1:
            logger.warning("[B-convert] SketchUseEdge3(False) failed: %r", e1)
            try:
                sue3(False, False)
                logger.warning("[B-convert] SketchUseEdge3(False, False) OK")
            except Exception as e2:
                logger.warning("[B-convert] SketchUseEdge3 2-arg failed: %r", e2)
                doc.SketchManager.InsertSketch(True)
                return False
        doc.SketchManager.InsertSketch(True)
        doc.ClearSelection2(True)
        doc.ForceRebuild3(False)
    except Exception as e:
        logger.warning("[B-convert] pipeline RAISED: %r", e)
        return False
    return True


def create_project_curve(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Project a sketch curve onto a face -> 3D reference curve. Fail-closed.

    Mode-A is QUARANTINED (no creation route -- see module docstring);
    the handler fires Mode-B-insert (InsertProjectedSketch2) then
    Mode-B-convert (SketchUseEdge3) in sequence.

    ``feature`` keys
        sketch_name : str  -- name of the source sketch to project
            (e.g. ``"Sketch2"`` from ``fx.seed_line_over_top``)
        reverse     : bool -- reverse projection direction (Mode-B-insert)

    ``target`` keys
        face        : Any  -- a live ``IFace2`` entity for the projection
            target (from ``fx.seed_line_over_top`` or an observe call).
            Aliased as ``face_entity`` for back-compat.
        sketch_name : str  -- alternate location for sketch_name
    """
    if SPIKE_STATUS != "GREEN":
        return False, (
            "project_curve: SEAT-PENDING -- both Mode-A "
            "(CreateDefinition(swFmRefCurve=14) -> QI ref-curve data) and "
            "Mode-B (InsertProjectedSketch2 + convert-on-face fallback) are "
            "awaiting live-seat proof (spike_project_curve)"
        )

    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    sketch_name = feature.get("sketch_name") or target.get("sketch_name")
    if not sketch_name or not isinstance(sketch_name, str):
        return False, "feature must include a non-empty 'sketch_name' string"

    count_before = _count_feature_nodes(doc)

    feat, mode = _try_mode_a(doc, feature), "A"
    if feat is None:
        feat = _try_mode_b_insert(doc, feature, target)
        mode = "B-insert"
    if feat is None:
        converted = _try_mode_b_convert(doc, feature, target)
        mode = "B-convert" if converted else "none"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    count_after = _count_feature_nodes(doc)
    d_nodes = count_after - count_before

    if d_nodes <= 0:
        if mode == "none":
            return False, (
                "project_curve: Mode-A QUARANTINED (no creation enum); Mode-B "
                "(InsertProjectedSketch2 + convert-on-face fallback) failed -- "
                "no ref-curve feature node materialized"
            )
        return False, (
            f"project_curve: mode-{mode} ran but no ref-curve feature node "
            f"materialized (delta_nodes={d_nodes})"
        )

    # CURVE geometric gate (W67 P3b): node-count alone is the W42 ghost trap —
    # the projected curve must carry real arc length (seat-proven 40.0 mm via
    # the RefCurve → IReferenceCurve.GetSegments head).
    new_node = verify.newest_node_by_type(
        doc, _NODE_TYPE_TOKENS, match="substring", limit=_FEATURE_TREE_WALK_LIMIT,
    )
    length_mm = _curve_length_mm(new_node)
    if verify.gate_curve(d_nodes, length_mm):
        return True, f"project_curve created via mode-{mode} (+{d_nodes} node)"
    return False, (
        f"a ref-curve node materialized but carries no readable arc length "
        f"(curve_length_mm={length_mm}) — geometric ghost, not a real curve"
    )


# ---------------------------------------------------------------------------
# Gated self-registration (W0 flips SPIKE_STATUS + adds import in __init__)
# ---------------------------------------------------------------------------

if SPIKE_STATUS == "GREEN":
    from . import HANDLER_REGISTRY

    HANDLER_REGISTRY["project_curve"] = create_project_curve
