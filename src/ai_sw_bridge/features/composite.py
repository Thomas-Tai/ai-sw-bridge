"""W62 — ``composite`` feature-add handler (registry seam).

Composite curve joining a chain of pre-selected edges into one reference curve
via dual-mode creation:

  **Mode-A** (modern): ``CreateDefinition(swFmRefCurve=14)`` →
  ``typed_qi(data, "ICompositeCurveFeatureData")`` →
  ``AccessSelections`` / ``SetEntitiesToJoin`` / ``ReleaseSelectionAccess`` →
  ``CreateFeature(data)``. Fails by ``E_NOINTERFACE`` on the QI (the iface may
  not exist for this SW version) or ``CreateDefinition`` returning None.

  **Mode-B** (legacy): select the edges, then ``doc.InsertCompositeCurve()``
  (no args, returns Boolean). Fails by silent no-op (returns, but no feature
  node materializes).

Verify-the-EFFECT (W21/W42 doctrine): success = a new feature node materialized
in the feature tree (FirstFeature walk; no ΔVol — a composite curve is a
reference curve, not solid geometry). A non-None return, or a return without a
node, is a ghost trap and is NOT reported as success.

The handler MUST try Mode-A first and fall back to Mode-B in the same call; no
feature is declared WALLED until BOTH modes are exhausted on the live seat (W0
fires the spike and adjudicates).
"""

from __future__ import annotations

from typing import Any

from ..com.earlybind import typed_qi
from ..selection.live import select_entity

SPIKE_STATUS = "UNPROVEN"

_SW_FM_REF_CURVE = 14  # swFeatureNameID_e.swFmRefCurve (probe; W0 resolves)


def _count_feature_nodes(doc: Any) -> int:
    """Walk the feature tree and count nodes (re-typing each to IFeature per step).

    The W59 lesson: the walk returns loosely-typed nodes, so we must re-type
    each to ``IFeature`` to access ``.GetNextFeature()`` reliably.
    """
    try:
        feat = doc.FirstFeature()
    except Exception:
        return 0
    count = 0
    while feat is not None:
        count += 1
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    return count


def _try_mode_a(doc: Any, edges: list[Any]) -> Any:
    """Mode-A: CreateDefinition → QI → SetEntitiesToJoin → CreateFeature.

    Returns the created feature on success, None on any failure (E_NOINTERFACE,
    CreateDefinition returning None, setter failure, CreateFeature returning None).
    """
    try:
        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_REF_CURVE)
        if data is None:
            return None
        typed_data = typed_qi(data, "ICompositeCurveFeatureData")
        typed_data.AccessSelections(doc, None)
        typed_data.SetEntitiesToJoin(edges)
        typed_data.ReleaseSelectionAccess()
        feat = fm.CreateFeature(data)
        return feat
    except Exception:
        return None


def _try_mode_b(doc: Any, edges: list[Any]) -> Any:
    """Mode-B: select edges → InsertCompositeCurve (legacy, no args).

    Returns the created feature on success (or a truthy sentinel if the method
    returns Boolean), None on any failure (select failure, method returning
    False/None, or exception).
    """
    try:
        doc.ClearSelection2(True)
        for edge in edges:
            if not select_entity(edge, append=True, mark=0):
                return None
        result = doc.InsertCompositeCurve()
        if result:
            return result  # Boolean True or a feature handle
        return None
    except Exception:
        return None


def create_composite(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Insert a composite curve joining a chain of pre-selected edges. Fail-closed.

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
        return False, "both Mode-A (CreateDefinition/QI) and Mode-B (InsertCompositeCurve) failed"

    doc.ForceRebuild3(False)
    nodes_after = _count_feature_nodes(doc)
    if nodes_after > nodes_before:
        return True, f"composite curve created via Mode-{mode}"

    return False, f"Mode-{mode} returned but no feature node materialized (ghost trap)"
