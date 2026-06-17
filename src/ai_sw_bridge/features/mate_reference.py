"""Mate-reference feature handler (W63 lane 1 — Mode-A quarantine + Mode-B multi-mark).

Designates 1--3 entities on the part as primary / secondary / tertiary
mate-references, consumed by SmartMate when the part is inserted into an
assembly.

Mode-A (QUARANTINE):
    No ``swFmMateReference`` enum is present in the SW2024 swconst harvest
    (``docs/sw_api_full.json``). The W62 quarantine doctrine bans speculative
    probing of random enum IDs — ``_try_mode_a`` is a no-op stub returning
    ``None`` until W0 provides a proven enum value from the seat.

Mode-B (PRIMARY PATH):
    ``IModelDoc2.InsertMateReference()`` on pre-selected entities with
    role-specific marks (primary=1, secondary=2, tertiary=4). The callable-
    or-property guard is applied because late-bound IDispatch may auto-invoke
    the zero-arg method as a property on ``getattr``.

Verify:
    ``GetFeatures(False)`` delta = +1 AND a node whose ``GetTypeName2``
    (callable-or-property-guarded) returns ``"MateReference"``.
"""

from __future__ import annotations

import logging
from typing import Any

from ..selection import (
    resolve_manifest_face,
    resolve_ref,
    select_entity,
)

logger = logging.getLogger(__name__)

SPIKE_STATUS = "UNFIRED"

_MARK_FOR_ROLE: dict[str, int] = {
    "primary": 1,
    "secondary": 2,
    "tertiary": 4,
}


def _count_feature_nodes(doc: Any) -> int:
    feats = doc.FeatureManager.GetFeatures(False)
    return len(feats) if feats else 0


def _type_name_of(node: Any) -> str:
    for attr in ("GetTypeName2", "GetTypeName"):
        try:
            _v = getattr(node, attr)
            return str(_v() if callable(_v) else _v)
        except Exception:
            continue
    return ""


def _resolve_entity_ref(doc: Any, ref: Any) -> Any:
    if isinstance(ref, dict):
        res = resolve_manifest_face(doc, ref)
    else:
        res = resolve_ref(doc, ref)
    return res.entity if res.entity is not None else None


def _try_mode_a(doc: Any, feature: dict, target: dict) -> bool | None:
    """Mode-A stub — quarantined (W62 doctrine).

    No ``swFmMateReference`` enum exists in the SW2024 swconst harvest.
    The W62 quarantine pattern bans speculative probing of random enum IDs.
    Returns ``None`` (not attempted) unconditionally. When W0 provides a
    proven enum value from the seat, this stub is replaced with the real
    ``CreateDefinition → typed_qi → CreateFeature`` path.
    """
    logger.warning("[mate_reference] mode_a: quarantined (no swFmMateReference enum)")
    return None


def _try_mode_b(doc: Any, feature: dict, target: dict) -> bool | None:
    """Mode-B: legacy ``InsertMateReference()`` on multi-mark pre-selected entities."""
    entities = feature.get("entities")
    if not isinstance(entities, list) or not entities:
        logger.warning("[mate_reference] mode_b: no entities in feature spec")
        return None

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    selected = 0
    for i, ent_spec in enumerate(entities):
        if not isinstance(ent_spec, dict):
            logger.warning("[mate_reference] mode_b: entity[%d] not a dict, skipping", i)
            continue
        role = ent_spec.get("role", "primary")
        mark = _MARK_FOR_ROLE.get(role)
        if mark is None:
            logger.warning("[mate_reference] mode_b: unknown role %r, skipping", role)
            continue
        ref = ent_spec.get("ref")
        if ref is None:
            logger.warning("[mate_reference] mode_b: entity[%d] has no ref", i)
            return None
        entity = _resolve_entity_ref(doc, ref)
        if entity is None:
            logger.warning("[mate_reference] mode_b: entity[%d] (%s) unresolved", i, role)
            return None
        if not select_entity(entity, append=(selected > 0), mark=mark):
            logger.warning("[mate_reference] mode_b: select_entity failed for %s", role)
            return None
        selected += 1

    if selected == 0:
        logger.warning("[mate_reference] mode_b: no entities selected")
        return None

    try:
        _insert = getattr(doc, "InsertMateReference")
        _result = _insert() if callable(_insert) else _insert
    except Exception as exc:
        logger.warning("[mate_reference] mode_b: InsertMateReference raised %r", exc)
        return None

    try:
        doc.ForceRebuild3(False)
    except Exception as exc:
        logger.warning("[mate_reference] mode_b: ForceRebuild3 raised %r", exc)
    return True


def _verify(doc: Any, before: int) -> tuple[bool, str]:
    after = _count_feature_nodes(doc)
    if after <= before:
        return False, f"no feature-node delta ({before} -> {after})"

    feats = doc.FeatureManager.GetFeatures(False)
    if feats:
        for node in feats:
            try:
                tn = _type_name_of(node)
                if tn == "MateReference":
                    return True, f"mode_b (delta {before} -> {after})"
            except Exception:
                continue
    return False, f"delta ok ({before} -> {after}) but no MateReference node found"


def create_mate_reference(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a mate-reference feature (1--3 entities, role-marked).

    ``feature`` shape::

        {
            "type": "mate_reference",
            "name": "MateRef-1",
            "entities": [
                {"ref": <edge_ref|face_ref>, "role": "primary"},
                {"ref": <edge_ref|face_ref>, "role": "secondary"}
            ]
        }

    Tries Mode-A (quarantined — always None) then Mode-B.
    Verifies via feature-node delta + ``GetTypeName2 == "MateReference"``.
    """
    try:
        return _create_mate_reference_inner(doc, feature, target)
    except Exception as exc:
        logger.warning("[mate_reference] unexpected exception: %r", exc)
        return False, f"mate_reference unexpected error: {exc!r}"


def _create_mate_reference_inner(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    before = _count_feature_nodes(doc)

    result_a = _try_mode_a(doc, feature, target)
    if result_a is True:
        ok, note = _verify(doc, before)
        if ok:
            return True, f"mode_a ({note})"
        logger.warning("[mate_reference] mode_a reported success but verify failed: %s", note)

    result_b = _try_mode_b(doc, feature, target)
    if result_b is None:
        return False, "mate_reference: all modes failed"

    ok, note = _verify(doc, before)
    if ok:
        return True, note
    return False, f"mate_reference verify failed: {note}"
