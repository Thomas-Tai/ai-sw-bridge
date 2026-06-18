"""W66 — ``planar_surface`` feature-add handler (registry seam).

Planar reference surface filling a closed boundary (sketch contour or
coplanar edge loop) via the legacy ``IModelDoc2.InsertPlanarRefSurface``
(0-arg, returns Boolean). Mode-B is the operative path — the method has
no ``CreateDefinition`` route (legacy ``Insert*`` per the W66 brief §0.5).

Verify-the-EFFECT by surface class (§0.1): a surface feature creates a
zero-thickness **sheet body**, so ΔVol is meaningless. The witness is
the surface-body count + area:

  * **Materialization witness:** ``GetBodies2(swSheetBody=1, False)``
    count delta ≥ +1.
  * **Anti-ghost witness:** total sheet-body area > 0. A Boolean return
    without a new body, or with zero area, is the surface form of the
    W42/W65 ghost — ``ΔArea > 0`` catches it exactly as ``ΔVol > 0``
    catches solid ghosts.
  * **Corroborate:** bounding-box change + survives save→reopen (spike).
"""

from __future__ import annotations

import logging
from typing import Any

from ..selection.live import select_entity

logger = logging.getLogger("ai_sw_bridge.features.planar_surface")

SPIKE_STATUS = "GREEN"  # seat-proven W0 2026-06-18: InsertPlanarRefSurface -> 'PlanarSurface', sheet bodies 0->1, area 0->600mm² (surface-CREATE gate), survives reopen

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


def create_planar_surface(
    doc: Any, feature: dict, target: dict
) -> tuple[bool, str | None]:
    """Insert a planar surface from a pre-selected closed boundary. Fail-closed.

    ``feature`` keys
        (none — the planar surface takes no parameters beyond the boundary)

    ``target`` keys
        boundary : str  — sketch name (e.g. ``"Sketch2"``) whose closed
            contour defines the surface region. Must already exist in the
            feature tree.
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    boundary = target.get("boundary")
    if not isinstance(boundary, str) or not boundary:
        return False, "target must contain a non-empty 'boundary' string (sketch name)"

    count_before = _sheet_body_count(doc)
    area_before = _total_sheet_area_mm2(doc)

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    feat = doc.FeatureByName(boundary)
    if feat is None:
        return False, f"boundary sketch {boundary!r} not found in feature tree"

    if not select_entity(feat, mark=0):
        return False, f"failed to select boundary sketch {boundary!r}"

    try:
        ips = doc.InsertPlanarRefSurface
        result = ips() if callable(ips) else ips
    except Exception as exc:
        return False, f"InsertPlanarRefSurface raised: {exc!r}"

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
        f"planar surface did not materialize "
        f"(delta_bodies={d_count}, delta_area_mm2={d_area:.6f}); "
        f"the boundary must be a closed coplanar sketch or edge loop"
    )
