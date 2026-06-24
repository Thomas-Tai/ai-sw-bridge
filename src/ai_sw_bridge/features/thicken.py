"""W66 — ``thicken`` feature-add handler (registry seam).

Surface-to-solid bridge: thickens a pre-selected **sheet body** into a solid
via ``IFeatureManager.FeatureBossThicken`` (7-arg → Feature).  The modern
``CreateDefinition`` path has no ``IThickenFeatureData`` creation enum in the
SW2024 swconst harvest (the interface is edit-only via
``IFeature.GetDefinition``), so Mode-B (legacy) is the only route.

**Reflected sig** (docs/sw_api_full.md line 8325, arg count W0-verified):

    FeatureBossThicken(Thickness:Double, Direction:Int32, FaceIndex:Int32,
                       FillVolume:Boolean, Merge:Boolean,
                       UseFeatScope:Boolean, UseAutoSelect:Boolean) -> Feature

``FeatureBossThicken2`` is the 4-arg Void variant — we use the 7-arg Feature
form (per the W66 brief §4).

No VARIANT-null marshaling is needed: all 7 args are primitives (Double,
Int32, Boolean) — no object-pointer / SAFEARRAY slots.

**Verify-the-EFFECT (additive gate, REVERTS TO VOLUME):** thicken consumes a
sheet body into a solid, so the surface-create gate (ΔSheetBodies ≥ +1) is
WRONG here — sheet body count may DECREASE.  The correct witness is:

    ΔVol > 0  ∧  ΔSolidBodies ≥ +1

(the brief §0.1 table; same as boss_extrude additive verify).  A Feature
return alone is the W21/W42 ghost trap and is NOT reported as success.

**Fixture (chained):** thicken needs a surface body to consume — the spike
creates one first (``InsertOffsetSurface`` or ``InsertPlanarRefSurface`` on a
block), selects that sheet body, then fires the handler.
"""

from __future__ import annotations

from typing import Any

from ..selection._ref import DurableRef
from ..selection.live import resolve_manifest_face, select_entity
from . import verify

# Spike gate: UNFIRED until W0 fires on the live seat.
SPIKE_STATUS = "UNFIRED"

# Verify class (W67): surface→solid bridge — volume appears AND a solid body
# materializes.  WALLED OOP (FeatureBossThicken no-ops across COM even on a
# standalone surface); see docs/DEFERRED.md.  Handler stays UNFIRED/unregistered.
VERIFY_CLASS = verify.FeatureClass.SURFACE_TO_SOLID

# swThickenDirectionType_e — harvest-sourced (docs/sw_api_full.json).
_THICKEN_DIRECTIONS: dict[str, int] = {
    "side1": 0,
    "side2": 1,
    "both": 2,
}


def _sheet_bodies(doc: Any) -> list[Any] | None:
    """Sheet bodies of *doc*. Delegates to the W67 verify substrate
    (``visible_only=False`` — Phase-3 normalized to count all bodies; thicken
    historically used ``True`` here, the now-resolved visibility drift)."""
    return verify.sheet_bodies(doc)


def _surface_area(body: Any) -> float:
    """Surface area of a single body in mm²; 0.0 on failure.

    AREA is to surfaces what VOLUME is to solids (the W66 §0.1 doctrine).
    Used by the surface-CREATE lanes (planar_surface, offset_surface) as the
    anti-ghost witness; included here for cross-lane utility.
    """
    try:
        mp = body.GetMassProperties(1.0)
        if mp and len(mp) > 3:
            return float(mp[3]) * 1e6
    except Exception:
        pass
    return 0.0


def _solid_body_count(doc: Any) -> int:
    """Count of solid bodies in *doc*. Delegates to the W67 verify substrate
    (``visible_only=False`` — Phase-3 normalized)."""
    return verify.solid_body_count(doc)


def _metrics_solid(doc: Any) -> tuple[int, float]:
    """(face_count, volume_mm³) over solid bodies. Delegates to the W67 verify
    substrate (``visible_only=False``) — the additive gate thicken reverts to
    after consuming the sheet body."""
    return verify.solid_metrics(doc)


def _enum(
    value: Any, table: dict[str, int], name: str
) -> tuple[int | None, str | None]:
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


def create_thicken(
    doc: Any,
    feature: dict,
    target: dict,
) -> tuple[bool, str | None]:
    """Thicken a surface (sheet) body into a solid.  Fail-closed.

    ``feature`` keys
        thickness_mm : float (>0) — thicken depth; default 2
        direction    : str|int   — side1|side2|both (default "side1")

    ``target`` keys
        face_ref : dict — a serialized ``DurableRef`` (from an observe call)
            naming a face whose parent sheet body will be thickened.
            Resolved via ``resolve_manifest_face`` → ``select_entity``.
        If omitted, the first available sheet body is used.
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    direction, err = _enum(
        feature.get("direction", "side1"),
        _THICKEN_DIRECTIONS,
        "direction",
    )
    if err:
        return False, err

    try:
        thickness_m = float(feature.get("thickness_mm", 2.0)) / 1000.0
    except (TypeError, ValueError) as exc:
        return False, f"numeric thicken parameter invalid: {exc}"
    if thickness_m <= 0:
        return False, (
            f"thickness_mm must be positive, got {feature.get('thickness_mm')!r}"
        )

    sheets = _sheet_bodies(doc)
    if not sheets:
        return False, "document has no sheet bodies to thicken"

    face_ref_data = target.get("face_ref")
    if isinstance(face_ref_data, dict):
        try:
            ref = DurableRef.from_dict(face_ref_data)
        except (TypeError, ValueError) as exc:
            return False, f"invalid face_ref: {exc}"
        res = resolve_manifest_face(doc, ref)
        entity = getattr(res, "entity", None)
        if entity is None:
            return False, (
                f"face_ref did not resolve to a live face "
                f"({getattr(res, 'note', '')})"
            )
    else:
        entity = sheets[0]

    vol_before, _ = _metrics_solid(doc)
    solids_before = _solid_body_count(doc)

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass
    if not select_entity(entity, mark=0):
        return False, "failed to select the target sheet body"

    try:
        fm = doc.FeatureManager
        # NOTE (W66 DEFERRED): FeatureBossThicken no-ops OUT-OF-PROCESS even
        # with a standalone surface + face selection + various flag combos —
        # surface→solid bridging refuses across the COM boundary. See
        # docs/DEFERRED.md. Handler kept UNFIRED/unregistered; this is the
        # authored shape, not a shipping path.
        fm.FeatureBossThicken(
            thickness_m,
            direction,
            0,
            False,
            False,
            False,
            True,
        )
        doc.ForceRebuild3(False)
    except Exception as exc:
        return False, f"FeatureBossThicken raised: {exc!r}"

    vol_after, _ = _metrics_solid(doc)
    solids_after = _solid_body_count(doc)
    d_vol = vol_after - vol_before
    d_solids = solids_after - solids_before
    # ADDITIVE gate (surface→solid bridge): the sheet body was consumed into
    # a solid, so ΔVol > 0 AND ΔSolidBodies ≥ +1 (the brief §0.1 table).
    if verify.gate_surface_to_solid(d_vol, d_solids):
        return True, None

    return False, (
        f"thicken did not produce a solid "
        f"(delta_vol_mm3={d_vol:.3f}, delta_solids={d_solids}); "
        f"the surface body must be a valid target for thickening"
    )
