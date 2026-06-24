"""W68 — ``face fillet`` feature-add handler (registry seam), full-round split out.

Seat-proven 2026-06-21 (W0).  The face-set wall was a makepy SAFEARRAY-of-
IDispatch marshaling boundary, NOT a Parasolid refusal:

  * ``SetFaces(which, [pyface])``  — bare Python list → silent no-op
    (``GetFaceCount(which)`` stays 0, CreateFeature → None).
  * ``SetFaces(which, VARIANT(VT_ARRAY|VT_DISPATCH, [pyface]))`` — binds
    (``GetFaceCount(which)`` → 1) and the kernel builds the fillet
    (face cert: dVol = -57.94 mm³ on a 3 mm fillet, GetTypeName2 = "Fillet",
    survives save/close/reopen).

This is the [[reference_makepy_wrong_argtype]] class — a typed VARIANT SafeArray
bypasses the mistyped late-bound array arg.  ``ISimpleFilletFeatureData2`` member
list (docs/sw_api_full.md, SW2024 v32.1):

    Initialize(Int32 FilletType) -> Boolean
    SetFaces(Int32 WhichFaceList, Object FaceList) -> Void   # needs VARIANT array
    GetFaceCount(Int32 WhichFaceList) -> Int32               # bind-check readback
    DefaultRadius : Double (prop, metres)

    swSimpleFilletType_e:       swFaceFillet=2, swFullRoundFillet=3
    swSimpleFilletWhichFaces_e: swFaceFilletSet1=1, swFaceFilletSet2=2,
                                swFullRoundFilletSet1=3, swFullRoundFilletCenterSet=4,
                                swFullRoundFilletSet2=5

**FACE fillet (SHIPPED):** two face-sets (WhichFaceList 1 / 2), each bound via a
VARIANT-array ``SetFaces``; a ``GetFaceCount(which) == 1`` readback guards against
the silent-no-op ghost BEFORE ``CreateFeature``.

**FULL-ROUND (SHIPPED 2026-06-21):** three face-sets (WhichFaceList 3 side1 /
4 center / 5 side2), each bound via the same VARIANT-array ``SetFaces`` +
``GetFaceCount==1`` guard, then ``Initialize(swFullRoundFillet=3)`` →
``CreateFeature``.  The centre face is replaced by a surface tangent to the two
side faces.  Seat-proven by ``spike_fillet_fullround_probe`` (40x20x10 box →
half-cylinder, dVol = -1716.81mm³ exact).  The earlier slab-fixture ghost was a
FIXTURE artifact (degenerate adjacency), NOT a kernel wall — full-round is
MATERIALIZE-class (explicit 3-face) per the boundary law.  Fail-closed: if a
caller's three faces are not a valid tangent candidate, ``CreateFeature``
no-ops and the |d_vol| gate returns ``(False, ...)``.

**Verify-the-EFFECT (VOLUME CHANGE):** a fillet REDISTRIBUTES material.  The face
delta is unreliable (a blend can consume faces), so the gate is
``|d_vol| > verify.VOL_EPS_MM3``.  ``CreateFeature`` may raise
DISP_E_MEMBERNOTFOUND on its return while the solid is already built — that COM
return-marshaling noise is swallowed; the volume delta is the witness.
"""

from __future__ import annotations

import logging
from typing import Any

from ..selection.live import resolve_manifest_face
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.fillet_face_fullround")

SPIKE_STATUS = "GREEN"  # face + full_round seat-proven 2026-06-21

# Verify class: no fillet-specific enum; the gate is an inline volume-change
# test (the brief's §WHY-NOT gate_additive_solid).  Attribute present so the
# registry seam's per-lane inspection finds a verify class.
VERIFY_CLASS = verify.FeatureClass.ADDITIVE_SOLID

# --- swconst harvest (SW2024 v32.1.0.123 — docs/sw_api_full.md) -------------
_SW_FM_FILLET = 1  # swFmFillet — shared with constant fillet
_SW_FACE_FILLET = 2  # swSimpleFilletType_e.swFaceFillet
_SW_FULL_ROUND_FILLET = 3  # swSimpleFilletType_e.swFullRoundFillet

# CreateFeature may raise this on its RETURN while the solid is already built.
_MEMBER_NOT_FOUND = -2147352573  # DISP_E_MEMBERNOTFOUND

# WhichFaceList ids per sub-type (the Int32 arg to SetFaces / GetFaceCount).
_FACE_WHICH = (1, 2)  # swFaceFilletSet1 / Set2
_FULL_ROUND_WHICH = (3, 4, 5)  # side1 / center / side2


def _face_safearray(face: Any) -> Any:
    """Wrap a single IFace2 in a typed ``VARIANT(VT_ARRAY|VT_DISPATCH)`` SafeArray.

    The bare-Python-list form of ``SetFaces`` mis-marshals to a silent no-op
    (the makepy array-VT trap); the typed VARIANT SafeArray binds correctly.
    """
    from win32com.client import VARIANT
    import pythoncom

    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [face])


def create_fillet_face_fullround(
    doc: Any,
    feature: dict,
    target: dict,
) -> tuple[bool, str | None]:
    """Create a FACE fillet on two resolved face-sets.  Fail-closed; never raises.

    ``feature`` keys
        fillet_type : str — ``"face"`` or ``"full_round"`` (both SHIPPED)
        radius_mm   : float — face-fillet radius (default 5.0; via DefaultRadius)

    ``target`` keys
        face:        faces : list[face_ref] — exactly 2 face_ref dicts (set1, set2)
        full_round:  side1 / center / side2 face_refs (the tangent candidate)

    Returns ``(True, None)`` on a verified materialization (|d_vol| > eps) or
    ``(False, "<reason>")`` otherwise.
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    fillet_type = feature.get("fillet_type")
    if fillet_type not in ("face", "full_round"):
        return False, (
            f"fillet_type must be one of ['face', 'full_round'], got {fillet_type!r}"
        )

    # full_round: SEAT-PROVEN 2026-06-21 (spike_fillet_fullround_probe = PASS,
    # Δvol -1716.81mm³ exact half-cylinder on a 40x20x10 box).  The prior slab
    # ghost was a FIXTURE artifact, NOT a kernel wall — full-round is
    # MATERIALIZE-class (explicit 3-face), per [[reference_oop_boundary_law]].
    if fillet_type == "full_round":
        return _create_full_round(doc, target)

    # --- FACE fillet: collect exactly two face_refs ------------------------
    faces = target.get("faces")
    if not isinstance(faces, list):
        return False, f"face target.faces must be a list, got {type(faces).__name__}"
    if len(faces) != 2:
        return (
            False,
            f"fillet_type='face' requires exactly 2 face refs, got {len(faces)}",
        )

    # --- radius ------------------------------------------------------------
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

    # --- CreateDefinition → Initialize(face) → SetFaces (VARIANT) → CreateFeature
    try:
        from ..com.earlybind import typed_qi
        from ..com.sw_type_info import wrapper_module

        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_FILLET)
        if data is None:
            return False, "CreateDefinition(swFmFillet=1) returned None"
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=wrapper_module())
        init_ok = fd.Initialize(_SW_FACE_FILLET)
        if init_ok is False:
            return (
                False,
                f"ISimpleFilletFeatureData2.Initialize({_SW_FACE_FILLET}) returned False",
            )
        fd.DefaultRadius = radius_mm / 1000.0  # mm → m

        # bind each face-set via a typed VARIANT SafeArray; readback-guard the bind
        for i, (ref, which) in enumerate(zip(faces, _FACE_WHICH)):
            if not isinstance(ref, dict):
                return False, f"face_ref[{i}] must be a dict, got {type(ref).__name__}"
            res = resolve_manifest_face(doc, ref)
            entity = getattr(res, "entity", None)
            if entity is None:
                return False, (
                    f"face_ref[{i}] did not resolve to a live face "
                    f"(method={getattr(res, 'method', None)})"
                )
            fd.SetFaces(which, _face_safearray(entity))
            try:
                bound = fd.GetFaceCount(which)
            except Exception as exc:
                return False, f"GetFaceCount({which}) raised: {exc!r}"
            if bound != 1:
                return False, (
                    f"face-set {which} did not bind (GetFaceCount={bound!r}); "
                    f"the SetFaces SafeArray marshaling failed"
                )

        # CreateFeature — swallow the DISP_E_MEMBERNOTFOUND return noise; the
        # volume delta below is the real witness.
        try:
            fm.CreateFeature(fd)
        except Exception as exc:
            hr = getattr(exc, "args", [None])[0] if hasattr(exc, "args") else None
            if hr != _MEMBER_NOT_FOUND:
                return False, f"CreateFeature raised: {exc!r}"
    except Exception as exc:
        return False, f"fillet pipeline raised: {exc!r}"

    # --- measure AFTER + anti-ghost gate ----------------------------------
    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    faces_after, vol_after = verify.solid_metrics(doc)
    d_vol = vol_after - vol_before
    d_faces = faces_after - faces_before  # corroboration only

    if abs(d_vol) > verify.VOL_EPS_MM3:
        logger.info(
            "face fillet materialized: d_vol_mm3=%.4f, d_faces=%d", d_vol, d_faces
        )
        return True, None

    return False, (
        f"face fillet did not redistribute material "
        f"(d_vol_mm3={d_vol:.4e}, d_faces={d_faces}, "
        f"vol_before={vol_before:.3f}, vol_after={vol_after:.3f}); "
        f"the two faces must share an edge suitable for a face fillet"
    )


def _create_full_round(doc: Any, target: dict) -> tuple[bool, str | None]:
    """Create a FULL-ROUND fillet across three resolved face-sets.

    Seat-proven 2026-06-21 (spike_fillet_fullround_probe):
    ``CreateDefinition(swFmFillet=1) → typed_qi(ISimpleFilletFeatureData2) →
    Initialize(swFullRoundFillet=3) → SetFaces(which, VARIANT[face]) for
    which ∈ (3 side1, 4 center, 5 side2) with a GetFaceCount==1 readback guard
    → CreateFeature``.  The centre face is replaced by a surface tangent to the
    two side faces, so the witness is ``|d_vol| > eps``.  Fail-closed.

    ``target`` keys (each a face_ref dict): ``side1`` / ``center`` / ``side2``.
    """
    refs = [
        (target.get("side1"), 3),
        (target.get("center"), 4),
        (target.get("side2"), 5),
    ]
    for name, ref_which in zip(("side1", "center", "side2"), refs):
        if not isinstance(ref_which[0], dict):
            return False, f"full_round target.{name} must be a face_ref dict"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    faces_before, vol_before = verify.solid_metrics(doc)
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    try:
        from ..com.earlybind import typed_qi
        from ..com.sw_type_info import wrapper_module

        fm = doc.FeatureManager
        data = fm.CreateDefinition(_SW_FM_FILLET)
        if data is None:
            return False, "CreateDefinition(swFmFillet=1) returned None"
        fd = typed_qi(data, "ISimpleFilletFeatureData2", module=wrapper_module())
        init_ok = fd.Initialize(_SW_FULL_ROUND_FILLET)
        if init_ok is False:
            return False, f"Initialize({_SW_FULL_ROUND_FILLET}) returned False"

        for ref, which in refs:
            res = resolve_manifest_face(doc, ref)
            entity = getattr(res, "entity", None)
            if entity is None:
                return False, (
                    f"full_round face-set {which} did not resolve to a live face "
                    f"(method={getattr(res, 'method', None)})"
                )
            fd.SetFaces(which, _face_safearray(entity))
            try:
                bound = fd.GetFaceCount(which)
            except Exception as exc:
                return False, f"GetFaceCount({which}) raised: {exc!r}"
            if bound != 1:
                return False, (
                    f"full_round face-set {which} did not bind (GetFaceCount={bound!r})"
                )

        try:
            fm.CreateFeature(fd)
        except Exception as exc:
            hr = getattr(exc, "args", [None])[0] if hasattr(exc, "args") else None
            if hr != _MEMBER_NOT_FOUND:
                return False, f"CreateFeature raised: {exc!r}"
    except Exception as exc:
        return False, f"full_round pipeline raised: {exc!r}"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    faces_after, vol_after = verify.solid_metrics(doc)
    d_vol = vol_after - vol_before
    d_faces = faces_after - faces_before

    if abs(d_vol) > verify.VOL_EPS_MM3:
        logger.info(
            "full_round fillet materialized: d_vol_mm3=%.4f, d_faces=%d", d_vol, d_faces
        )
        return True, None

    return False, (
        f"full_round fillet did not redistribute material "
        f"(d_vol_mm3={d_vol:.4e}, d_faces={d_faces}); the three face-sets must "
        f"form a valid side1/center/side2 tangent candidate"
    )
