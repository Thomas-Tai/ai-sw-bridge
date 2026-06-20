"""W68 — ``face fillet`` / ``full-round fillet`` feature-add handler (registry seam).

Two fillet sub-types that share the proven constant-fillet
``CreateDefinition → typed_qi(ISimpleFilletFeatureData2) → Initialize →
CreateFeature`` pipeline, but branch on ``FilletType`` (the handler's delta
vs. the shipped constant-radius edge fillet in ``mutate._create_fillet``):

    face        swFaceFillet = 2       2 face-sets (mark 1 / mark 2)
    full_round  swFullRoundFillet = 3  3 face-sets (mark 3 / 4 / 5)

**Reflected sigs** (docs/sw_api_full.md, SW2024 v32.1 — REAL, do not guess):

    ISimpleFilletFeatureData2.Initialize(Int32 FilletType) -> Boolean
    ISimpleFilletFeatureData2.SetFaces(Int32 WhichFaceList, Object FaceList) -> Void
    ISimpleFilletFeatureData2.DefaultRadius  : Double   (prop, metres)
    ISimpleFilletFeatureData2.Type           : Int32    (prop, read after Initialize)

    swSimpleFilletType_e:       swFaceFillet=2, swFullRoundFillet=3
    swSimpleFilletWhichFaces_e: swFaceFilletSet1=1, swFaceFilletSet2=2,
                                swFullRoundFilletSet1=3, swFullRoundFilletCenterSet=4,
                                swFullRoundFilletSet2=5

**Selection (mark routing — mirror mutate._create_linear_pattern):** each face
is resolved via the durable ``resolve_manifest_face`` path (persist→fingerprint
hierarchy), then selected via ``select_entity(entity, append=i>0, mark=<mark>)``.
``select_entity`` routes through a typed ``IEntity.Select2(Append, Mark)`` —
the proven post-resolve selection step (S-EARLYBIND) — so the mark is bound
to the selection at select-time; a post-hoc ``SelectionManager.SetSelectedObjectMark``
hop is not needed (the linear-pattern ``SetSelectedObjectMark`` path is for
``SelectByID`` which cannot carry a mark in the legacy 5-arg form).

**RESIDUAL UNKNOWN (W0 closes on the seat):** whether the mark-bound
selection ALONE drives the face-set assignment in ``CreateFeature``, or whether
``SetFaces(WhichFaceList, FaceList)`` must be called on the FeatureData to
commit the face sets explicitly.  The handler wires mark-bound selection as
the PRIMARY path; a diagnostic ``SetFaces`` probe is included in the spike
so W0 can flip the flag if the seat rejects the marks-only path.  The brief
explicitly calls this out as the "face-set setter members" unknown.

**Verify-the-EFFECT (VOLUME CHANGE, not face delta):** a fillet REDISTRIBUTES
material — it rounds a sharp edge (face fillet) or consumes a center face
into a tangent blend (full-round).  The face delta is UNRELIABLE: a full-
round fillet can leave ``d_faces ≤ 0`` even on a successful materialization
(the center face is consumed, replaced by the blend).  The robust witness is
VOLUME CHANGE — a real fillet moves material, even if only microscopically:

    PASS iff  |d_vol| > verify.VOL_EPS_MM3

Using ``verify.gate_additive_solid`` (which requires ``d_faces > 0``) would
FALSE-FAIL a successful full-round — the exact inverse of the W65 sketched_bend
trap (there the fold gate required volume change; here the additive gate
would require face delta).  ``d_faces`` is logged as corroboration only.

A CreateFeature returning non-None is NOT success — that is the W21/W42
ghost trap.  The volume delta is the whole game.
"""

from __future__ import annotations

import logging
from typing import Any

from ..selection.live import resolve_manifest_face, select_entity
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.fillet_face_fullround")

SPIKE_STATUS = "UNFIRED"  # seat-pending: W0 flips to GREEN after live-seat fire

# Verify class (W67): there is no fillet-specific enum value; the handler
# declares an inline volume-change gate in-module (the brief §WHY NOT
# gate_additive_solid).  The attribute is present so the registry seam's
# per-lane inspection finds a verify class; the gate expression lives here.
VERIFY_CLASS = verify.FeatureClass.ADDITIVE_SOLID

# --- swconst harvest (SW2024 v32.1.0.123 — docs/sw_api_full.md line 40562-40579)
_SW_FM_FILLET = 1                       # swFmFillet — shared with constant fillet
_SW_FACE_FILLET = 2                     # swSimpleFilletType_e.swFaceFillet
_SW_FULL_ROUND_FILLET = 3               # swSimpleFilletType_e.swFullRoundFillet

# Face-set mark constants — the ``Mark`` arg to IEntity.Select2.
# Face fillet:    two sets (1 / 2)
# Full-round:     three sets (side1=3, center=4, side2=5)
_FACE_SET_MARKS = {
    "face": {
        "type": _SW_FACE_FILLET,
        "marks": (1, 2),
        "expected": 2,
    },
    "full_round": {
        "type": _SW_FULL_ROUND_FILLET,
        "marks": (3, 4, 5),
        "expected": 3,
    },
}


def _null_dispatch() -> Any:
    """ICallout null as a typed VARIANT (the §0.2 marshaling doctrine).

    Some COM paths (SelectByID2 in particular) require a typed
    ``VARIANT(VT_DISPATCH, None)`` for the callout slot — bare ``None``
    marshals to com_error -2147352571.  Returned for spike parity; the
    handler's PRIMARY selection path (``select_entity``) does not need it
    because ``IEntity.Select2`` has no callout argument.
    """
    try:
        from win32com.client import VARIANT
        import pythoncom
        return VARIANT(pythoncom.VT_DISPATCH, None)
    except ImportError:
        return None


def _resolve_and_select_faces(
    doc: Any,
    face_refs: list[dict],
    marks: tuple[int, ...],
) -> tuple[bool, str | None]:
    """Resolve each face_ref dict via ``resolve_manifest_face`` and select it
    with the corresponding mark.  Fail-closed on any unresolved face or
    failed select.

    The first face is selected with ``append=False``; subsequent faces are
    appended (the standard multi-entity selection pattern).
    """
    for i, (ref, mark) in enumerate(zip(face_refs, marks)):
        if not isinstance(ref, dict):
            return False, f"face_ref[{i}] must be a dict, got {type(ref).__name__}"
        try:
            res = resolve_manifest_face(doc, ref)
        except Exception as exc:
            return False, f"face_ref[{i}] resolve raised: {exc!r}"
        entity = getattr(res, "entity", None)
        if entity is None:
            return False, (
                f"face_ref[{i}] did not resolve to a live face "
                f"(method={getattr(res, 'method', None)})"
            )
        if not select_entity(entity, append=(i > 0), mark=mark):
            return False, (
                f"face_ref[{i}] resolved but select_entity returned False "
                f"(mark={mark})"
            )
    return True, None


def create_fillet_face_fullround(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Create a face fillet or full-round fillet on resolved faces.  Fail-closed.

    ``feature`` keys
        fillet_type : str — ``"face"`` or ``"full_round"`` (REQUIRED)
        radius_mm   : float — fillet radius (default 5.0; applied via
            ``DefaultRadius``.  For full-round fillets the radius is
            geometrically determined by the three faces; the setter is
            still invoked but the kernel may override.

    ``target`` keys (shape depends on ``fillet_type``)
        face:
            faces : list[face_ref] — exactly 2 face_ref dicts (set1, set2)
        full_round:
            side1  : face_ref — the first side face    (mark 3)
            center : face_ref — the center face to be consumed (mark 4)
            side2  : face_ref — the second side face   (mark 5)

    Returns ``(True, None)`` on a verified materialization (|d_vol| > eps)
    or ``(False, "<reason>")`` on any failure — never raises.
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    fillet_type = feature.get("fillet_type")
    if fillet_type not in _FACE_SET_MARKS:
        return False, (
            f"fillet_type must be one of {sorted(_FACE_SET_MARKS)}, "
            f"got {fillet_type!r}"
        )

    spec = _FACE_SET_MARKS[fillet_type]
    type_id: int = spec["type"]
    marks: tuple[int, ...] = spec["marks"]
    expected: int = spec["expected"]

    # --- collect face_refs in the canonical order --------------------------
    if fillet_type == "full_round":
        face_refs: list[dict] = []
        for key, mark in (("side1", marks[0]), ("center", marks[1]), ("side2", marks[2])):
            ref = target.get(key)
            if not isinstance(ref, dict):
                return False, (
                    f"full_round target must carry side1/center/side2 face_refs; "
                    f"{key!r} is {type(ref).__name__}"
                )
            face_refs.append(ref)
    else:
        faces = target.get("faces")
        if not isinstance(faces, list):
            return False, f"face target.faces must be a list, got {type(faces).__name__}"
        face_refs = faces

    if len(face_refs) != expected:
        return False, (
            f"fillet_type={fillet_type!r} requires exactly {expected} face refs, "
            f"got {len(face_refs)}"
        )

    # --- radius (face fillet primary; full-round tolerates the setter) -----
    try:
        radius_mm = float(feature.get("radius_mm", 5.0))
    except (TypeError, ValueError) as exc:
        return False, f"radius_mm parameter invalid: {exc}"
    if radius_mm <= 0:
        return False, f"radius_mm must be positive, got {radius_mm!r}"

    # --- measure BEFORE ----------------------------------------------------
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    faces_before, vol_before = verify.solid_metrics(doc)

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    # --- resolve + select faces with their set marks -----------------------
    sel_ok, sel_err = _resolve_and_select_faces(doc, face_refs, marks)
    if not sel_ok:
        return False, sel_err  # type: ignore[return-value]

    # --- CreateDefinition → Initialize(type) → DefaultRadius → CreateFeature
    try:
        from ..com.earlybind import typed_qi
        from ..com.sw_type_info import wrapper_module

        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_FILLET)
        if data is None:
            return False, "CreateDefinition(swFmFillet=1) returned None"
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=wrapper_module())
        init_ok = fd.Initialize(type_id)
        if init_ok is False:
            return False, (
                f"ISimpleFilletFeatureData2.Initialize({type_id}) returned False"
            )
        fd.DefaultRadius = radius_mm / 1000.0  # mm → m
        feat = fm.CreateFeature(fd)
        if feat is None or isinstance(feat, (int, bool)):
            return False, (
                f"CreateFeature returned non-Feature ({feat!r}) — ghost / rejected"
            )
    except Exception as exc:
        return False, f"fillet pipeline raised: {exc!r}"

    # --- measure AFTER + anti-ghost gate ----------------------------------
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    faces_after, vol_after = verify.solid_metrics(doc)
    d_vol = vol_after - vol_before
    d_faces = faces_after - faces_before  # corroboration only (logged by caller)

    if abs(d_vol) > verify.VOL_EPS_MM3:
        logger.info(
            "fillet %s materialized: d_vol_mm3=%.4f, d_faces=%d",
            fillet_type, d_vol, d_faces,
        )
        return True, None

    return False, (
        f"fillet {fillet_type!r} did not redistribute material "
        f"(d_vol_mm3={d_vol:.4e}, d_faces={d_faces}, "
        f"vol_before={vol_before:.3f}, vol_after={vol_after:.3f}); "
        f"the faces must share geometry suitable for the chosen fillet type"
    )
