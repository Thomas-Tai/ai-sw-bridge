"""W66 — ``knit`` feature-add handler (registry seam, BOSS FIGHT lane).

Surface aggregation: sews/knits two or more adjacent sheet bodies into a
single sheet (or solid, with ``try_to_form_solid=True``) via
``IFeatureManager.InsertSewRefSurface`` (5-arg → Feature).

**Reflected sig** (CHM InsertSewRefSurface, W0 arg-count verified):

    InsertSewRefSurface(UseGapFilters:Boolean, TryToFormSolid:Boolean,
                        MergeEntities:Boolean, KnitTolerance:Double,
                        MaxValueForGapRange:Double) -> Feature

Mode-B is the operative path.  Mode-A (``ISurfaceKnitFeatureData`` via
``CreateDefinition → typed_qi → CreateFeature``) is a possible future
probe but NOT exercised here — the ``ISurfaceKnitFeatureData`` interface
is edit-only on this SW build (W62 quarantine doctrine: never speculative-
probe random IDs).

**Selection:** the CHM VB6 recipe requires ``IModelDocExtension.SelectByID2``
with **mark=1** for every body — ``select_entity`` (``IEntity.Select2``)
cannot express this mark, so the handler routes selection through the
model-doc extension directly with ``VARIANT(VT_DISPATCH, None)`` callout
null (the §0.2 marshaling doctrine).

**Verify-the-EFFECT (AGGREGATION gate — INVERTED):** knit MERGES sheet
bodies, so the surface-CREATE gate (ΔSheetBodies ≥ +1) is WRONG here —
sheet-body count goes DOWN.  The correct witnesses are:

  Surface-knit mode (``try_to_form_solid=False``, default):
    ΔSheetBodies < 0  (consumed ≥1 sheet body)
    total area > 0    (knit body has positive area — anti-ghost)

  Solid-knit mode (``try_to_form_solid=True``):
    ΔSheetBodies < 0  (sheets consumed)
    ΔSolidBodies ≥ +1 (solid materialized)
    ΔVol > 0          (anti-ghost volume witness)

Gating on "≥1 new body" is WRONG for knit (the W65 inverse false-fail).
"""

from __future__ import annotations

import logging
from typing import Any

from . import verify

logger = logging.getLogger("ai_sw_bridge.features.knit")

SPIKE_STATUS = "GREEN"  # seat-proven W0 2026-06-18: InsertSewRefSurface merged sheets 2->1 (ΔSheetBodies=-1, aggregation gate), area 1900mm² conserved, survives reopen

try:
    import pythoncom
    from win32com.client import VARIANT
except ImportError:
    pythoncom = None
    VARIANT = None

# Verify class (W67): surface AGGREGATION (INVERTED) — sheet-body count goes
# DOWN as bodies are sewn; the surface-knit path also uses gate_surface_to_solid.
VERIFY_CLASS = verify.FeatureClass.SURFACE_AGGREGATE

# CHM-sourced knit-tolerance bounds (metres).
_TOL_LOWER_M = 1e-7  # 0.0001 mm
_TOL_UPPER_M = 1e-4  # 0.1 mm


def _sheet_body_count(doc: Any) -> int:
    """Sheet-body count. Delegates to the W67 verify substrate;
    ``visible_only=False`` preserves the historical surface-lane arg."""
    return verify.sheet_body_count(doc, visible_only=False)


def _total_sheet_area_mm2(doc: Any) -> float:
    """Total sheet-body face area (mm²). Delegates to the W67 verify substrate."""
    return verify.sheet_area_mm2(doc, visible_only=False)


def _solid_body_count(doc: Any) -> int:
    """Solid-body count. Delegates to the W67 verify substrate
    (``visible_only=False`` — knit always used False; W67 Phase 3 made it the
    normalized default for all lanes)."""
    return verify.solid_body_count(doc)


def _solid_volume_mm3(doc: Any) -> float:
    """Total solid volume (mm³). Delegates to the W67 verify substrate
    (``visible_only=False`` — Phase-3 normalized default)."""
    return verify.solid_volume_mm3(doc)


def _null_disp() -> Any:
    """ICallout null as a typed VARIANT (the §0.2 marshaling doctrine)."""
    if VARIANT is None or pythoncom is None:
        return None
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _select_bodies_for_knit(
    doc: Any,
    body_refs: list[dict],
) -> tuple[bool, str | None]:
    """Pre-select sheet bodies via Extension.SelectByID2 with mark=1.

    Each entry in *body_refs* must carry ``name`` (the feature/body name
    string) and optionally ``type`` (``"BODYFEATURE"`` or ``"SURFACEBODY"``;
    default ``"SURFACEBODY"``).

    The first body is selected with ``Append=False``; subsequent bodies
    with ``Append=True`` — matching the CHM VB6 recipe.
    """
    ext = doc.Extension
    null_callout = _null_disp()

    for i, ref in enumerate(body_refs):
        name = ref.get("name") if isinstance(ref, dict) else None
        if not isinstance(name, str) or not name:
            return False, f"body_refs[{i}] must contain a non-empty 'name' string"
        sel_type = "SURFACEBODY"
        if isinstance(ref, dict) and isinstance(ref.get("type"), str):
            sel_type = ref["type"]

        append = i > 0
        try:
            ok = ext.SelectByID2(
                name,
                sel_type,
                0,
                0,
                0,
                append,
                1,
                null_callout,
                0,
            )
        except Exception as exc:
            return False, f"SelectByID2({name!r}, {sel_type!r}) raised: {exc!r}"
        if not ok:
            return False, (
                f"SelectByID2({name!r}, {sel_type!r}) returned False — "
                f"body feature not found or not selectable"
            )
    return True, None


def _select_all_sheet_bodies(doc: Any) -> tuple[bool, str | None]:
    """Auto-discover and select all sheet bodies for knit (fallback path).

    Walks ``GetBodies2(swSheetBody)`` and selects each body by persist
    reference via ``select_entity`` with mark=1 — the CHM requires mark=1
    for InsertSewRefSurface, so we fall back to SelectByID2 with the
    body's ``Name`` property when available.
    """
    bodies = verify.sheet_bodies(doc, visible_only=False)
    if not bodies or len(bodies) < 2:
        return (
            False,
            f"need ≥2 sheet bodies to knit, found {len(bodies) if bodies else 0}",
        )

    ext = doc.Extension
    null_callout = _null_disp()

    for i, body in enumerate(bodies):
        body_name = None
        try:
            nm = body.Name
            body_name = nm() if callable(nm) else str(nm)
        except Exception:
            pass
        if not body_name:
            return False, (
                f"sheet body {i} has no readable Name — "
                f"provide explicit body_refs in the target"
            )
        append = i > 0
        try:
            ok = ext.SelectByID2(
                body_name,
                "SURFACEBODY",
                0,
                0,
                0,
                append,
                1,
                null_callout,
                0,
            )
        except Exception as exc:
            return False, f"SelectByID2({body_name!r}) raised: {exc!r}"
        if not ok:
            return False, f"SelectByID2({body_name!r}) returned False"
    return True, None


def create_knit(
    doc: Any,
    feature: dict,
    target: dict,
) -> tuple[bool, str | None]:
    """Knit (sew) two or more surface bodies together.  Fail-closed.

    ``feature`` keys
        try_to_form_solid : bool  — attempt to form a solid from the knit
            surface (default ``False``).
        use_gap_filters   : bool  — (default ``True``)
        merge_entities    : bool  — (default ``False``)
        knit_tolerance_mm : float — (default 0.0001; CHM lower bound)
        max_gap_mm        : float — (default 0.0001; CHM lower bound)

    ``target`` keys
        body_refs : list[dict] — each dict has ``name`` (required) and
            ``type`` (optional: ``"BODYFEATURE"`` or ``"SURFACEBODY"``,
            default ``"SURFACEBODY"``).
            If omitted, the handler auto-selects all sheet bodies in the
            document (requires ≥ 2).
    """
    if not isinstance(feature, dict):
        return False, "feature must be a dict"
    if not isinstance(target, dict):
        return False, "target must be a dict"

    try_to_form_solid = bool(feature.get("try_to_form_solid", False))
    use_gap_filters = bool(feature.get("use_gap_filters", True))
    merge_entities = bool(feature.get("merge_entities", False))

    try:
        knit_tol_m = float(feature.get("knit_tolerance_mm", 0.0001)) / 1000.0
        max_gap_m = float(feature.get("max_gap_mm", 0.0001)) / 1000.0
    except (TypeError, ValueError) as exc:
        return False, f"numeric tolerance parameter invalid: {exc}"

    if knit_tol_m < _TOL_LOWER_M or knit_tol_m > _TOL_UPPER_M:
        return False, (
            f"knit_tolerance_mm out of CHM bounds "
            f"[{_TOL_LOWER_M * 1000:.4f}, {_TOL_UPPER_M * 1000:.1f}] mm, "
            f"got {knit_tol_m * 1000:.6f} mm"
        )
    if max_gap_m < _TOL_LOWER_M or max_gap_m > _TOL_UPPER_M:
        return False, (
            f"max_gap_mm out of CHM bounds "
            f"[{_TOL_LOWER_M * 1000:.4f}, {_TOL_UPPER_M * 1000:.1f}] mm, "
            f"got {max_gap_m * 1000:.6f} mm"
        )

    sheet_before = _sheet_body_count(doc)
    solids_before = _solid_body_count(doc)
    vol_before = _solid_volume_mm3(doc)

    try:
        doc.ClearSelection2(True)
    except Exception:
        pass

    body_refs = target.get("body_refs")
    if isinstance(body_refs, list) and len(body_refs) >= 2:
        sel_ok, sel_err = _select_bodies_for_knit(doc, body_refs)
    else:
        sel_ok, sel_err = _select_all_sheet_bodies(doc)
    if not sel_ok:
        return False, sel_err

    try:
        fm = doc.FeatureManager
        fm.InsertSewRefSurface(
            use_gap_filters,
            try_to_form_solid,
            merge_entities,
            knit_tol_m,
            max_gap_m,
        )
    except Exception as exc:
        return False, f"InsertSewRefSurface raised: {exc!r}"

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass

    sheet_after = _sheet_body_count(doc)
    area_after = _total_sheet_area_mm2(doc)
    solids_after = _solid_body_count(doc)
    vol_after = _solid_volume_mm3(doc)

    d_sheets = sheet_after - sheet_before
    d_solids = solids_after - solids_before
    d_vol = vol_after - vol_before

    if try_to_form_solid:
        # Solid-knit mode: sheets consumed AND solid materialized.
        if d_sheets < 0 and verify.gate_surface_to_solid(d_vol, d_solids):
            return True, None
        return False, (
            f"knit-to-solid did not materialize "
            f"(delta_sheets={d_sheets}, delta_solids={d_solids}, "
            f"delta_vol_mm3={d_vol:.3f}); "
            f"the surface bodies must form a watertight volume"
        )

    # Surface-knit mode: sheets merged AND knit body has positive area.
    if verify.gate_surface_aggregate(d_sheets, area_after):
        return True, None

    return False, (
        f"knit did not merge surface bodies "
        f"(delta_sheets={d_sheets}, area_after_mm2={area_after:.3f}); "
        f"the bodies must share edges suitable for sewing"
    )
