"""W62 — ``helix`` feature-add handler (registry seam).

Helix reference curve on a pre-selected sketch circle.

  **Mode-A (QUARANTINED — documented unreachable for CREATION)**: the SW2024
  swconst harvest exposes NO ``swFeatureNameID_e`` for helix at all (DLL
  reflection 2026-06-17). The worker-authored probe id=36 (``swFmHelix``)
  was a guess; the live seat returns None from ``CreateDefinition(36)``.
  Like composite, ``IHelixFeatureData`` is edit-only via
  ``IFeature.GetDefinition()`` on an existing helix node; no creation
  enum exists. Mode-A is a no-op stub.

  **Mode-B (legacy, operative path)**: select the sketch (Extension.SelectByID2
  with `"SKETCH"` type), then ``doc.InsertHelix(ConstantPitch, Reverse,
  Dimension, Clockwise, DefinedBy, Pitch, Revolution, Height, StartAngle,
  Diameter)`` — 10-arg method returning void. Verify via the
  ``IFeatureManager.GetFeatures(False)`` type-name filter for "Helix".

Verify-the-EFFECT: a new Helix feature node materialized via
``IFeatureManager.GetFeatures(False)`` (each node exposes ``GetTypeName``
directly; some surfaces resolve it as a property — callable-or-property
guard handles both). No ΔVol expected — a helix is a reference curve.

Why GetFeatures(False) and not FirstFeature: ``IModelDoc2.FirstFeature``
is unreachable on the raw late-bound doc out-of-process (com_error
-2147352573 "Member not found" — proven on the W62 composite seat fire,
2026-06-17). ``IFeatureManager.GetFeatures(False)`` returns a flat tuple
that IS reachable (seat-proven: 25 features on a fresh block).
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pythoncom
import win32com.client.dynamic as _w32dyn
from win32com.client import VARIANT

from . import verify

logger = logging.getLogger("ai_sw_bridge.features.helix")

# Flipped to "GREEN" by W0 after spike_helix returns PASS on the seat.
SPIKE_STATUS = (
    "GREEN"  # Mode-B fired clean + survived save→reopen on the live seat (W62)
)

# Verify class (W67): CURVE — witnessed by a Helix-node count delta. NOTE
# (Phase-3 finding): node presence is trusted without a geometric scalar
# (pitch/length); hardening the CURVE witness is W67 Phase 3.
VERIFY_CLASS = verify.FeatureClass.CURVE

# swHelixDefinedBy_e — pitch and revolution (the default parametrisation).
_SW_HELIX_DEFINED_BY_PITCH_AND_REVOLUTION = 0


def _latebound(com_obj: Any) -> Any:
    """Re-wrap a COM proxy as LATE-BOUND (``win32com.client.dynamic.Dispatch``).

    The ref_axis / spiral binding trap: the disk-transaction path opens docs
    TYPED (``mutate._open_doc_typed``). On a TYPED ``IModelDocExtension`` proxy,
    ``SelectByID2``'s arg-8 ICallout ``VARIANT(VT_DISPATCH, None)`` raises
    ``TypeError('The Python instance can not be converted to a COM object')``,
    and ``InsertHelix`` is likewise late-bound-only. A late-bound re-wrap
    marshals both regardless of how the doc was opened. Seam so offline tests
    patch to identity. PROVEN broken through the typed transaction
    (probe_curve_lanes_typed_txn 2026-06-24, helix dry_run reproduced the exact
    TypeError) — fixed here per the ref_axis precedent (commit 794a7c4) and the
    spiral lane (features/spiral._latebound).
    """
    return _w32dyn.Dispatch(com_obj)


def _count_helices(doc: Any) -> int:
    """Count Helix feature nodes in the tree (exact type-name match). Delegates
    to the W67 verify substrate."""
    return verify.count_nodes_by_type(doc, ("Helix",), match="exact")


def _curve_length_mm(node: Any) -> float | None:
    """Arc length (mm) of the new helix curve node, or None if unreadable.
    Delegates to the W67 verify substrate (seat-proven IReferenceCurve.
    GetSegments → IEdge.GetCurve → ICurve.GetLength); offline tests patch
    this shim."""
    return verify.curve_length_mm(node)


def create_helix(
    doc: Any,
    feature: dict,
    target: dict,
) -> tuple[bool, str | None]:
    """Insert a helix reference curve on a pre-selected sketch circle.

    Mode-A is QUARANTINED (no creation enum exists — see module docstring).
    The handler fires Mode-B only: select the sketch via Extension.SelectByID2,
    then ``doc.InsertHelix`` (10-arg, void return — verify via
    ``GetFeatures(False)`` Helix-count delta).

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

    # Late-bound re-wrap: the typed transaction doc rejects the SelectByID2
    # VARIANT callout AND InsertHelix marshaling (ref_axis / spiral binding
    # trap — PROVEN broken through the typed transaction, probe_curve_lanes_
    # typed_txn 2026-06-24). Both calls go through _latebound.
    ldoc = _latebound(doc)

    # Select the sketch on the model. Extension.SelectByID2 with a VARIANT
    # null callout is the W60/W61 selection-proven idiom for named features.
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    try:
        null_callout = VARIANT(pythoncom.VT_DISPATCH, None)
        sel_ok = _latebound(doc.Extension).SelectByID2(
            sketch,
            "SKETCH",
            0.0,
            0.0,
            0.0,
            False,
            0,
            null_callout,
            0,
        )
        logger.warning(
            "[helix] Extension.SelectByID2(%r,'SKETCH') -> %r", sketch, sel_ok
        )
        if not sel_ok:
            return False, f"could not select sketch {sketch!r}"
    except Exception as e:
        logger.warning("[helix] SelectByID2 RAISED: %r", e)
        return False, f"sketch selection raised: {e}"

    # Mode-B: doc.InsertHelix (legacy, 10 args, returns void).
    try:
        ldoc.InsertHelix(
            True,  # ConstantPitch
            False,  # Reverse
            False,  # Dimension
            clockwise,  # Clockwise
            _SW_HELIX_DEFINED_BY_PITCH_AND_REVOLUTION,  # DefinedBy
            pitch_m,  # Pitch (m)
            revolutions,  # Revolution
            height_m,  # Height (m)
            start_angle_rad,  # StartAngle (rad)
            0.0,  # Diameter (0 = use sketch circle)
        )
        logger.warning("[helix] InsertHelix called (void return)")
    except Exception as e:
        logger.warning("[helix] InsertHelix RAISED: %r", e)
        return False, f"InsertHelix raised: {e}"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    helices_after = _count_helices(doc)
    d_nodes = helices_after - helices_before
    if d_nodes <= 0:
        return False, (
            "Mode-A QUARANTINED (no creation enum for helix in swconst harvest); "
            "Mode-B (InsertHelix) called without exception but no Helix node "
            "materialized (selection / unit / arg-shape wall)"
        )

    # CURVE geometric gate (W67 P3b): a node ALONE is the W42 ghost trap — the
    # helix must carry real arc length (seat-proven IReferenceCurve.GetSegments
    # → ICurve.GetLength).
    new_node = verify.newest_node_by_type(doc, ("Helix",), match="exact")
    length_mm = _curve_length_mm(new_node)
    if verify.gate_curve(d_nodes, length_mm):
        return True, None
    return False, (
        f"a Helix node materialized but carries no readable arc length "
        f"(curve_length_mm={length_mm}) — geometric ghost, not a real curve"
    )


# ---------------------------------------------------------------------------
# Gated self-registration (W0 flips SPIKE_STATUS + adds import in __init__)
# ---------------------------------------------------------------------------

if SPIKE_STATUS == "GREEN":
    from . import HANDLER_REGISTRY

    HANDLER_REGISTRY["helix"] = create_helix
