"""W62 — ``helix`` feature-add handler (registry seam).

Helix reference curve on a pre-selected sketch circle via dual-mode creation:

- **Mode-A** (primary): ``CreateDefinition(swFeatureNameID)`` →
  ``typed_qi(data, "IHelixFeatureData")`` → set Pitch / Revolution /
  Height / StartingAngle (deg→rad) / Clockwise → ``CreateFeature(data)``.
  The exact ``swFeatureNameID`` for helix is unspiked — probed as 36
  (``swFmHelix``); W0 resolves on the live seat.  QI may raise
  ``E_NOINTERFACE`` (the dual-mode doctrine wall).
- **Mode-B** (fallback): ``doc.InsertHelix(ConstantPitch, Reverse,
  Dimension, Clockwise, DefinedBy, Pitch, Revolution, Height, StartAngle,
  Diameter)`` — 10 args, returns void.  Exact bool semantics are fuzzy;
  W0 nails them on the seat.

Verify-the-EFFECT: a new Helix feature node materialized via
``FirstFeature`` / ``GetNextFeature`` walk (each node re-typed to
``IFeature`` per step — the W59 thread walk lesson).  No ΔVol expected —
a helix is a reference curve.
"""

from __future__ import annotations

import math
from typing import Any

from ..com.earlybind import EarlyBindError, typed_qi
from ..com.sw_type_info import wrapper_module

# Flipped to "GREEN" by W0 after spike_helix returns PASS on the seat.
# While "UNRUN", this module is dormant: the handler exists but is NOT
# registered in HANDLER_REGISTRY (W0 controls wiring in __init__.py).
SPIKE_STATUS = "UNRUN"

# swFeatureNameID_e probe for helix.  W0 resolves the exact value on the
# live seat (DLL reflection + CreateDefinition probe).  36 = swFmHelix per
# the SW const enum; if wrong the Mode-A QI will fail and Mode-B fires.
_SW_FM_HELIX = 36

# swHelixDefinedBy_e — pitch and revolution (the default parametrisation).
_SW_HELIX_DEFINED_BY_PITCH_AND_REVOLUTION = 0


def _feature_nodes(doc: Any) -> list[Any]:
    """Walk the feature tree via FirstFeature / GetNextFeature.

    Re-types each node to ``IFeature`` per step (the W59 thread walk
    lesson: the walk returns loosely-typed nodes that must be narrowed
    before calling ``GetTypeName``).
    """
    nodes: list[Any] = []
    try:
        mod = wrapper_module()
        feat = doc.FirstFeature()
        while feat is not None:
            try:
                from ..com.earlybind import typed

                typed_feat = typed(feat, "IFeature", module=mod)
                nodes.append(typed_feat)
            except Exception:
                nodes.append(feat)
            feat = feat.GetNextFeature()
    except Exception:
        pass
    return nodes


def _count_helices(doc: Any) -> int:
    """Count Helix feature nodes in the tree (type-name match)."""
    count = 0
    for node in _feature_nodes(doc):
        try:
            if node.GetTypeName() == "Helix":
                count += 1
        except Exception:
            pass
    return count


def create_helix(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Insert a helix reference curve on a pre-selected sketch circle.

    Tries Mode-A (``CreateDefinition`` → ``typed_qi(IHelixFeatureData)``
    → set params → ``CreateFeature``) first; on any failure falls back to
    Mode-B (``doc.InsertHelix`` with 10 args).  Returns
    ``(False, "<reason>")`` if both modes fail — never raises.

    ``feature`` keys
        pitch_mm       : float (>0) — helix pitch in mm; default 5
        revolutions    : float (>0) — number of revolutions; default 4
        start_angle_deg: float      — start angle in degrees; default 0
        clockwise      : bool       — True for CW; default False

    ``target`` keys
        sketch : str — name of the sketch with one circle (e.g. "Sketch2")
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    sketch = target.get("sketch")
    if not sketch or not isinstance(sketch, str):
        return False, "target must contain a non-empty 'sketch' name"

    try:
        pitch_mm = float(feature.get("pitch_mm", 5.0))
        revolutions = float(feature.get("revolutions", 4.0))
        start_angle_deg = float(feature.get("start_angle_deg", 0.0))
    except (TypeError, ValueError) as exc:
        return False, f"numeric helix parameter invalid: {exc}"

    if pitch_mm <= 0:
        return False, f"pitch_mm must be positive, got {pitch_mm}"
    if revolutions <= 0:
        return False, f"revolutions must be positive, got {revolutions}"

    clockwise = bool(feature.get("clockwise", False))
    pitch_m = pitch_mm / 1000.0
    start_angle_rad = math.radians(start_angle_deg)
    height_m = pitch_m * revolutions

    helices_before = _count_helices(doc)

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    # -- Mode-A: CreateDefinition → typed_qi(IHelixFeatureData) → CreateFeature
    mode_used = None
    try:
        fm = doc.FeatureManager
        mod = wrapper_module()
        data = fm.CreateDefinition(_SW_FM_HELIX)
        if data is not None:
            fd = typed_qi(data, "IHelixFeatureData", module=mod)
            fd.DefinedBy = _SW_HELIX_DEFINED_BY_PITCH_AND_REVOLUTION
            fd.Pitch = pitch_m
            fd.Revolution = revolutions
            fd.Height = height_m
            fd.StartingAngle = start_angle_rad
            fd.Clockwise = clockwise
            doc.SelectByID(sketch, "SKETCH", 0, 0, 0)
            fm.CreateFeature(data)
            mode_used = "A"
    except (EarlyBindError, Exception):
        pass

    if mode_used == "A" and _count_helices(doc) > helices_before:
        return True, None

    # -- Mode-B: legacy doc.InsertHelix (10 args, returns void)
    try:
        doc.InsertHelix(
            True,           # ConstantPitch
            False,          # Reverse
            False,          # Dimension
            clockwise,      # Clockwise
            _SW_HELIX_DEFINED_BY_PITCH_AND_REVOLUTION,  # DefinedBy
            pitch_m,        # Pitch (m)
            revolutions,    # Revolution
            height_m,       # Height (m)
            start_angle_rad,  # StartAngle (rad)
            0.0,            # Diameter (0 = use sketch circle)
        )
        mode_used = "B"
    except Exception:
        pass

    if mode_used == "B" and _count_helices(doc) > helices_before:
        return True, None

    return False, (
        "both Mode-A (CreateDefinition/IHelixFeatureData) and "
        "Mode-B (InsertHelix) failed to produce a Helix feature node"
    )


# ---------------------------------------------------------------------------
# Gated self-registration (W0 flips SPIKE_STATUS + adds import in __init__)
# ---------------------------------------------------------------------------

if SPIKE_STATUS == "GREEN":
    from . import HANDLER_REGISTRY

    HANDLER_REGISTRY["helix"] = create_helix
