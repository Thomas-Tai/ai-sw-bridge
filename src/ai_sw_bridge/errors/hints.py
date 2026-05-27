"""Hint catalog — structured remediation hints (spec.md §3.4).

A static lookup table mapping ``(iface_method, hresult)`` or
``(iface_method, feature_type)`` pairs to a :class:`Hint`.

Design rules:

* Every hint is a frozen dataclass so it can be hashed, memoized, and
  round-tripped through telemetry without mutation.
* The resolver never hallucinations on unknown HRESULTs — it returns
  ``None`` when no catalog entry matches. The caller (``wrapper.py``,
  E1.2) decides whether to attach a generic fallback.
* Multi-key lookup: primary key is ``(iface_method, hresult)``. If no
  match, fall back to ``(iface_method, feature_type)``. If still no
  match, return ``None``.
* Source attribution: every hint records the doc (``ref_doc``) it was
  drawn from so downstream tooling can trace provenance. Ported entries
  from SolidworksMCP-python carry three-surface attribution per the
  harvest plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Hint:
    """A catalogued remediation hint for a known failure mode."""

    key: str
    summary: str
    remedy: str
    ref_doc: str


# ---------------------------------------------------------------------------
# Catalog — nine entries enumerated in E1.3 spec.
# ---------------------------------------------------------------------------

HINT_CATALOG: dict[str, Hint] = {
    "face_no_longer_exists": Hint(
        key="face_no_longer_exists",
        summary=(
            "Face id changed under a downstream rebuild. The face id "
            "captured at validate-time no longer resolves in the live "
            "part topology."
        ),
        remedy=(
            "Re-resolve the face via the brep manifest: use face_role "
            "(e.g., 'top', '+z_outboard') or fingerprint match against "
            "the parent feature's brep block rather than literal "
            "GetSelectByIDString ids. See spec.md §2.6."
        ),
        ref_doc="docs/central_idea/spec.md §2.6",
    ),
    "sketch_under_constrained": Hint(
        key="sketch_under_constrained",
        summary=(
            "Sketch closed successfully but is under-constrained; SW "
            "may beep or silently accept the loose sketch. Downstream "
            "extrude can produce non-deterministic geometry."
        ),
        remedy=(
            "Add explicit dimensions or geometric relations to fully "
            "constrain the sketch. The sketch status bar in SW reports "
            "under/over-constrained state; until the bridge adds a "
            "lint check, the spec author must verify in the SW UI."
        ),
        ref_doc="docs/known_gotchas.md (sketch constraint gotcha)",
    ),
    "end_condition_mismatch": Hint(
        key="end_condition_mismatch",
        summary=(
            "Confusion between swEndCondThroughAll and "
            "swEndCondUpToSurface enum values. FeatureCut4 / "
            "FeatureExtrusion2 accept integer enums; a string or "
            "out-of-range int silently falls back to swEndCondBlind."
        ),
        remedy=(
            "Use the integer enum value from the SW API help "
            "(swEndCondBlind=0, swEndCondThroughAll=1, "
            "swEndCondUpToSurface=5, etc.). The bridge's "
            "boss_extrude_blind / cut_through_all primitives already "
            "map these; if authoring a new primitive, consult "
            "docs/api_reference.md for the enum table."
        ),
        ref_doc="docs/api_reference.md (swEndConditions_e)",
    ),
    "plane_not_found": Hint(
        key="plane_not_found",
        summary=(
            "SelectByID for a reference plane returned False — the "
            "plane was deleted, renamed, or is not present in the "
            "active configuration."
        ),
        remedy=(
            "Verify the plane name against the feature tree. The "
            "bridge supports 'Front Plane', 'Top Plane', 'Right "
            "Plane' by default; renamed planes must be referenced by "
            "their current name. For localized SW installs, use the "
            "localized plane name (see docs/i18n/README.md)."
        ),
        ref_doc="docs/known_gotchas.md (SelectByID plane gotcha)",
    ),
    "unconsumed_sketch": Hint(
        key="unconsumed_sketch",
        summary=(
            "Sketch exists in the tree but no feature consumes it. "
            "Caught by --lint; surfaces here when a downstream "
            "face_role resolves to the unconsumed sketch's plane."
        ),
        remedy=(
            "Either delete the sketch, or add a feature that consumes "
            "it (boss_extrude_blind, revolve, etc.). Unconsumed "
            "sketches pollute the brep manifest and can confuse "
            "face_role resolution."
        ),
        ref_doc="docs/central_idea/spec.md §7 (lint rules)",
    ),
    "addim_popup_blocking": Hint(
        key="addim_popup_blocking",
        summary=(
            "AddDimension2 triggered a modal popup in the SW UI. The "
            "bridge never calls AddDimension2; see "
            "docs/why_no_addim2.md for the rationale."
        ),
        remedy=(
            "Do not call AddDimension2 from bridge code. Dimensions "
            "should be driven via the EquationMgr (locals.txt) or "
            "via a sketch primitive that bakes the dimension into "
            "the sketch geometry at create-time."
        ),
        ref_doc="docs/why_no_addim2.md",
    ),
    "feature_cut_arg_count_mismatch": Hint(
        key="feature_cut_arg_count_mismatch",
        summary=(
            "FeatureCut4 was invoked with the wrong argument count. "
            "SW 2024 SP1 expects the 27-arg form; older service "
            "packs may accept 26. Late binding does not validate "
            "the signature at call time."
        ),
        remedy=(
            "Use the 27-arg form with the trailing FlipStartOffset "
            "flag. The bridge's cut handler tries 27 then 26 as a "
            "fallback (see spikes/phase0/spike_a_extrude.py "
            "convention). If the fallback also fails, capture the "
            "traceback and file a bug."
        ),
        ref_doc="spikes/phase0/spike_a_extrude.py",
    ),
    "negative_offset_clash": Hint(
        key="negative_offset_clash",
        summary=(
            "Face-sketch center offset crosses the origin projection; "
            "SW silently flips the sketch orientation."
        ),
        remedy=(
            "Keep the face-sketch origin offset within the positive "
            "quadrant of the target face's bounding box. The "
            "face_role + centroid in the brep manifest lets you "
            "compute a safe offset vector; see spec.md §2.10."
        ),
        ref_doc="docs/central_idea/spec.md §2.10",
    ),
    "parametric_value_out_of_range": Hint(
        key="parametric_value_out_of_range",
        summary=(
            "A locals.txt value violates a min/max constraint from "
            "the spec. The bridge validates at ingest; this hint "
            "fires when a downstream --auto-retry mutation bypassed "
            "the validator."
        ),
        remedy=(
            "Clamp the value to the declared range in the spec, or "
            "relax the constraint if the new value is intentional. "
            "The validator's error envelope names the offending "
            "variable and its bounds."
        ),
        ref_doc="docs/central_idea/spec.md §6 (locals validation)",
    ),
}

# Fallback used when callers want a non-None placeholder for unknown
# failure modes. The wrapper (E1.2) typically passes None through when
# no catalog entry matches — this is the documented fail-soft contract
# per spec.md §3.4.
_DEFAULT_HINT = Hint(
    key="unknown_failure",
    summary="Uncatalogued failure mode.",
    remedy=(
        "Inspect the traceback in stderr; if this is a new failure "
        "mode, add an entry to errors/hints.py."
    ),
    ref_doc="src/ai_sw_bridge/errors/hints.py",
)


def resolve_hint(
    hresult: Optional[str],
    iface_method: str,
    feature_type: Optional[str] = None,
) -> Optional[Hint]:
    """Resolve a hint from the catalog.

    Lookup order:
      1. (iface_method, hresult) exact match
      2. (iface_method, feature_type) exact match (fallback for
         validation-style errors that don't carry an HRESULT)
      3. Return None on no match (no hallucination).

    The caller decides whether to substitute :data:`_DEFAULT_HINT`.
    """
    if hresult is not None:
        hresult_key = _hresult_to_key(hresult)
        for hint in HINT_CATALOG.values():
            if _matches_hresult_entry(hint, iface_method, hresult_key):
                return hint

    if feature_type is not None:
        for hint in HINT_CATALOG.values():
            if _matches_feature_entry(hint, iface_method, feature_type):
                return hint

    return None


def default_hint() -> Hint:
    """Return the fail-soft default hint (spec.md §3.4)."""
    return _DEFAULT_HINT


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Catalog-indexed tags. Each hint may declare which (iface_method,
# hresult) or (iface_method, feature_type) pairs it matches.
#
# The E1.3 catalog uses a simplified matching model: the resolver
# walks the catalog and asks each hint "do you match?" via the
# helpers below. This keeps the data structure flat (no nested dicts)
# and makes the catalog easy to extend — add a Hint + register it
# in _IFACE_HRESULT_MAP or _IFACE_FEATURE_MAP.

_IFACE_HRESULT_MAP: dict[tuple[str, str], str] = {
    # (iface_method, hresult) -> hint_key
    ("IFeatureManager.FeatureExtrusion2", "0x80004005"): "face_no_longer_exists",
    ("IFeatureManager.FeatureCut4", "0x80004005"): "face_no_longer_exists",
    ("IModelDocExtension.SelectByID2", "0x80070057"): "plane_not_found",
    ("IModelDoc2.SelectByID", "0x80070057"): "plane_not_found",
    ("IModelDoc2.AddRelation", "0x80004005"): "sketch_under_constrained",
    ("ISketchManager.AddDimension2", "0x80004005"): "addim_popup_blocking",
    ("IFeatureManager.FeatureCut4", "0x80020009"): "feature_cut_arg_count_mismatch",
    ("IEquationMgr.Add2", "0x8002000B"): "parametric_value_out_of_range",
}

_IFACE_FEATURE_MAP: dict[tuple[str, str], str] = {
    # (iface_method, feature_type) -> hint_key
    ("IFeatureManager.FeatureExtrusion2", "boss_extrude_blind"): "end_condition_mismatch",
    ("IFeatureManager.FeatureCut4", "simple_hole"): "end_condition_mismatch",
    ("IModelDoc2.SelectByID", "sketch_on_plane"): "plane_not_found",
    ("ISketchManager.CreateCornerRectangle", "sketch_under_constrained"): "sketch_under_constrained",
    ("IFeatureManager.FeatureExtrusion2", "unconsumed_sketch"): "unconsumed_sketch",
    ("IFeatureManager.FeatureExtrusion2", "negative_offset_clash"): "negative_offset_clash",
}


def _hresult_to_key(hresult: str) -> str:
    """Normalize an HRESULT string to the catalog key form (uppercase 0x...)."""
    if isinstance(hresult, int):
        return f"0x{hresult:08X}"
    s = hresult.strip()
    if s.startswith("0x") or s.startswith("0X"):
        return "0x" + s[2:].upper()
    return s.upper()


def _matches_hresult_entry(
    hint: Hint, iface_method: str, hresult_key: str
) -> bool:
    for (im, hr), key in _IFACE_HRESULT_MAP.items():
        if key == hint.key and im == iface_method and hr == hresult_key:
            return True
    return False


def _matches_feature_entry(
    hint: Hint, iface_method: str, feature_type: str
) -> bool:
    for (im, ft), key in _IFACE_FEATURE_MAP.items():
        if key == hint.key and im == iface_method and ft == feature_type:
            return True
    return False


__all__ = [
    "HINT_CATALOG",
    "Hint",
    "default_hint",
    "resolve_hint",
]
