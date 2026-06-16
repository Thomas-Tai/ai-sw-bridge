"""W59 — ``hem`` feature-add handler (registry seam).

Sheet-metal hem at a durable boundary edge via the legacy
``IFeatureManager.InsertSheetMetalHem`` (9-arg, memid 91). The modern
``CreateDefinition`` path is E_NOINTERFACE for hem (W55-C proved that wall),
so the legacy route is the only one — and it is GENERATIVE, proven on the
live seat 2026-06-16 (``spikes/v0_2x/spike_hem_v5.py`` → faces +8, vol
+1103.84 mm³, surviving save→reopen). TWO locks had to clear, both baked in:

  1. **PCBA null marshaling** — the 9th arg (``PCBA``, a CustomBendAllowance
     pointer, ``VT_PTR``/raw_vt 26) is coerced with
     ``VARIANT(VT_DISPATCH, None)`` (the edge_flange null recipe), which
     clears the ``DISP_E_TYPEMISMATCH`` that the bare-``None`` path hit.
     *(Supersedes the ``bc5c849`` "mode-B wall" draft, which pushed a raw
     ``VT_UNKNOWN`` ``InvokeTypes`` that the server silently no-op'd.)*
  2. **Topological precondition** — the target must be a valid linear
     sheet-metal BOUNDARY edge. A 2mm thickness edge → silent NO_OP. The
     caller passes a durable ``edge_ref`` (selected upstream as the
     major-face perimeter), resolved here via the proven persist→fingerprint
     tier hierarchy (``selection.live.resolve_edge_ref``).

Verify-the-EFFECT (W21/W42 doctrine): success = face count UP **and** volume
delta ≠ 0. A non-None feature return, or a face-count delta alone, is a ghost
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

# Spike gate: GREEN since spike_hem_v5 (2026-06-16, feat/w59-hem). The
# registry import in features/__init__.py is unconditional now that the
# recipe is seat-proven (faces +8 / vol +1103.84 mm³ / survives reopen).
SPIKE_STATUS = "GREEN"

_SW_SOLID_BODY = 0

# swHemTypes_e / swHemPositionTypes_e — O1-sourced (W55 swconst.tlb dump).
_HEM_TYPES: dict[str, int] = {
    "open": 0, "closed": 1, "teardrop": 2, "rolled": 3, "double": 4,
}
_HEM_POSITIONS: dict[str, int] = {"inside": 0, "outside": 1}

# Below this, a volume delta is FP noise, not a fold (the v5 NO_OP showed
# ~1e-21 mm³ jitter; the real fold was +1103.84 mm³).
_VOL_EPS_MM3 = 1e-6


def _solid_bodies(doc: Any) -> list[Any] | None:
    """Solid bodies of *doc*; ``None`` on COM failure, ``[]`` when there are none.

    Robust to doc flavor: a dynamic dispatch resolves ``GetBodies2`` directly;
    a typed ``IModelDoc2`` proxy does not expose it, so fall back to a typed
    ``IPartDoc`` QI (the bc5c849 draft's one sound idea).
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


def create_hem(doc: Any, feature: dict, target: dict) -> tuple[bool, str | None]:
    """Insert a sheet-metal hem at a durable boundary edge. Fail-closed.

    ``feature`` keys
        hem_type : str|int  — open|closed|teardrop|rolled|double (default closed)
        position : str|int  — inside|outside (default inside)
        reverse  : bool     — default False
        length_mm    : float (>0)  — hem length (open/closed); default 10
        gap_mm       : float        — gap (open only); default 0
        angle_deg    : float        — hem angle (teardrop/rolled); default 0
        radius_mm    : float        — hem radius (teardrop/rolled); default 0
        miter_gap_mm : float        — miter gap; default 1.0

    ``target`` keys
        edge_ref : dict  — a serialized ``DurableEdgeRef`` (from an observe
            call) naming the linear sheet-metal boundary edge to fold.
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    hem_type, err = _enum(feature.get("hem_type", "closed"), _HEM_TYPES, "hem_type")
    if err:
        return False, err
    position, err = _enum(feature.get("position", "inside"), _HEM_POSITIONS, "position")
    if err:
        return False, err
    reverse = bool(feature.get("reverse", False))

    try:
        length_m = float(feature.get("length_mm", 10.0)) / 1000.0
        gap_m = float(feature.get("gap_mm", 0.0)) / 1000.0
        angle_rad = math.radians(float(feature.get("angle_deg", 0.0)))
        radius_m = float(feature.get("radius_mm", 0.0)) / 1000.0
        miter_gap_m = float(feature.get("miter_gap_mm", 1.0)) / 1000.0
    except (TypeError, ValueError) as exc:
        return False, f"numeric hem parameter invalid: {exc}"
    if length_m <= 0:
        return False, f"length_mm must be positive, got {feature.get('length_mm')!r}"

    edge_ref_data = target.get("edge_ref")
    if not isinstance(edge_ref_data, dict):
        return False, "target must contain an 'edge_ref' dict"
    try:
        ref = DurableEdgeRef.from_dict(edge_ref_data)
    except (TypeError, ValueError) as exc:
        return False, f"invalid edge_ref: {exc}"

    res = resolve_edge_ref(doc, ref)
    edge = getattr(res, "entity", None)
    if edge is None:
        return False, f"edge_ref did not resolve to a live edge ({getattr(res, 'note', '')})"

    faces_before, vol_before = _metrics(doc)
    if faces_before == 0:
        return False, "document has no solid bodies to hem"

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    if not select_entity(edge, mark=0):
        return False, "failed to select the resolved hem edge"

    try:
        fm = doc.FeatureManager
        pcba_null = VARIANT(pythoncom.VT_DISPATCH, None)  # Tactic 1 (v5-proven)
        fm.InsertSheetMetalHem(
            hem_type, position, reverse,
            length_m, gap_m, angle_rad, radius_m, miter_gap_m,
            pcba_null,
        )
        doc.ForceRebuild3(False)
    except Exception as exc:
        return False, f"InsertSheetMetalHem raised: {exc!r}"

    faces_after, vol_after = _metrics(doc)
    d_faces = faces_after - faces_before
    d_vol = vol_after - vol_before
    if d_faces > 0 and abs(d_vol) > _VOL_EPS_MM3:
        return True, None

    # A hem node may exist yet add no geometry (W42 ghost) — NOT success.
    return False, (
        f"hem did not fold (delta_faces={d_faces}, delta_vol_mm3={d_vol:.3f}); "
        f"the edge_ref must name a linear sheet-metal boundary edge, not a "
        f"thickness or interior edge"
    )
