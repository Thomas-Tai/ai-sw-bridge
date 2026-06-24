"""W73 — ``structural_weldment`` feature-add handler (registry seam).

Generates real, mass-bearing structural frame geometry by sweeping a library
weldment profile along an explicit 3D-sketch path via
``IFeatureManager.InsertStructuralWeldment5`` — and the kernel executes the
member end-trim/coped/miter INTERSECTION SOLVE out-of-process too.

**Boundary-law corollary (W73, the reason this lane exists):** the raw
mid-invocation B-rep boolean solve walls when the kernel must DERIVE instance
positions (fill_pattern grid+boundary, indent clearance surface).  But an
ENCAPSULATED MACRO-FEATURE like ``InsertStructuralWeldment5`` bundles the
explicit-path profile sweep AND the subsequent corner intersection-solve into
one generative transaction; the members are placed at positions the caller
fully determined (the 3D-sketch segments), so the corner trim is a LOCAL,
deterministic boolean at a KNOWN joint — it MATERIALIZES.  W73 probe proved
even the heaviest case (miter-merge fusing two members into one body by solving
the member-member intersection) materializes out-of-process.

**Reflected sig** (docs/sw_api_full.md line 8513)::

    InsertStructuralWeldment5(Path:String, ConnectedSegmentsOption:Int32,
        AllowProtrusion:Boolean, Groups:Object, ConfigurationName:String)
        -> Feature

**The ``0`` GHOST TRAP:** ``swConnectedSegmentsOption_e`` is SimpleCut=1 /
CopedCut=2 — there is NO ``0``.  Connected segments (segments sharing an
endpoint) MUST be cut; passing ``0`` makes the WHOLE feature return None / ΔVol
0 (it masquerades as a kernel wall — it is not).  This handler maps to {1, 2}
ONLY and defaults to SimpleCut(1); ``0`` is unreachable.

**Marshalling (the SAFEARRAY friction point):** group segments are assigned
through the ``Segments`` PROPERTY with ``VARIANT(VT_ARRAY|VT_DISPATCH, segs)``
(the ``ISetSegments`` METHOD raises 'Python instance can not be converted to a
COM object').  The ``Groups`` arg is likewise a ``VARIANT(VT_ARRAY|VT_DISPATCH,
[group])``.  Both go through ``_disp_array`` (monkeypatchable for offline tests).

**Path-feature re-typing:** the driving sketch is resolved by name, then
re-typed to ``IFeature`` before ``GetSpecificFeature2`` (raw late-bound dispatch
'Member not found's on it — the FirstFeature-walk lesson), then to ``ISketch``
for ``GetSketchSegments``.

**Verify-the-EFFECT (ADDITIVE_SOLID gate):** success = ΔFaces > 0 ∧ |ΔVol| >
eps (frame members are mass-bearing solid bodies built from the path).  A
non-None Feature return ALONE is the W21/W42 ghost trap and is NOT success.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pythoncom
from win32com.client import VARIANT

from ..com.earlybind import typed_qi
from ..com.sw_type_info import wrapper_module
from ..sw_com import resolve
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.structural_weldment")

# seat-proven 2026-06-22 (spike_structural_weldment): create_structural_weldment
# on a square-tube profile swept along a 100mm L-path -> valid Feature, ΔVol
# +26739.822 mm³, 2 bodies; miter-merge variant fuses 2->1 body (ΔVol
# +26740.332). Encapsulated macro-feature = boundary-law MATERIALIZE corollary.
# Production seat-proof spike_structural_weldment GREEN 7/7 2026-06-22 (handler
# path: simple_cut +36 faces/2 bodies, miter_merge fuses 2->1, both guards).
SPIKE_STATUS = "GREEN"

VERIFY_CLASS = verify.FeatureClass.ADDITIVE_SOLID

# swConnectedSegmentsOption_e (swconst 32.1 harvest). NOTE: NO 0 — connected
# segments must be cut; 0 ghosts the whole feature (the W73 footgun). Default
# routes to SimpleCut(1).
_CONNECTED_SEGMENTS: dict[str, int] = {
    "simple_cut": 1,
    "coped_cut": 2,
}


def _disp_array(items: list[Any]) -> Any:
    """Wrap a list of COM dispatch objects into a SAFEARRAY VARIANT.

    Isolated so offline tests can monkeypatch it to identity (keeping COM
    marshalling off the test path)."""
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(items))


def _fm(doc: Any) -> Any:
    """The typed ``IFeatureManager`` (the InsertStructuralWeldment5 caller).

    Falls back to the raw late-bound ``doc.FeatureManager`` (the seam offline
    tests monkeypatch ``typed_qi`` / ``resolve`` to bypass)."""
    try:
        return typed_qi(
            resolve(doc, "FeatureManager"), "IFeatureManager", module=wrapper_module()
        )
    except Exception as e:  # pragma: no cover - exercised only on a live seat
        logger.warning("[structural_weldment] typed FM QI failed (%r); using raw", e)
        return doc.FeatureManager


def _resolve_path_segments(doc: Any, sketch_name: str) -> list[Any] | None:
    """Resolve the driving sketch by name and return its sketch segments.

    Re-types the resolved feature to IFeature before GetSpecificFeature2 (raw
    late-bound 'Member not found's), then to ISketch.  Returns ``None`` on any
    failure, ``[]`` if the sketch has no segments.
    """
    try:
        feat_raw = doc.FeatureByName(sketch_name)
    except Exception as e:
        logger.warning(
            "[structural_weldment] FeatureByName(%r) RAISED: %r", sketch_name, e
        )
        return None
    if feat_raw is None:
        logger.warning("[structural_weldment] FeatureByName(%r) -> None", sketch_name)
        return None
    try:
        mod = wrapper_module()
        feat = typed_qi(feat_raw, "IFeature", module=mod)
        sketch = typed_qi(feat.GetSpecificFeature2(), "ISketch", module=mod)
        segs = sketch.GetSketchSegments()
    except Exception as e:
        logger.warning("[structural_weldment] segment resolve RAISED: %r", e)
        return None
    if segs is None:
        return []
    return list(segs) if isinstance(segs, (list, tuple)) else [segs]


def _build_and_fire(
    fm: Any,
    *,
    profile_path: str,
    segments: list[Any],
    connected_opt: int,
    allow_protrusion: bool,
    corner_treatment: bool,
    corner_type: int | None,
    miter_merge: bool,
    configuration: str,
) -> Any:
    """Create the structural-member group, assign segments + corner options,
    and fire InsertStructuralWeldment5.  Returns the Feature (or None)."""
    grp = fm.CreateStructuralMemberGroup()
    grp.Segments = _disp_array(segments)
    grp.ApplyCornerTreatment = corner_treatment
    if corner_type is not None:
        try:
            grp.CornerTreatmentType = corner_type
        except Exception as e:
            logger.warning(
                "[structural_weldment] CornerTreatmentType set RAISED: %r", e
            )
    if miter_merge:
        try:
            grp.MiterMergeCondition = True
        except Exception as e:
            logger.warning(
                "[structural_weldment] MiterMergeCondition set RAISED: %r", e
            )
    return fm.InsertStructuralWeldment5(
        profile_path,
        connected_opt,
        allow_protrusion,
        _disp_array([grp]),
        configuration,
    )


def create_structural_weldment(
    doc: Any,
    feature: dict,
    target: dict,
) -> tuple[bool, str | None]:
    """Generate structural frame members along a 3D-sketch path.

    Fail-closed: returns ``(False, reason)`` on any failure; never raises.

    ``feature`` keys
        profile_path       : str  — FULL path to a ``.sldlfp`` weldment profile
                                     library part (required; must exist on disk)
        configuration      : str  — the size config inside the profile
                                     (e.g. "20 x 20 x 2"); required
        sketch_name        : str  — name of the driving 3D-sketch path (required)
        connected_segments : str  — "simple_cut" (default) | "coped_cut"
                                     (maps to swConnectedSegmentsOption 1/2 — never 0)
        allow_protrusion   : bool — allow members to protrude (default True)
        corner_treatment   : bool — apply group corner treatment (default False)
        corner_treatment_type : int — optional CornerTreatmentType enum value
        miter_merge        : bool — miter-merge connected members into one body
                                     (default False)

    ``target`` keys
        (reserved; the driving sketch is named in ``feature['sketch_name']``)
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    profile_path = feature.get("profile_path")
    if not profile_path or not isinstance(profile_path, str):
        return False, "feature must include a non-empty 'profile_path' string"
    if not os.path.isfile(profile_path):
        # fail closed — a missing profile makes InsertStructuralWeldment5 ghost
        # silently (ret None / ΔVol 0), masquerading as a kernel wall.
        return False, f"profile_path does not exist on disk: {profile_path!r}"

    configuration = feature.get("configuration")
    if not configuration or not isinstance(configuration, str):
        return False, "feature must include a non-empty 'configuration' string"

    sketch_name = feature.get("sketch_name")
    if not sketch_name or not isinstance(sketch_name, str):
        return False, "feature must include a non-empty 'sketch_name' string"

    cseg = feature.get("connected_segments", "simple_cut")
    if not isinstance(cseg, str) or cseg.strip().lower() not in _CONNECTED_SEGMENTS:
        return False, (
            f"connected_segments {cseg!r} not one of {sorted(_CONNECTED_SEGMENTS)}"
        )
    connected_opt = _CONNECTED_SEGMENTS[cseg.strip().lower()]

    allow_protrusion = bool(feature.get("allow_protrusion", True))
    corner_treatment = bool(feature.get("corner_treatment", False))
    miter_merge = bool(feature.get("miter_merge", False))
    corner_type = feature.get("corner_treatment_type")
    if corner_type is not None and (
        isinstance(corner_type, bool) or not isinstance(corner_type, int)
    ):
        return False, "corner_treatment_type must be an int (or omitted)"

    segments = _resolve_path_segments(doc, sketch_name)
    if segments is None:
        return False, f"could not resolve driving sketch {sketch_name!r}"
    if not segments:
        return False, f"driving sketch {sketch_name!r} has no path segments"

    faces_before, vol_before = verify.solid_metrics(doc)

    try:
        doc.ClearSelection2(True)
    except Exception as e:
        logger.warning("[structural_weldment] ClearSelection2 RAISED: %r", e)

    try:
        fm = _fm(doc)
        _build_and_fire(
            fm,
            profile_path=profile_path,
            segments=segments,
            connected_opt=connected_opt,
            allow_protrusion=allow_protrusion,
            corner_treatment=corner_treatment,
            corner_type=corner_type,
            miter_merge=miter_merge,
            configuration=configuration,
        )
        doc.ForceRebuild3(False)
    except Exception as exc:
        return False, f"InsertStructuralWeldment5 raised: {exc!r}"

    faces_after, vol_after = verify.solid_metrics(doc)
    d_faces = faces_after - faces_before
    d_vol = vol_after - vol_before
    bodies_after = verify.solid_body_count(doc)

    if verify.gate_additive_solid(d_faces, d_vol):
        return True, (
            f"structural_weldment created (profile={os.path.basename(profile_path)!r}, "
            f"config={configuration!r}, sketch={sketch_name!r}, "
            f"segments={len(segments)}, connected={cseg}, miter_merge={miter_merge}, "
            f"+{d_faces} faces, ΔVol={d_vol:+.3f} mm3, bodies={bodies_after})"
        )

    return False, (
        f"structural_weldment did not materialize frame geometry "
        f"(Δfaces={d_faces}, ΔVol={d_vol:+.3f} mm3); profile="
        f"{os.path.basename(profile_path)!r}, config={configuration!r}, "
        f"sketch={sketch_name!r}, connected={cseg} — a 0 connected-segments "
        f"option or a missing profile config ghosts the feature"
    )


# Registration is via the sanctioned ``_register_lane`` gate in
# ``features/__init__.py`` (W67 Phase-4 fail-loud path) — not a module-level
# self-register block.
