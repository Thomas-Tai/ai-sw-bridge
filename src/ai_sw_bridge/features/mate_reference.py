"""Mate-reference feature handler (W63 lane 1 — parametric InsertMateReference2).

Designates 1--3 entities on the part as primary / secondary / tertiary
mate-references, consumed by SmartMate when the part is inserted into an
assembly.

Mode-A (QUARANTINE):
    No ``swFmMateReference`` enum is present in the SW2024 swconst harvest.
    The W62 quarantine doctrine bans speculative probing of random enum IDs —
    ``_try_mode_a`` is a no-op stub returning ``None`` until a proven enum
    value comes off the seat.

Mode-B (PRIMARY PATH — parametric, NOT selection-mark):
    ``IFeatureManager.InsertMateReference2`` — a **12-arg** parametric call
    (DLL reflection, ``SolidWorks.Interop.sldworks.dll`` 32.1.0.123,
    2026-06-17). We pass topological ``IEntity`` references directly and
    abandon the brittle ``SelectByID2`` selection-mark routing entirely.

    Authoritative signature (positions 0--11)::

        InsertMateReference2(
            BstrMateReferenceName,        # 0  str
            PrimaryReferenceEntity,       # 1  IEntity
            PrimaryReferenceType,         # 2  int  (swMateReferenceType_e)
            PrimaryReferenceAlignment,    # 3  int  (swMateReferenceAlignment_e)
            PrimaryReferenceAlignAxes,    # 4  bool
            SecondaryReferenceEntity,     # 5  IEntity  (or VARIANT null)
            SecondaryReferenceType,       # 6  int
            SecondaryReferenceAlignment,  # 7  int
            SecondaryReferenceAlignAxes,  # 8  bool
            TertiaryReferenceEntity,      # 9  IEntity  (or VARIANT null)
            TertiaryReferenceType,        # 10 int
            TertiaryReferenceAlignment,   # 11 int
        ) -> IFeature

    NOTE: there is NO ``TertiaryReferenceAlignAxes`` — the AlignAxes bools
    exist only for primary (pos 4) and secondary (pos 8). The CHM/recollection
    13-arg form is a hallucination; the live tlb is 12 args. (Same
    reflect-first discipline that caught com_point's wrong interface.)

    Enum defaults (swconst 32.1.0.123, reflected): ``swMateReferenceType_default
    = 0`` and ``swMateReferenceAlignment_Any = 0`` — so type=0 / align=0 are
    real values, not guesses.

Verify:
    ``GetFeatures(False)`` delta = +1 AND a node whose ``GetTypeName2``
    contains ``"materef"`` (case-insensitive). The exact kernel string is
    NOT trusted (bbox returned ``'BoundingBoxProfileFeat'``, com_point
    ``'CenterOfMassRefPoint'`` — both unlike their guessed names); the spike
    logs the true string via an A7 probe.
"""

from __future__ import annotations

import logging
from typing import Any

from ..com.earlybind import EarlyBindError, typed, typed_qi
from ..com.sw_type_info import wrapper_module
from ..selection import (
    resolve_manifest_face,
    resolve_ref,
)

logger = logging.getLogger(__name__)

SPIKE_STATUS = "GREEN"  # seat-proven: InsertMateReference2 → 'MateReferenceGroupFolder', survives reopen (W63 2026-06-17)

# swMateReferenceType_e / swMateReferenceAlignment_e defaults (reflected).
_REF_TYPE_DEFAULT = 0   # swMateReferenceType_default
_REF_ALIGN_ANY = 0      # swMateReferenceAlignment_Any


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
    """Resolve a ref (manifest-face dict or DurableRef) to a live entity,
    then type it to ``IEntity`` so the [in] Entity arg marshals cleanly."""
    if isinstance(ref, dict):
        res = resolve_manifest_face(doc, ref)
    else:
        res = resolve_ref(doc, ref)
    ent = res.entity if res.entity is not None else None
    if ent is None:
        return None
    # InsertMateReference2's reference args are typed IEntity. Faces/edges
    # QI to IEntity; type the proxy so the marshaler hands the kernel a
    # proper IEntity dispatch (mirrors select_entity's typed(entity, "IEntity")).
    try:
        return typed(ent, "IEntity")
    except EarlyBindError as exc:
        logger.warning("[mate_reference] typed(IEntity) failed, passing raw: %r", exc)
        return ent
    except Exception as exc:
        logger.warning("[mate_reference] typed(IEntity) unexpected, passing raw: %r", exc)
        return ent


def _null_entity() -> Any:
    """Null for an absent [in] IEntity arg.

    SEAT LESSON (W63 mate_reference, 2026-06-17): the
    ``VARIANT(VT_DISPATCH, None)`` trailing-null recipe (edge_flange / hem /
    helix) is for RAW ``InvokeTypes`` / late-bound calls where you set the VT
    yourself. On the makepy EARLY-BOUND typed proxy (what ``typed_qi`` returns),
    a ``VARIANT`` wrapper is not a COM object and conversion fails with
    ``TypeError: The Python instance can not be converted to a COM object``.
    The typed wrapper already knows the arg is ``Entity``; plain Python ``None``
    marshals to a null interface pointer. So: ``None`` here, not a VARIANT.
    """
    return None


def _try_mode_a(doc: Any, feature: dict, target: dict) -> bool | None:
    """Mode-A stub — quarantined (W62 doctrine; no ``swFmMateReference`` enum)."""
    logger.warning("[mate_reference] mode_a: quarantined (no swFmMateReference enum)")
    return None


def _try_mode_b(doc: Any, feature: dict, target: dict) -> bool | None:
    """Mode-B: parametric ``IFeatureManager.InsertMateReference2`` (12 args)."""
    entities = feature.get("entities")
    if not isinstance(entities, list) or not entities:
        logger.warning("[mate_reference] mode_b: no entities in feature spec")
        return None

    # Bucket the resolved entities by role. Primary is mandatory; the rest
    # default to a VARIANT null so the 12-arg signature is always satisfied.
    by_role: dict[str, Any] = {}
    for i, ent_spec in enumerate(entities):
        if not isinstance(ent_spec, dict):
            logger.warning("[mate_reference] mode_b: entity[%d] not a dict, skipping", i)
            continue
        role = ent_spec.get("role", "primary")
        if role not in ("primary", "secondary", "tertiary"):
            logger.warning("[mate_reference] mode_b: unknown role %r, skipping", role)
            continue
        ref = ent_spec.get("ref")
        if ref is None:
            logger.warning("[mate_reference] mode_b: entity[%d] (%s) has no ref", i, role)
            return None
        ent = _resolve_entity_ref(doc, ref)
        if ent is None:
            logger.warning("[mate_reference] mode_b: entity[%d] (%s) unresolved", i, role)
            return None
        by_role[role] = ent

    primary = by_role.get("primary")
    if primary is None:
        logger.warning("[mate_reference] mode_b: no primary entity resolved")
        return None
    secondary = by_role.get("secondary", _null_entity())
    tertiary = by_role.get("tertiary", _null_entity())

    name = feature.get("name") or "Default"

    # FeatureManager arrives as a bare CDispatch out-of-process (com_point
    # round-3 lesson): dispatch via the typed early-bound proxy so the
    # dispid table resolves. typed_qi-first, raw fallback.
    try:
        fm = doc.FeatureManager
    except Exception as exc:
        logger.warning("[mate_reference] mode_b: FeatureManager access failed: %r", exc)
        return None

    fm_typed = None
    try:
        fm_typed = typed_qi(fm, "IFeatureManager", module=wrapper_module())
    except EarlyBindError as exc:
        logger.warning("[mate_reference] mode_b: typed_qi(IFeatureManager) E_NOINTERFACE: %r", exc)
    except Exception as exc:
        logger.warning("[mate_reference] mode_b: typed_qi(IFeatureManager) failed: %r", exc)
    target_fm = fm_typed if fm_typed is not None else fm

    try:
        feat = target_fm.InsertMateReference2(
            name,                 # 0  name
            primary,              # 1  primary entity
            _REF_TYPE_DEFAULT,    # 2  primary type
            _REF_ALIGN_ANY,       # 3  primary alignment
            False,                # 4  primary align-axes
            secondary,            # 5  secondary entity (or null)
            _REF_TYPE_DEFAULT,    # 6  secondary type
            _REF_ALIGN_ANY,       # 7  secondary alignment
            False,                # 8  secondary align-axes
            tertiary,             # 9  tertiary entity (or null)
            _REF_TYPE_DEFAULT,    # 10 tertiary type
            _REF_ALIGN_ANY,       # 11 tertiary alignment
        )
        logger.warning("[mate_reference] mode_b: InsertMateReference2 returned %r", feat)
    except Exception as exc:
        logger.warning("[mate_reference] mode_b: InsertMateReference2 raised %r", exc)
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
                # Widened from exact 'MateReference' to a case-insensitive
                # substring: the kernel's GetTypeName2 is not trusted to match
                # the guessed name (bbox/com_point doctrine).
                if "materef" in tn.lower():
                    return True, f"mode_b (delta {before} -> {after}, type={tn!r})"
            except Exception:
                continue
    return False, f"delta ok ({before} -> {after}) but no MateReference node found"


def create_mate_reference(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Create a mate-reference feature (1--3 entities, role-tagged).

    ``feature`` shape::

        {
            "type": "mate_reference",
            "name": "MateRef-1",
            "entities": [
                {"ref": <edge_ref|face_ref>, "role": "primary"},
                {"ref": <edge_ref|face_ref>, "role": "secondary"}
            ]
        }

    Tries Mode-A (quarantined — always None) then Mode-B (parametric
    InsertMateReference2). Verifies via feature-node delta +
    ``GetTypeName2`` containing ``"materef"``.
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
