"""``spiral`` feature-add handler (registry seam) — curve sibling of helix.

A flat (planar) Archimedean spiral via the SAME legacy ``IModelDoc2.InsertHelix``
call as the helix lane, with two seat-proven differences (probe_spiral, live
SW2024 SP1, 2026-06-23):

  1. **DefinedBy = 3** (``swHelixDefinedBy_e.swHelixDefinedBySpiral``). The
     swept sweep over 0..5 showed db 0/1/2/4/5 all materialize a *helix* node;
     only db=3 is the flat spiral.
  2. **ConstantPitch = False** (arg 1). With ConstantPitch=True the spiral
     SILENTLY no-ops (a spiral has a *variable* radius, so constant-pitch is a
     degenerate combination the kernel refuses without error). ConstantPitch=
     False materializes it. This is the whole difference from the helix recipe.

Closed-form curve (``r = a + bθ``) → materialize-class per the boundary law;
not a kernel-traversal wall.

**Binding (the ref_axis trap, applied):** the disk-transaction path opens docs
TYPED (``mutate._open_doc_typed``); ``Extension.SelectByID2``'s arg-8 ICallout
``VARIANT(VT_DISPATCH, None)`` does NOT marshal on a typed proxy (raises
``TypeError: The Python instance can not be converted to a COM object``), and
``InsertHelix`` is likewise late-bound-only. Both calls go through
:func:`_latebound` (``win32com.client.dynamic.Dispatch``) so they marshal
regardless of how the doc was opened. The node-count/verify reads stay on the
passed ``doc`` (they share the one live document). Isolated as a seam so offline
tests patch it to identity.

Verify-the-EFFECT: a new 'Helix'-type node (a spiral is a Helix feature in SW)
carrying real arc length — node presence ALONE is the W42 ghost trap, so the
CURVE gate also requires a readable ``ICurve.GetLength``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pythoncom
import win32com.client.dynamic as _w32dyn
from win32com.client import VARIANT

from . import verify

logger = logging.getLogger("ai_sw_bridge.features.spiral")

SPIKE_STATUS = "GREEN"  # seat-proven 2026-06-23 (probe_spiral: db=3 + ConstantPitch=False materializes a flat spiral; PAE drives propose->dry_run->commit)

VERIFY_CLASS = verify.FeatureClass.CURVE

# swHelixDefinedBy_e — 3 = spiral (seat-confirmed: only db=3 of 0..5 is flat).
_SW_HELIX_DEFINED_BY_SPIRAL = 3


def _latebound(com_obj: Any) -> Any:
    """Re-wrap a COM proxy as LATE-BOUND (``win32com.client.dynamic.Dispatch``).

    ``InsertHelix`` and ``Extension.SelectByID2``'s VARIANT(VT_DISPATCH,None)
    callout marshal on a late-bound proxy but NOT on the makepy-typed one the
    transaction path produces (``mutate._open_doc_typed``). Seam so offline
    tests can patch to identity and still drive the fakes. See ref_axis
    (``features.ref_geometry._latebound``) for the same fix.
    """
    return _w32dyn.Dispatch(com_obj)


def _count_spirals(doc: Any) -> int:
    """Count Helix-type feature nodes (a spiral is a Helix feature in SW)."""
    return verify.count_nodes_by_type(doc, ("Helix",), match="exact")


def _curve_length_mm(node: Any) -> float | None:
    """Arc length (mm) of the new spiral curve node, or None if unreadable.
    Delegates to the W67 verify substrate; offline tests patch this shim."""
    return verify.curve_length_mm(node)


def create_spiral(
    doc: Any, feature: dict, target: dict,
) -> tuple[bool, str | None]:
    """Insert a flat spiral reference curve on a pre-selected sketch circle.

    ``feature`` keys
        pitch_mm       : float (>0) — radial growth per revolution in mm; default 5
        revolutions    : float (>0) — number of revolutions; default 3
        start_angle_deg: float      — start angle in degrees; default 0
        clockwise      : bool       — True for CW; default False

    ``target`` keys
        sketch : str — name of the sketch with one circle (the start radius)
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
        revolutions = float(feature.get("revolutions", 3.0))
        start_angle_deg = float(feature.get("start_angle_deg", 0.0))
    except (TypeError, ValueError) as exc:
        return False, f"numeric spiral parameter invalid: {exc}"

    if pitch_mm <= 0:
        return False, f"pitch_mm must be positive, got {pitch_mm}"
    if revolutions <= 0:
        return False, f"revolutions must be positive, got {revolutions}"

    clockwise = bool(feature.get("clockwise", False))
    pitch_m = pitch_mm / 1000.0
    start_angle_rad = math.radians(start_angle_deg)
    height_m = pitch_m * revolutions  # ignored for spiral; nonzero is safe

    spirals_before = _count_spirals(doc)

    # Late-bound re-wrap: the typed transaction doc rejects the SelectByID2
    # VARIANT callout AND InsertHelix marshaling (ref_axis binding trap).
    ldoc = _latebound(doc)
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    try:
        null_callout = VARIANT(pythoncom.VT_DISPATCH, None)
        sel_ok = _latebound(doc.Extension).SelectByID2(
            sketch, "SKETCH", 0.0, 0.0, 0.0, False, 0, null_callout, 0,
        )
        if not sel_ok:
            return False, f"could not select sketch {sketch!r}"
    except Exception as e:  # noqa: BLE001
        return False, f"sketch selection raised: {e}"

    # InsertHelix in SPIRAL mode: ConstantPitch=False (arg 1) + DefinedBy=3.
    try:
        ldoc.InsertHelix(
            False,                          # ConstantPitch — MUST be False for spiral
            False,                          # Reverse
            False,                          # Dimension
            clockwise,                      # Clockwise
            _SW_HELIX_DEFINED_BY_SPIRAL,    # DefinedBy = 3 (spiral)
            pitch_m,                        # Pitch (m) — radial growth per rev
            revolutions,                    # Revolution
            height_m,                       # Height (m) — ignored for spiral
            start_angle_rad,                # StartAngle (rad)
            0.0,                            # Diameter (0 = use sketch circle)
        )
    except Exception as e:  # noqa: BLE001
        return False, f"InsertHelix (spiral) raised: {e}"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    spirals_after = _count_spirals(doc)
    d_nodes = spirals_after - spirals_before
    if d_nodes <= 0:
        return False, (
            "InsertHelix (DefinedBy=3 spiral, ConstantPitch=False) called without "
            "exception but no spiral node materialized (selection / arg-shape wall)"
        )

    # CURVE geometric gate (W42 ghost-trap guard): a node alone is not enough —
    # the spiral must carry real arc length.
    new_node = verify.newest_node_by_type(doc, ("Helix",), match="exact")
    length_mm = _curve_length_mm(new_node)
    if verify.gate_curve(d_nodes, length_mm):
        return True, None
    return False, (
        f"a spiral (Helix) node materialized but carries no readable arc length "
        f"(curve_length_mm={length_mm}) — geometric ghost, not a real curve"
    )


# ---------------------------------------------------------------------------
# Gated self-registration (W0 flips SPIKE_STATUS to GREEN after the seat PAE)
# ---------------------------------------------------------------------------

if SPIKE_STATUS == "GREEN":
    from . import HANDLER_REGISTRY

    HANDLER_REGISTRY["spiral"] = create_spiral
