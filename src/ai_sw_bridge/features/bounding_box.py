"""Global bounding-box reference-feature handler (W63 lane 2 — ``bounding_box``).

Mode-A is the SHIPPED path: ``CreateDefinition(swFmBoundingBox=114)`` →
``typed_qi(IBoundingBoxFeatureData)`` → ``AccessSelections`` →
``PlanarEntity = <Front Plane>`` → ``ReleaseSelectionAccess`` →
``CreateFeature(bd)``. This is the W62-quarantine-breaking lane — the
first feature where a CreateDefinition enum AND the specialized QI
genuinely materialize a non-interactive feature via the FeatureData route.

Seat-discovered facts (SW2024 v32.1, 2026-06-17 spike, 5 rounds of
forensic iteration) that contradict the CHM:

1. **No ``BBoxType`` property** on ``IBoundingBoxFeatureData``. The CHM-
   documented enum-based "axis-aligned vs best-fit" toggle does not
   exist on this build. The kernel picks the alignment from WHICH planar
   reference you supply.
2. **``PlanarEntity`` (not ``ReferenceFaceOrPlane``) is the writable
   setter.** ``ReferenceFaceOrPlane`` raises ``DISP_E_TYPEMISMATCH`` on
   an ``IFeature`` argument; ``PlanarEntity`` accepts the same value.
3. **``AccessSelections``/``ReleaseSelectionAccess`` ARE required** —
   the FeatureData must be opened for editing before reference setters
   bind. (CHM tools advice was correct; an earlier intermediate patch
   that dropped these calls was a self-inflicted regression.)
4. **``GetTypeName2`` returns ``'BoundingBoxProfileFeat'``** — not the
   CHM/UI strings ``'BoundingBox'`` or ``'BoundingBoxFolder'``. The
   verifier matches via case-insensitive substring on ``'bound'`` /
   ``'bbox'`` so it survives further naming drift.
5. **The bbox feature is NOT inserted at the tail of GetFeatures(False).**
   Its +2 visible delta in the depth-first walk is two SUB-children
   (``DirectionLight``, ``RefPlane``); the actual bbox node is inserted
   earlier in the tree. Verify by walking the full feature list, not
   ``feats[before:]``.

Mode-B: legacy ``IFeatureManager.InsertGlobalBoundingBox``
-----------------------------------------------------------
CHM signature: ``InsertGlobalBoundingBox(BBoxType, IncludeHiddenBodies,
IncludeSurfaceBodies, [out] Status)``. Live v32.1 dispid raises
``DISP_E_PARAMNOTOPTIONAL`` on 3-arg, ``DISP_E_TYPEMISMATCH`` on 4-arg
with a raw int placeholder for ``[out] Status`` — the classic
``[out]``-param marshaling wall (see [[reference_makepy_wrong_argtype]]).
Walled on this build; kept as a fallback stub but Mode-A is sufficient.

Verify-the-EFFECT
-----------------
``CreateFeature`` returns a real ``IFeature`` whose ``GetTypeName2``
contains ``'bound'`` / ``'bbox'``, ``_count_feature_nodes`` delta ≥ 1,
and ``_find_bbox_node`` matches after ``ForceRebuild3``. Spike validates
survival across save → reopen.
"""

from __future__ import annotations

import logging
from typing import Any

from ..com.earlybind import EarlyBindError, typed_qi
from ..com.sw_type_info import wrapper_module
from . import verify

logger = logging.getLogger(__name__)

SPIKE_STATUS = "GREEN"  # W63 round-5 seat-proven 2026-06-17 (PlanarEntity setter, BoundingBoxProfileFeat node, survives save->reopen)

# Verify class (W67): REF_NODE — node count delta + type-name corroboration.
VERIFY_CLASS = verify.FeatureClass.REF_NODE

# swFeatureNameID_e::swFmBoundingBox
_SW_FM_BOUNDING_BOX = 114


def _count_feature_nodes(doc: Any) -> int:
    """Flat feature-node count via ``GetFeatures(False)``. Delegates to the W67
    verify substrate (the W62-canonical substrate — not ``GetFeatures(True)``
    or ``GetFeatureCount()``)."""
    return verify.feature_node_count(doc)


def _get_type_name(node: Any) -> str | None:
    """Callable-or-property-guarded ``GetTypeName2`` / ``GetTypeName`` access.
    Delegates to the W67 verify substrate."""
    return verify.type_name(node)


def _find_bbox_node(doc: Any) -> Any | None:
    """Walk feature nodes looking for a BoundingBox-typed node.

    W63 round-5 doctrine update: CHM-named identifiers
    ('BoundingBoxFolder' / 'BoundingBox') were UI/CHM hallucinations;
    SW2024 v32.1 kernel exposes its own GetTypeName2 strings (harvested
    via the A7 probe in `_try_mode_a`). Match via case-insensitive
    substring on 'bound' or 'bbox' so we catch the real kernel names
    (e.g., 'BoundingBoxFolder', 'GlobalBoundingBox', 'BodyBoundingBox')
    without binding the verifier to one specific casing.
    """
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception as exc:
        logger.warning("[bounding_box] find_bbox_node GetFeatures failed: %r", exc)
        return None
    if not feats:
        return None
    for node in feats:
        tname = _get_type_name(node)
        if not tname:
            continue
        lower = tname.lower()
        if "bound" in lower or "bbox" in lower:
            return node
    return None


def _try_mode_a(
    doc: Any, best_fit: bool
) -> tuple[bool, str | None]:
    """Mode-A: ``CreateDefinition(swFmBoundingBox)`` → ``IBoundingBoxFeatureData``
    → ``CreateFeature(data)``.

    Returns ``(True, "mode_a")`` on verified materialization, ``(False, reason)``
    on any failure.  Never raises.
    """
    logger.warning("[bounding_box] mode_a: attempting CreateDefinition(%d)", _SW_FM_BOUNDING_BOX)
    before = _count_feature_nodes(doc)

    try:
        fm = doc.FeatureManager
    except Exception as exc:
        logger.warning("[bounding_box] mode_a: FeatureManager access failed: %r", exc)
        return False, f"FeatureManager unavailable: {exc!r}"

    # CreateDefinition
    try:
        data = fm.CreateDefinition(_SW_FM_BOUNDING_BOX)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a CreateDefinition raised: %r", exc)
        return False, f"CreateDefinition raised: {exc!r}"

    if data is None:
        logger.warning("[bounding_box] mode_a: CreateDefinition returned None")
        return False, "CreateDefinition(swFmBoundingBox) returned None"

    # typed_qi — IBoundingBoxFeatureData
    try:
        mod = wrapper_module()
        bd = typed_qi(data, "IBoundingBoxFeatureData", module=mod)
    except EarlyBindError as exc:
        logger.warning("[bounding_box] mode_a typed_qi E_NOINTERFACE: %r", exc)
        return False, f"IBoundingBoxFeatureData QI failed: {exc!r}"
    except Exception as exc:
        logger.warning("[bounding_box] mode_a typed_qi unexpected error: %r", exc)
        return False, f"typed_qi failed: {exc!r}"

    # A3 reflection probe (W63 round-3) — kept for telemetry provenance.
    # The round-3 fire surfaced the actual property set: AccessSelections,
    # IncludeEnvelopeComponents, IncludeHiddenBodies, IncludeHiddenComponents,
    # IncludeSurfaces, PlanarEntity, ReferenceFaceOrPlane, ReleaseSelectionAccess.
    # No BBoxType / Type / BoundingBoxType — the CHM is wrong for SW2024 v32.1.
    try:
        _attrs = sorted([a for a in dir(bd) if not a.startswith("_")])
        logger.warning("[bounding_box] mode_a A3 probe — proxy attrs: %r", _attrs)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a A3 probe failed: %r", exc)

    # A5/A6 (W63 round-4): the bbox is NOT a global/auto-fit feature — it
    # requires a planar reference entity (PlanarEntity / ReferenceFaceOrPlane).
    # Sequence per macro pattern: AccessSelections → hydrate properties INSIDE
    # the selection scope → ReleaseSelectionAccess → CreateFeature.
    # The `best_fit` param is no longer meaningful for Mode-A here (no enum
    # toggle in this iface) — best-fit-vs-axis-aligned is a function of WHICH
    # plane/face you supply as the reference (a body face → best-fit-to-body;
    # a principal plane → axis-aligned-to-that-plane).
    plane = None
    try:
        plane = doc.FeatureByName("Front Plane")
    except Exception as exc:
        logger.warning("[bounding_box] mode_a Front Plane lookup raised: %r", exc)
    if plane is None:
        logger.warning("[bounding_box] mode_a Front Plane not resolvable via FeatureByName")

    # AccessSelections — open the FeatureData for editing (round-2 A2 dropped
    # this in error; round-3 reflection confirmed the iface DOES expose it).
    access_ok = False
    try:
        access_ret = bd.AccessSelections(doc, None)
        access_ok = True
        logger.warning("[bounding_box] mode_a AccessSelections returned %r", access_ret)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a AccessSelections failed: %r", exc)

    # A4 isolated setters (Include* known-valid attrs from A3 reflection).
    try:
        bd.IncludeHiddenBodies = False
    except Exception as exc:
        logger.warning("[bounding_box] mode_a IncludeHiddenBodies setter failed: %r", exc)

    try:
        bd.IncludeSurfaces = False
    except Exception as exc:
        logger.warning("[bounding_box] mode_a IncludeSurfaces setter failed: %r", exc)

    # A5 strike: ReferenceFaceOrPlane is the likely primary setter for the
    # geometric reference. A6 fallback: PlanarEntity if A5 throws / no-ops.
    ref_setter = None
    if plane is not None:
        try:
            bd.ReferenceFaceOrPlane = plane
            ref_setter = "ReferenceFaceOrPlane"
            logger.warning("[bounding_box] mode_a A5 ReferenceFaceOrPlane = <Front Plane> OK")
        except Exception as exc:
            logger.warning("[bounding_box] mode_a A5 ReferenceFaceOrPlane setter failed: %r", exc)
        if ref_setter is None:
            try:
                bd.PlanarEntity = plane
                ref_setter = "PlanarEntity"
                logger.warning("[bounding_box] mode_a A6 PlanarEntity = <Front Plane> OK")
            except Exception as exc:
                logger.warning("[bounding_box] mode_a A6 PlanarEntity setter failed: %r", exc)
    logger.warning("[bounding_box] mode_a planar reference setter outcome: %s", ref_setter or "NONE")

    # ReleaseSelectionAccess — commit edits before CreateFeature.
    if access_ok:
        try:
            bd.ReleaseSelectionAccess()
            logger.warning("[bounding_box] mode_a ReleaseSelectionAccess OK")
        except Exception as exc:
            logger.warning("[bounding_box] mode_a ReleaseSelectionAccess failed: %r", exc)

    # CreateFeature
    try:
        feat = fm.CreateFeature(bd)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a CreateFeature raised: %r", exc)
        return False, f"CreateFeature raised: {exc!r}"

    # Verify materialization
    if feat is None or isinstance(feat, int):
        logger.warning("[bounding_box] mode_a: CreateFeature did not materialize (feat=%r)", feat)
        return False, "CreateFeature did not materialize"

    try:
        doc.ForceRebuild3(False)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a ForceRebuild3 failed: %r", exc)

    after = _count_feature_nodes(doc)
    delta = after - before
    logger.warning("[bounding_box] mode_a: node count %d -> %d (delta %d)", before, after, delta)

    if delta < 1:
        logger.warning("[bounding_box] mode_a: no feature node added (ghost)")
        return False, f"bounding_box did not add a feature node (count {before} -> {after})"

    # A7 probe (W63 round-5) — log kernel's authoritative type names. The
    # worker brief assumed GetTypeName2 returns 'BoundingBox' or
    # 'BoundingBoxFolder' (CHM/UI strings); v32.1's actual identifiers may
    # differ. The CreateFeature IFeature is the source-of-truth; record
    # what it identifies as plus the type names of all newly-added nodes
    # for doctrine provenance.
    try:
        feat_tname = _get_type_name(feat)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a A7 probe (feat) raised: %r", exc)
        feat_tname = None
    logger.warning("[bounding_box] mode_a A7 probe — feat.GetTypeName2 = %r", feat_tname)

    try:
        _all_feats = doc.FeatureManager.GetFeatures(False) or []
        _new_feats = list(_all_feats[before:])
        _new_tnames = [_get_type_name(f) for f in _new_feats]
        logger.warning("[bounding_box] mode_a A7 probe — new top-level node type names: %r", _new_tnames)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a A7 probe (GetFeatures) raised: %r", exc)

    bbox_node = _find_bbox_node(doc)
    if bbox_node is None:
        logger.warning("[bounding_box] mode_a: node added but no BoundingBox-typed node found")
        return False, "feature node added but no BoundingBox-typed node found in tree"

    logger.warning("[bounding_box] mode_a: BoundingBox node materialized (type=%r)", _get_type_name(bbox_node))
    return True, "mode_a"


def _try_mode_b(
    doc: Any, best_fit: bool
) -> tuple[bool, str | None]:
    """Mode-B: ``IFeatureManager.InsertGlobalBoundingBox`` — legacy entry.

    Signature (from CHM):
        ``InsertGlobalBoundingBox(BBoxType, IncludeHiddenBodies,
        IncludeSurfaceBodies, [out] Status) -> Object``

    The ``[out] Status`` param may not marshal under late binding; the return
    value may be the feature object alone or a tuple.  The callable-or-property
    guard is applied.  If the method does not exist on the typelib this is a
    no-op stub (W0 discovers the actual entry point on the seat).
    """
    logger.warning("[bounding_box] mode_b: attempting InsertGlobalBoundingBox")
    before = _count_feature_nodes(doc)

    try:
        fm = doc.FeatureManager
    except Exception as exc:
        logger.warning("[bounding_box] mode_b: FeatureManager access failed: %r", exc)
        return False, f"FeatureManager unavailable: {exc!r}"

    # VERBATIM callable-or-property guard (§0): getattr first, then callable check.
    # If InsertGlobalBoundingBox is absent from the typelib, getattr raises
    # AttributeError — caught here (no-op stub per the brief).
    try:
        _v = getattr(fm, "InsertGlobalBoundingBox")
    except AttributeError:
        logger.warning("[bounding_box] mode_b: InsertGlobalBoundingBox not on typelib (no-op stub)")
        return False, "InsertGlobalBoundingBox not available on typelib"

    # BBoxType: 0 = axis-aligned (block), 1 = best-fit
    bbox_type = 1 if best_fit else 0

    # B1 patch (W63 post-mortem): CHM signature is 3 inputs + 1 [out] Status,
    # but the live SW2024 dispid raised DISP_E_PARAMNOTOPTIONAL on the 3-arg
    # call. Late-binding treats the [out] slot as required input — pass a
    # placeholder. See [[reference_makepy_wrong_argtype]] for the [out]-param
    # marshaling family.
    try:
        _result = (
            _v(bbox_type, False, False, 0) if callable(_v) else _v
        )
    except Exception as exc:
        logger.warning("[bounding_box] mode_b InsertGlobalBoundingBox raised: %r", exc)
        return False, f"InsertGlobalBoundingBox raised: {exc!r}"

    # Under early binding the [out] Status may arrive as a trailing tuple
    # element; extract the feature object if so.
    feat = _result
    if isinstance(_result, tuple) and len(_result) >= 1:
        feat = _result[0]

    try:
        doc.ForceRebuild3(False)
    except Exception as exc:
        logger.warning("[bounding_box] mode_b ForceRebuild3 failed: %r", exc)

    after = _count_feature_nodes(doc)
    delta = after - before
    logger.warning("[bounding_box] mode_b: node count %d -> %d (delta %d)", before, after, delta)

    if delta < 1:
        logger.warning("[bounding_box] mode_b: no feature node added (ghost)")
        return False, f"bounding_box did not add a feature node (count {before} -> {after})"

    bbox_node = _find_bbox_node(doc)
    if bbox_node is None:
        logger.warning("[bounding_box] mode_b: node added but no BoundingBox-typed node found")
        return False, "feature node added but no BoundingBox/BoundingBoxFolder node found"

    logger.warning("[bounding_box] mode_b: BoundingBox node materialized")
    return True, "mode_b"


def create_bounding_box(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Insert a global bounding-box reference feature on the part.

    ``feature`` spec shape::

        {"kind": "bounding_box", "name": "BBox-1", "best_fit": false}

    ``target`` is unused (global bounding box auto-fits the solid body).

    Returns ``(True, "<mode>")`` on verified materialization, or
    ``(False, "<reason>")`` on any failure — never raises.
    """
    best_fit = bool(feature.get("best_fit", False))

    # Mode-A first (the doctrine-asymmetry lane: first non-quarantined Mode-A
    # in the curves/refgeom adjacency).
    ok, note = _try_mode_a(doc, best_fit)
    if ok:
        return True, note

    mode_a_reason = note
    logger.warning("[bounding_box] mode_a failed (%s), falling through to mode_b", mode_a_reason)

    # Mode-B fallback
    ok, note = _try_mode_b(doc, best_fit)
    if ok:
        return True, note

    mode_b_reason = note
    return False, f"both modes failed — mode_a: {mode_a_reason}; mode_b: {mode_b_reason}"
