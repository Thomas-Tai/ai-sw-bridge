"""W66 — ``offset_surface`` feature-add handler (registry seam).

Offsets an existing face (or surface body) into a new sheet body via the
legacy ``IModelDoc2.InsertOffsetSurface(Thickness: Double, Reverse: Boolean)``
(2-arg, returns Void). Mode-B is the operative path — the method has no
``CreateDefinition`` route (legacy ``Insert*`` per the W66 brief §0.5).

Verify-the-EFFECT by surface class (§0.1): a surface feature creates a
zero-thickness **sheet body**, so ΔVol is meaningless. The witness is
the surface-body count + area:

  * **Materialization witness:** ``GetBodies2(swSheetBody=1, False)``
    count delta ≥ +1.
  * **Anti-ghost witness:** total sheet-body area > 0. A Void return
    without a new body, or with zero area, is the surface form of the
    W42/W65 ghost — ``ΔArea > 0`` catches it exactly as ``ΔVol > 0``
    catches solid ghosts.
  * **Corroborate:** bounding-box change + survives save→reopen (spike).
"""

from __future__ import annotations

import logging
from typing import Any

from ..selection.live import select_entity

logger = logging.getLogger("ai_sw_bridge.features.offset_surface")

SPIKE_STATUS = "GREEN"  # seat-proven W0 2026-06-18: InsertOffsetSurface -> 'OffsetRefSurface', sheet bodies 0->1, area 0->1200mm² (surface-CREATE gate), survives reopen

_SW_SHEET_BODY = 1

# Below this, an area delta is FP noise, not a real surface.
_AREA_EPS_MM2 = 1e-6


def _sheet_bodies(doc: Any) -> list[Any] | None:
    """Sheet bodies of *doc*; ``None`` on COM failure, ``[]`` when empty."""
    try:
        bodies = doc.GetBodies2(_SW_SHEET_BODY, False)
    except Exception:
        return None
    if not bodies:
        return []
    return list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]


def _sheet_body_count(doc: Any) -> int:
    bodies = _sheet_bodies(doc)
    if bodies is None:
        return 0
    return len(bodies)


def _total_sheet_area_mm2(doc: Any) -> float:
    """Sum of face areas over all sheet bodies (mm²); 0.0 on failure.

    SW returns area in m² per face; converted to mm² (×1e6) to match the
    handler's mm-domain gate constant.
    """
    bodies = _sheet_bodies(doc)
    if not bodies:
        return 0.0
    total = 0.0
    for b in bodies:
        try:
            faces = b.GetFaces
            if callable(faces):
                faces = faces()
            if not faces:
                continue
            for f in faces:
                try:
                    a = f.GetArea
                    if callable(a):
                        a = a()
                    total += float(a) * 1e6
                except Exception:
                    pass
        except Exception:
            pass
    return total


def create_offset_surface(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Insert an offset surface from a pre-selected face. Fail-closed.

    ``feature`` keys
        offset_mm : float  — offset distance in mm (default 5.0); converted
            to metres for the SW API call.
        reverse   : bool   — flip offset direction (default False)

    ``target`` keys
        face_entity : Any  — the live COM face entity (IFace2) to offset.
            Obtained upstream via coordinate-pick or durable face manifest.
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    face_entity = target.get("face_entity")
    if face_entity is None:
        return False, "target must include 'face_entity'"

    try:
        offset_m = float(feature.get("offset_mm", 5.0)) / 1000.0
    except (TypeError, ValueError) as exc:
        return False, f"offset_mm must be numeric: {exc}"
    if offset_m < 0:
        return False, f"offset_mm must be non-negative, got {feature.get('offset_mm')!r}"

    reverse = bool(feature.get("reverse", False))

    count_before = _sheet_body_count(doc)
    area_before = _total_sheet_area_mm2(doc)

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    if not select_entity(face_entity, mark=0):
        return False, "failed to select the target face"

    try:
        doc.InsertOffsetSurface(offset_m, reverse)
    except Exception as exc:
        return False, f"InsertOffsetSurface raised: {exc!r}"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    count_after = _sheet_body_count(doc)
    area_after = _total_sheet_area_mm2(doc)

    d_count = count_after - count_before
    d_area = area_after - area_before

    if d_count >= 1 and d_area > _AREA_EPS_MM2:
        return True, None

    return False, (
        f"offset surface did not materialize "
        f"(delta_bodies={d_count}, delta_area_mm2={d_area:.6f}); "
        f"the face_entity must reference an existing solid or surface face"
    )
