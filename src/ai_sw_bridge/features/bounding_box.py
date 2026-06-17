"""Global bounding-box reference-feature handler (W63 lane 2 — ``bounding_box``).

Inserts a global bounding-box feature via ``CreateDefinition(swFmBoundingBox)``
(Mode-A, primary path) or ``InsertGlobalBoundingBox`` (Mode-B, fallback).
No pre-selection required — the box is auto-fitted over the solid body.

Mode-A status: PRIMARY PATH
----------------------------
``swFmBoundingBox`` (enum value 114) is named in the ``CreateDefinition``
doc-string, making this the rare curves/refgeom-adjacent lane where a
creation enum genuinely exists — the first W63 candidate to break the W62
quarantine streak.

``CreateDefinition(114)`` returns an ``IFeatureData`` that should
``QueryInterface`` to ``IBoundingBoxFeatureData``.  If QI succeeds, set the
box properties and call ``CreateFeature(data)``.  If any step fails
(``None`` from ``CreateDefinition``, ``E_NOINTERFACE`` on the QI, or
``CreateFeature`` not materializing), fall through to Mode-B.

Mode-B: legacy ``IFeatureManager.InsertGlobalBoundingBox``
-----------------------------------------------------------
``InsertGlobalBoundingBox(BBoxType, IncludeHiddenBodies,
IncludeSurfaceBodies, [out] Status)`` — 3 input args + 1 ``[out]``.
Under late binding the ``[out]`` param may not marshal; under early binding
it arrives as a trailing tuple element.  The callable-or-property guard is
mandatory: win32com late-binding may resolve the method as a property.

Verify-the-EFFECT
-----------------
``_count_feature_nodes(doc)`` delta = +1 AND a node whose ``GetTypeName2``
returns ``"BoundingBoxFolder"`` or ``"BoundingBox"`` materializes.
"""

from __future__ import annotations

import logging
from typing import Any

from ..com.earlybind import EarlyBindError, typed_qi
from ..com.sw_type_info import wrapper_module

logger = logging.getLogger(__name__)

SPIKE_STATUS = "UNFIRED"

# swFeatureNameID_e::swFmBoundingBox
_SW_FM_BOUNDING_BOX = 114


def _count_feature_nodes(doc: Any) -> int:
    """Flat feature-node count via ``GetFeatures(False)`` (W62 substrate).

    ``GetFeatures(False)`` returns individual nodes (not folders); this is the
    W62-canonical verify substrate — do NOT substitute ``GetFeatures(True)``
    or ``GetFeatureCount()``.
    """
    try:
        feats = doc.FeatureManager.GetFeatures(False)
        return len(feats) if feats else 0
    except Exception as exc:
        logger.warning("[bounding_box] count_feature_nodes failed: %r", exc)
        return 0


def _get_type_name(node: Any) -> str | None:
    """Callable-or-property-guarded ``GetTypeName2`` / ``GetTypeName`` access.

    Uses the VERBATIM §0 guard pattern: win32com IDispatch may resolve
    ``GetTypeName*`` as a property and auto-invoke on attribute access.
    """
    for attr_name in ("GetTypeName2", "GetTypeName"):
        try:
            _v = getattr(node, attr_name)
            _result = _v() if callable(_v) else _v
            return str(_result)
        except Exception as exc:
            logger.warning("[bounding_box] %s access failed: %r", attr_name, exc)
            continue
    return None


def _find_bbox_node(doc: Any) -> Any | None:
    """Walk feature nodes looking for a BoundingBox-typed node."""
    try:
        feats = doc.FeatureManager.GetFeatures(False)
    except Exception as exc:
        logger.warning("[bounding_box] find_bbox_node GetFeatures failed: %r", exc)
        return None
    if not feats:
        return None
    for node in feats:
        tname = _get_type_name(node)
        if tname in ("BoundingBoxFolder", "BoundingBox"):
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

    # Set properties
    try:
        bd.IncludeHiddenBodies = False
        bd.IncludeSurfaces = False
    except Exception as exc:
        logger.warning("[bounding_box] mode_a property-set failed: %r", exc)

    # AccessSelections (required by the iface per CHM)
    try:
        bd.AccessSelections(doc, None)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a AccessSelections failed: %r", exc)

    # CreateFeature
    try:
        feat = fm.CreateFeature(bd)
    except Exception as exc:
        logger.warning("[bounding_box] mode_a CreateFeature raised: %r", exc)
        return False, f"CreateFeature raised: {exc!r}"

    # ReleaseSelectionAccess (cleanup regardless of outcome)
    try:
        bd.ReleaseSelectionAccess()
    except Exception as exc:
        logger.warning("[bounding_box] mode_a ReleaseSelectionAccess failed: %r", exc)

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

    bbox_node = _find_bbox_node(doc)
    if bbox_node is None:
        logger.warning("[bounding_box] mode_a: node added but no BoundingBox-typed node found")
        return False, "feature node added but no BoundingBox/BoundingBoxFolder node found"

    logger.warning("[bounding_box] mode_a: BoundingBox node materialized")
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

    try:
        _result = _v(bbox_type, False, False) if callable(_v) else _v
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
