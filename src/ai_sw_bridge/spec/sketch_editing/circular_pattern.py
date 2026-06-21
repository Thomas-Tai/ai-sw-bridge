"""Sketch-editing lane: ``sketch_circular_pattern`` (closed-form rotation).

Sibling to the W60 linear ``sketch_pattern``.  Multiplies the selected seed
sketch segments around the sketch origin via
``ISketchManager.CreateCircularSketchStepAndRepeat`` (the 6-arg form).  An
N-instance circular pattern of ``S`` seeds adds ``S * (N - 1)`` new segments;
verify-the-EFFECT is the resulting sketch-segment COUNT delta
(``after > before``), never the COM ``True`` return (the W21/W42 ghost trap).

Operates ONLY on the already-open active sketch handed to ``_apply`` by the
``apply_sketch_edit`` orchestrator: it selects the seeds and fires the call,
and never opens/closes/rebuilds/saves the document.  Imports nothing live-COM
at module scope, so ``propose`` validates the params fully offline.

COM signature (``ISketchManager``, SW 2024 v32.1 wants the 9-arg form — the
6-arg form raises DISP_E_PARAMNOTOPTIONAL on this build, the gen/server skew):
    CreateCircularSketchStepAndRepeat(
        double ArcRadius, double ArcAngle, int PatternNum,
        double PatternSpacing, bool PatternRotate, str DeleteInstances,
        bool RadiusDim, bool AngleDim, bool CreateNumOfInstancesDim) -> bool

Units: ``ArcRadius`` in METRES (``mm_to_m`` — distance from the sketch origin
to the seed), ``ArcAngle`` / ``PatternSpacing`` in RADIANS (``deg_to_rad``).
The seed segment must lie at radius ``radius_mm`` from the sketch origin for
the rotation to land instances on the intended circle.
"""

from __future__ import annotations

from typing import Any

from ._base import (
    SketchEditError,
    SketchEditOp,
    clear_selection,
    deg_to_rad,
    get_segments,
    mm_to_m,
    select_segment,
)

# ---------------------------------------------------------------------------
# Params schema (additionalProperties: false — validated offline at propose)
# ---------------------------------------------------------------------------

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "num", "radius_mm"],
    "properties": {
        "entities": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "integer", "minimum": 0},
            "description": "Indices of the seed sketch segments to pattern.",
        },
        "num": {
            "type": "integer",
            "minimum": 2,
            "description": "Total number of instances around the circle (incl. seed).",
        },
        "radius_mm": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Pattern radius — origin-to-seed distance (millimetres).",
        },
        "arc_angle_deg": {
            "type": "number",
            "default": 360.0,
            "description": "Total angle the pattern spans (degrees; 360 = full circle).",
        },
        "spacing_deg": {
            "type": "number",
            "default": 0.0,
            "description": "Angle between instances (degrees); 0 -> arc_angle/num (equal).",
        },
        "pattern_rotate": {
            "type": "boolean",
            "default": True,
            "description": "Rotate each instance to face the centre (vs translate-only).",
        },
        "delete_instances": {
            "type": "string",
            "default": "",
            "description": "Comma/space list of instance indices to skip (e.g. '1 3').",
        },
    },
}


# ---------------------------------------------------------------------------
# Semantic validation (beyond the JSON schema)
# ---------------------------------------------------------------------------


def _validate(params: dict) -> None:
    """Reject param combinations the schema cannot express."""
    entities = params.get("entities")
    if not entities:
        raise SketchEditError(
            "sketch_circular_pattern requires a non-empty 'entities' list"
        )
    num = int(params.get("num", 0))
    if num < 2:
        raise SketchEditError(
            f"sketch_circular_pattern requires num >= 2 (got {num}; a 1-instance "
            "pattern is a no-op)"
        )


def _effective_spacing_deg(params: dict) -> float:
    """Equal-spacing default: when ``spacing_deg`` is 0/unset, split the arc."""
    spacing = float(params.get("spacing_deg", 0.0) or 0.0)
    if spacing > 0:
        return spacing
    num = int(params.get("num", 2))
    arc = float(params.get("arc_angle_deg", 360.0))
    # full-circle equal spacing wraps, so divide by num; a partial arc by num-1.
    divisor = num if abs(arc) >= 360.0 else max(num - 1, 1)
    return arc / divisor


# ---------------------------------------------------------------------------
# Apply (operates on the OPEN active sketch — never open/close/rebuild/save)
# ---------------------------------------------------------------------------


def _apply(doc: Any, sk: Any, params: dict) -> dict:
    """Select the seed segments and fire the circular step-and-repeat."""
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs) or not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}

    ret = doc.SketchManager.CreateCircularSketchStepAndRepeat(
        mm_to_m(params["radius_mm"]),
        deg_to_rad(params.get("arc_angle_deg", 360.0)),
        int(params["num"]),
        deg_to_rad(_effective_spacing_deg(params)),
        bool(params.get("pattern_rotate", True)),
        str(params.get("delete_instances", "")),
        False,  # RadiusDim — no driving radius dimension
        False,  # AngleDim — no driving angle dimension
        False,  # CreateNumOfInstancesDim
    )
    return {"ok": bool(ret), "raw_return": ret, "seeds_selected": len(params["entities"])}


# ---------------------------------------------------------------------------
# Verify-the-EFFECT (segment-count delta — the gate)
# ---------------------------------------------------------------------------


def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    """A circular pattern of ``S`` seeds into ``num`` instances adds
    ``S * (num - 1)`` new segments, so ``after > before``.
    """
    seeds = len(params.get("entities", []))
    num = int(params.get("num", 2))
    expected = before + seeds * (num - 1)
    note = f"{before}->{after} (expected {expected}: +{seeds}*({num}-1))"
    return after > before, note


OP = SketchEditOp(
    op="sketch_circular_pattern",
    schema=_SCHEMA,
    validate=_validate,
    apply=_apply,
    verify_effect=_verify,
)
