"""W71 — ``scale`` feature-add handler (registry seam).

Uniformly scales the part's solid body about its centroid via
``IFeatureManager.InsertScale`` — the closed-form-transform lane that
formally locks the Part-Feature axis (the boundary law's MATERIALIZE
column: a 1.5× scale is a pure matrix transform, so the kernel never has
to traverse/solve geometry mid-invocation; W71 classification proved it
materializes with a volume ratio of 3.375 = 1.5³ to IEEE-754 precision).

**Reflected sig** (docs/sw_api_full.md line 8490 — the IFeatureManager
Feature-returning form, NOT the line-10908 ``IModelDoc2.InsertScale``
void form which ignores the scale-type semantics we need)::

    InsertScale(Type:Int16, Uniform:Boolean,
                Xscale:Double, YScale:Double, ZScale:Double) -> Feature

``Type`` is ``swScaleType_e`` (swconst 32.1 harvest):

    swScaleAboutCentroid          = 0   ("centroid")
    swScaleAboutOrigin            = 1   ("origin")
    swScaleAboutCoordinateSystem  = 2   ("coordinate_system")

**v1 scope = uniform centroid/origin scale.** ``uniform=False`` (per-axis
X/Y/Z) is fail-closed (the witness gate below assumes f**3); the
``coordinate_system`` origin is accepted by the enum but needs a selected
coordinate-system entity the v1 caller does not yet provide — documented,
not silently mis-scaled.

**Selection (IBody2.Select doctrine):** the target solid body is selected
with ``IBody2.Select(False, 0)`` — IBody2 is NOT IEntity, so the whole-body
select uses the body's own native ``Select`` (``select_entity`` /
``IEntity.Select2`` return False on a body; see the W68 seat finding).
Selection is best-effort: ``InsertScale(centroid)`` operates on the model's
bodies regardless, and the W71 probe proved the call materializes even with
no pre-selection — so a failed select is logged, not fatal (false-rejecting
a working scale would be the worse error).

**Verify-the-EFFECT (VOLUME_TRANSFORM gate):** success = the solid volume
changed by the COMMANDED ratio ``f**3`` (uniform), not merely
``|ΔVol| > eps``.  A silent no-op leaves ``ratio == 1.0``; the legacy void
``InsertScale`` form would move volume but miss the exact ratio.  A non-None
Feature return ALONE is the W21/W42 ghost trap and is NOT reported as success.
"""

from __future__ import annotations

import logging
from typing import Any

from ..com.earlybind import typed_qi
from ..com.sw_type_info import wrapper_module
from ..sw_com import resolve
from . import verify

logger = logging.getLogger("ai_sw_bridge.features.scale")

# seat-proven 2026-06-21 (spike_scale): InsertScale(0, True, 1.5, 1.5, 1.5) on a
# 10 mm cube -> ΔVol +2375.000 mm³ (1000 → 3375, ratio 3.375 = 1.5³ exact),
# survives save→reopen. Closed-form matrix transform = boundary-law MATERIALIZE.
SPIKE_STATUS = "GREEN"

VERIFY_CLASS = verify.FeatureClass.VOLUME_TRANSFORM

# swScaleType_e (swconst 32.1.0.123 harvest) — about-which-origin.
_SCALE_ABOUT: dict[str, int] = {
    "centroid": 0,
    "origin": 1,
    "coordinate_system": 2,
}


def _fm(doc: Any) -> Any:
    """The typed ``IFeatureManager`` (the W71-probe-proven InsertScale caller).

    InsertScale's leading ``Int16`` arg marshals cleanly through the compiled
    typelib; the raw late-bound ``doc.FeatureManager`` is the fallback (and the
    seam offline tests monkeypatch)."""
    try:
        return typed_qi(
            resolve(doc, "FeatureManager"), "IFeatureManager", module=wrapper_module()
        )
    except Exception as e:  # pragma: no cover - exercised only on a live seat
        logger.warning("[scale] typed FeatureManager QI failed (%r); using raw", e)
        return doc.FeatureManager


def _select_target_body(doc: Any, body_name: str | None) -> bool:
    """Select the target solid body via ``IBody2.Select(False, 0)`` (best-effort).

    Returns ``True`` if a body was selected. IBody2 is NOT IEntity — the
    whole-body select is the body's OWN native ``Select`` (W68 seat finding).
    """
    sols = verify.bodies(doc, verify.SW_SOLID_BODY, False)
    if not sols:
        return False
    target = sols[0]
    if body_name:
        for b in sols:
            try:
                nm = b.Name
                nm = nm() if callable(nm) else nm
            except Exception:
                nm = None
            if nm == body_name:
                target = b
                break
    try:
        ok = bool(target.Select(False, 0))
    except Exception as e:
        logger.warning("[scale] IBody2.Select RAISED: %r", e)
        return False
    if not ok:
        logger.warning("[scale] IBody2.Select(False, 0) -> False")
    return ok


def create_scale(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Uniformly scale the part's solid body about its centroid/origin.

    Fail-closed: returns ``(False, reason)`` on any failure; never raises.

    ``feature`` keys
        scale_factor : float (>0)  — uniform scale multiplier (required)
        uniform      : bool        — v1 supports only True (default True)
        origin       : str         — centroid | origin | coordinate_system
                                     (default "centroid")

    ``target`` keys
        body_name : str — optional; name the solid body to scale (default:
                          the first solid body).
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    raw_factor = feature.get("scale_factor")
    if isinstance(raw_factor, bool) or not isinstance(raw_factor, (int, float)):
        return False, "feature must include a numeric 'scale_factor'"
    scale_factor = float(raw_factor)
    if scale_factor <= 0.0:
        return False, f"scale_factor must be positive, got {scale_factor!r}"

    uniform = bool(feature.get("uniform", True))
    if not uniform:
        return False, (
            "non-uniform (per-axis) scale is not supported in v1 — "
            "v1 is uniform centroid/origin scale only"
        )

    origin = feature.get("origin", "centroid")
    if not isinstance(origin, str) or origin.strip().lower() not in _SCALE_ABOUT:
        return False, (
            f"origin {origin!r} not one of {sorted(_SCALE_ABOUT)}"
        )
    scale_type = _SCALE_ABOUT[origin.strip().lower()]

    vol_before = verify.solid_volume_mm3(doc)
    if vol_before <= verify.VOL_EPS_MM3:
        return False, "document has no solid body to scale"

    try:
        doc.ClearSelection2(True)
    except Exception as e:
        logger.warning("[scale] ClearSelection2 RAISED: %r", e)

    # Best-effort body targeting (IBody2.Select doctrine). A failed select is
    # NOT fatal: InsertScale(centroid) operates on the body regardless and the
    # W71 probe materialized with no pre-selection.
    _select_target_body(doc, target.get("body_name"))

    try:
        fm = _fm(doc)
        fm.InsertScale(scale_type, True, scale_factor, scale_factor, scale_factor)
        doc.ForceRebuild3(False)
    except Exception as exc:
        return False, f"InsertScale raised: {exc!r}"

    vol_after = verify.solid_volume_mm3(doc)
    expected_ratio = scale_factor ** 3
    d_vol = vol_after - vol_before

    if verify.gate_volume_transform(vol_before, vol_after, expected_ratio):
        return True, (
            f"scale created (factor={scale_factor}, origin={origin!r}, "
            f"vol {vol_before:.3f}→{vol_after:.3f} mm3, ΔVol={d_vol:+.3f}, "
            f"ratio≈{vol_after / vol_before:.4f}, expected {expected_ratio:.4f})"
        )

    actual_ratio = (vol_after / vol_before) if vol_before else float("nan")
    return False, (
        f"scale did not transform the body by the commanded ratio "
        f"(vol {vol_before:.3f}→{vol_after:.3f} mm3, ratio={actual_ratio:.4f}, "
        f"expected {expected_ratio:.4f}); factor={scale_factor}, origin={origin!r}"
    )

# Registration is via the sanctioned ``_register_lane`` gate in
# ``features/__init__.py`` (W67 Phase-4 fail-loud path) — not a module-level
# self-register block.
