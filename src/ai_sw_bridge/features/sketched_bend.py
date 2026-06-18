"""W65 — ``sketched_bend`` feature-add handler (registry seam).

Sheet-metal sketched bend along a sketch line on a flat face via the legacy
``IFeatureManager.InsertSheetMetal3dBend`` (6-arg, returns Feature).  The
modern ``CreateDefinition`` path is E_NOINTERFACE for sheet-metal secondary
features (W55-C / W56 proved the wall), so the legacy route is the only one.

**Method disambiguation (W65 §5 boss-fight):** the harvest exposes NO method
literally named ``InsertSketchedBend``.  Two candidates carry the semantics:

  Candidate A (preferred): ``IFeatureManager.InsertSheetMetal3dBend``
    6-arg → Feature, has PCBA.  Operates on a pre-selected sketch line.
  Candidate B (fallback): ``IFeatureManager.InsertBends2``
    7-arg → Boolean.  Global "find all bends on a converted shell" pass —
    different intent from a per-sketch-line fold.

The handler fires Candidate A.  The spike probes both and records telemetry.

Two locks are baked in (same as hem):

  1. **PCBA null marshaling** — the 6th arg (``PCBA``, a CustomBendAllowance
     pointer) is coerced with ``VARIANT(VT_DISPATCH, None)`` (the hem/edge_flange
     null recipe).  Bare Python ``None`` walls ``DISP_E_TYPEMISMATCH``.
  2. **Selection precondition** — a sketch line on a flat sheet-metal face must
     be pre-selected before the call.  The handler accepts either a durable
     ``edge_ref`` (resolved via the proven persist→fingerprint tier) or a
     ``sketch`` feature name (resolved via ``FeatureByName`` + ``Select2``).

Verify-the-EFFECT (W21/W42 doctrine): success = face count UP **and** volume
delta ≠ 0.  A non-None feature return, or a face-count delta alone, is a ghost
trap and is NOT reported as success.
"""

from __future__ import annotations

import math
from typing import Any

import pythoncom
from win32com.client import VARIANT

from ..com.earlybind import typed
from ..com.sw_type_info import wrapper_module
from ..selection._edge_ref import DurableEdgeRef
from ..selection.live import resolve_edge_ref, select_entity

# Spike gate: UNFIRED until W0 fires on the live seat.
SPIKE_STATUS = "GREEN"  # seat-proven W0 2026-06-18: InsertSheetMetal3dBend → 'SM3dBend', ΔFaces +8, bbox moved (fold-class gate), ΔVol=0, survives reopen

_SW_SOLID_BODY = 0

# swFlangePositionTypes_e — harvest-sourced (docs/sw_api_full.json, confirmed
# W65 brief §2).  Same enum as edge_flange and miter_flange.
_BEND_POSITIONS: dict[str, int] = {
    "material_inside": 1,
    "material_outside": 2,
    "bend_outside": 3,
    "bend_center_line": 4,
    "bend_sharp": 5,
    "bend_tangent": 6,
}

# Below this, a volume delta is FP noise, not a fold (the hem v5 NO_OP showed
# ~1e-21 mm³ jitter; the real fold was +1103.84 mm³).
_VOL_EPS_MM3 = 1e-6


def _solid_bodies(doc: Any) -> list[Any] | None:
    """Solid bodies of *doc*; ``None`` on COM failure, ``[]`` when there are none.

    Robust to doc flavor: a dynamic dispatch resolves ``GetBodies2`` directly;
    a typed ``IModelDoc2`` proxy does not expose it, so fall back to a typed
    ``IPartDoc`` QI.
    """
    try:
        src = (
            doc if hasattr(doc, "GetBodies2")
            else typed(doc, "IPartDoc", module=wrapper_module())
        )
        bodies = src.GetBodies2(_SW_SOLID_BODY, True)
    except Exception:
        return None
    if not bodies:
        return []
    return list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]


def _metrics(doc: Any) -> tuple[int, float]:
    """(face_count, volume_mm³) over the doc's solid bodies; (0, 0.0) on failure."""
    bodies = _solid_bodies(doc)
    if not bodies:
        return 0, 0.0
    faces = 0
    vol_mm3 = 0.0
    for b in bodies:
        try:
            f = b.GetFaces()
            faces += len(f) if f else 0
        except Exception:
            pass
        try:
            mp = b.GetMassProperties(1.0)
            if mp and len(mp) > 3:
                vol_mm3 += float(mp[3]) * 1e9
        except Exception:
            pass
    return faces, vol_mm3


def _body_bbox(doc: Any) -> tuple[float, ...] | None:
    """Aggregate solid-body bounding box [xmin,ymin,zmin,xmax,ymax,zmax] in
    metres, or None on failure. The fold-class verify substrate: a bend is
    VOLUME-PRESERVING (folds existing material, adds no volume), so ΔVol≈0 is
    expected — the EFFECT is a bounding-box change as material rotates out of
    the original plane. W65 seat finding 2026-06-18 (InsertSheetMetal3dBend
    returned an 'SM3dBend' node + ΔFaces +8 with ΔVol=0 — a real bend the old
    ΔVol>0 gate falsely rejected)."""
    bodies = _solid_bodies(doc)
    if not bodies:
        return None
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    found = False
    for b in bodies:
        try:
            box = b.GetBodyBox()
        except Exception:
            continue
        if not box or len(box) < 6:
            continue
        found = True
        for i in range(3):
            lo[i] = min(lo[i], float(box[i]))
            hi[i] = max(hi[i], float(box[i + 3]))
    if not found:
        return None
    return (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])


def _bbox_changed(before: tuple | None, after: tuple | None, eps_m: float = 1e-6) -> bool:
    """True if the bounding box moved by more than eps in any coordinate."""
    if before is None or after is None or len(before) != 6 or len(after) != 6:
        return False
    return any(abs(a - b) > eps_m for a, b in zip(before, after))


def _enum(value: Any, table: dict[str, int], name: str) -> tuple[int | None, str | None]:
    """Map a string token (or accept a raw int) to its enum value, fail-closed."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None, f"{name} must be a string or int, got bool"
    if isinstance(value, int):
        return value, None
    if isinstance(value, str):
        key = value.strip().lower()
        if key in table:
            return table[key], None
        return None, f"{name} {value!r} not one of {sorted(table)}"
    return None, f"{name} must be a string or int, got {type(value).__name__}"


def create_sketched_bend(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Insert a sheet-metal sketched bend along a sketch line on a flat face.

    ``feature`` keys
        angle_deg : float        — bend angle (default 90)
        use_default_radius : bool — True ⇒ Radius is ignored (default True)
        radius_mm : float        — bend radius (default 1; used when
                                   use_default_radius is False)
        flip      : bool         — flip bend direction (default False)
        position  : str|int      — swFlangePositionTypes_e token or int
                                   (default "material_inside" = 1)

    ``target`` keys
        edge_ref : dict  — a serialized ``DurableEdgeRef`` naming the sketch
            line entity (resolved via ``resolve_edge_ref`` → ``select_entity``).
        sketch   : str   — OR the name of an on-face sketch feature (resolved
            via ``FeatureByName`` → ``Select2``).  At least one of ``edge_ref``
            or ``sketch`` is required.
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    position, err = _enum(
        feature.get("position", "material_inside"), _BEND_POSITIONS, "position",
    )
    if err:
        return False, err

    try:
        angle_rad = math.radians(float(feature.get("angle_deg", 90.0)))
        use_default_radius = bool(feature.get("use_default_radius", True))
        radius_m = float(feature.get("radius_mm", 1.0)) / 1000.0
        flip = bool(feature.get("flip", False))
    except (TypeError, ValueError) as exc:
        return False, f"numeric bend parameter invalid: {exc}"

    edge_ref_data = target.get("edge_ref")
    sketch_name = target.get("sketch")

    ref = None
    if isinstance(edge_ref_data, dict):
        try:
            ref = DurableEdgeRef.from_dict(edge_ref_data)
        except (TypeError, ValueError) as exc:
            return False, f"invalid edge_ref: {exc}"
    elif not isinstance(sketch_name, str) or not sketch_name:
        return False, "target must contain an 'edge_ref' dict or a 'sketch' string"

    entity = None
    if ref is not None:
        res = resolve_edge_ref(doc, ref)
        entity = getattr(res, "entity", None)
        if entity is None:
            return False, (
                f"edge_ref did not resolve to a live entity "
                f"({getattr(res, 'note', '')})"
            )
    else:
        try:
            feat_obj = doc.FeatureByName(sketch_name)
        except Exception:
            feat_obj = None
        if feat_obj is None:
            return False, f"sketch {sketch_name!r} not found in document"
        entity = feat_obj

    faces_before = _metrics(doc)[0]
    bbox_before = _body_bbox(doc)
    if faces_before == 0:
        return False, "document has no solid bodies to bend"

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    if ref is not None:
        if not select_entity(entity, mark=0):
            return False, "failed to select the resolved bend target"
    else:
        try:
            entity.Select2(False, 0)
        except Exception as exc:
            return False, f"failed to select sketch {sketch_name!r}: {exc!r}"

    try:
        fm = doc.FeatureManager
        pcba_null = VARIANT(pythoncom.VT_DISPATCH, None)
        fm.InsertSheetMetal3dBend(
            angle_rad, use_default_radius, radius_m, flip, position, pcba_null,
        )
        doc.ForceRebuild3(False)
    except Exception as exc:
        return False, f"InsertSheetMetal3dBend raised: {exc!r}"

    faces_after = _metrics(doc)[0]
    bbox_after = _body_bbox(doc)
    d_faces = faces_after - faces_before
    moved = _bbox_changed(bbox_before, bbox_after)
    # FOLD-CLASS gate (W65 2026-06-18): a bend is volume-preserving (ΔVol≈0
    # expected) — gating on ΔVol falsely rejected the real SM3dBend (ΔFaces +8,
    # ΔVol 0) on the seat. Honest effect = ΔFaces>0 AND a bounding-box change.
    if d_faces > 0 and moved:
        return True, None

    return False, (
        f"sketched_bend did not fold (delta_faces={d_faces}, "
        f"bbox_changed={moved}); the target must be a sketch line on a "
        f"flat sheet-metal face"
    )
