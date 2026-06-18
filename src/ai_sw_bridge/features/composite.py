"""W62 — ``composite`` feature-add handler (registry seam).

Composite curve joining a chain of pre-selected edges into one reference curve.

  **Mode-A (QUARANTINED — documented unreachable for CREATION)**: the SW2024
  swconst harvest (docs/sw_api_full.json @ build 32.1.0.123) exposes only two
  curve enums for ``IFeatureManager.CreateDefinition`` (14=swFmRefCurve,
  61=swFmReferenceCurve). On the live seat: id=61 returns None; id=14
  instantiates a generic ref-curve container whose runtime type rejects QI
  for ``ICompositeCurveFeatureData`` with E_NOINTERFACE. The interface IS in
  the typelib but is **edit-only** — accessible via
  ``IFeature.GetDefinition()`` on an EXISTING composite-curve feature, not as
  a creation route. The Mode-A code is retained for record + future workers'
  reference; ``_try_mode_a`` is a no-op stub. Do NOT attempt to un-wall.

  **Mode-B (legacy, the operative path)**: select the edges with the macro-
  recorder's selection mark (``mark=1`` — composite curve's "Edges to join"
  PropertyManager list-box), then ``doc.InsertCompositeCurve()`` (no args,
  returns Boolean). ``InsertCompositeCurve`` resolves as a callable-OR-property
  on the late-bound proxy; the rollback.py idiom handles both.

Verify-the-EFFECT (W21/W42 doctrine): success = a new feature node materialized
in the feature tree (``IFeatureManager.GetFeatures(False)`` array-length delta;
no ΔVol — a composite curve is a reference curve, not solid geometry). A
non-None return, or a return without a node, is a ghost trap and is NOT
reported as success.

Why GetFeatures(False) and not FirstFeature: ``IModelDoc2.FirstFeature`` is
unreachable on the raw late-bound doc (com_error -2147352573 "Member not
found"); the linked-list traversal does not survive the IDispatch boundary.
``IFeatureManager.GetFeatures(False)`` returns a flat tuple that IS reachable
(seat-proven: 25 features on a fresh block).
"""

from __future__ import annotations

import logging
from typing import Any

from ..selection.live import select_entity
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.composite")

SPIKE_STATUS = "GREEN"  # Mode-B fired clean + survived save→reopen on the live seat (W62)

# Verify class (W67): CURVE — witnessed by a feature-node count delta. NOTE
# (Phase-3 finding): this is the W42-ghost-trap-prone family — node presence is
# trusted without a geometric scalar (curve length / edge count). Hardening the
# CURVE witness is W67 Phase 3.
VERIFY_CLASS = verify.FeatureClass.CURVE

# Composite-curve PropertyManager selection mark — the macro-recorder corpus
# uses mark=1 for the "Edges to join" list box. mark=0 (preselection) is
# accepted by select_entity but InsertCompositeCurve returns False silently
# because the selection isn't routed to the list box.
_EDGES_TO_JOIN_MARK = 1


def _resolve(obj: Any, attr: str) -> Any:
    """Late-bound callable-or-property indirection (kept for legacy callers)."""
    v = getattr(obj, attr)
    return v() if callable(v) else v


def _count_feature_nodes(doc: Any) -> int:
    """Flat feature-node count via ``GetFeatures(False)``. Delegates to the W67
    verify substrate (``FirstFeature`` is unreachable out-of-process; the flat
    tuple from ``GetFeatures(False)`` is the W62-canonical substrate)."""
    return verify.feature_node_count(doc)


def _try_mode_a(doc: Any, edges: list[Any]) -> Any:
    """Mode-A: QUARANTINED — documented unreachable for CREATION.

    The SW2024 swconst harvest proves ``ICompositeCurveFeatureData`` has no
    valid ``swFeatureNameID_e`` for ``IFeatureManager.CreateDefinition``:
    only ids 14 and 61 sit in the curve family, and on the live seat
        id=61 -> CreateDefinition returns None
        id=14 -> instantiates a generic ref-curve container; the resulting
                 object's runtime type rejects QI for
                 ICompositeCurveFeatureData with E_NOINTERFACE.
    The interface IS in the typelib but is exposed only via
    ``IFeature.GetDefinition()`` on an EXISTING composite-curve feature
    (post-hoc editing). No creation route exists. Returning None here
    routes the handler to Mode-B without spending a CreateDefinition call
    every invocation.

    Historical implementation (probe loop over (61, 14), VARIANT(VT_DISPATCH,
    None) for the Component2 arg, SetEntitiesToJoin SAFEARRAY marshaling)
    can be reconstructed from git history at composite.py @ 14ea3ef..HEAD~1
    if a future SW version exposes a creation enum.
    """
    return None


def _try_mode_b(doc: Any, edges: list[Any]) -> Any:
    """Mode-B: select edges (mark=1) → InsertCompositeCurve (no-arg method on IModelDoc2).

    Returns the created feature on success (or a truthy sentinel —
    InsertCompositeCurve returns Boolean True on success), None on any failure.

    Selection mark: composite curve's PropertyManager uses the "Edges to join"
    list box, which the macro-recorder routes via ``mark=1``. ``mark=0``
    (preselection) is accepted by select_entity but the Insert macro returns
    False silently because the selection isn't routed to the list box.

    InsertCompositeCurve resolves to a late-bound bool on the raw IDispatch
    proxy (same trap class as FirstFeature, RevisionNumber, GetEdges) — calling
    it with ``()`` then raises TypeError("'bool' object is not callable")
    because win32com already auto-invoked the dispid as a property. The
    callable-or-property guard (the rollback.py idiom) handles both
    resolutions.
    """
    try:
        doc.ClearSelection2(True)
    except Exception as e:
        logger.warning("[B] ClearSelection2 RAISED: %r", e)
        return None

    for i, edge in enumerate(edges):
        try:
            ok = select_entity(edge, append=True, mark=_EDGES_TO_JOIN_MARK)
        except Exception as e:
            logger.warning("[B] select_entity edge[%d] RAISED: %r", i, e)
            return None
        logger.warning(
            "[B] select_entity edge[%d] (append=True, mark=%d) -> %r",
            i, _EDGES_TO_JOIN_MARK, ok,
        )
        if not ok:
            return None

    try:
        ic = doc.InsertCompositeCurve
        result = ic() if callable(ic) else ic
    except Exception as e:
        logger.warning("[B] InsertCompositeCurve invocation RAISED: %r", e)
        return None
    logger.warning(
        "[B] InsertCompositeCurve (callable=%s) -> %r", callable(ic), result
    )
    if result:
        return result
    return None


def create_composite(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Insert a composite curve joining a chain of pre-selected edges. Fail-closed.

    Mode-A is QUARANTINED (documented unreachable for creation — see module
    docstring); the handler still calls ``_try_mode_a`` for the registry-level
    contract but it returns None immediately. Mode-B is the operative path.

    ``feature`` keys
        (none — the composite curve takes no parameters beyond the edge chain)

    ``target`` keys
        edges : list[Any]  — a list of live edge entities to join (the fixture
            supplies a connected edge chain on the block).
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    edges = target.get("edges")
    if not isinstance(edges, list) or not edges:
        return False, "target must contain a non-empty 'edges' list"

    nodes_before = _count_feature_nodes(doc)

    feat = _try_mode_a(doc, edges)
    mode = "A"
    if feat is None:
        feat = _try_mode_b(doc, edges)
        mode = "B"
    if feat is None:
        return False, (
            "Mode-A is documented unreachable (no creation enum); Mode-B "
            "(InsertCompositeCurve with mark=1 selection) failed"
        )

    doc.ForceRebuild3(False)
    nodes_after = _count_feature_nodes(doc)
    if nodes_after > nodes_before:
        return True, f"composite curve created via Mode-{mode}"

    return False, f"Mode-{mode} returned but no feature node materialized (ghost trap)"
