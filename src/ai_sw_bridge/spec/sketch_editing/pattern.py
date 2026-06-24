"""W60 sketch-editing lane: ``sketch_pattern`` (linear step-and-repeat).

Multiplies the selected seed sketch segments into an NxM grid via
``ISketchManager.CreateLinearSketchStepAndRepeat`` (the 12-arg linear form).
A 3x1 pattern of one seed circle adds 2 copies (3 total); verify-the-EFFECT is
the resulting sketch-segment COUNT delta (``after > before``), never the COM
``True`` return (the W21/W42 ghost trap).

Operates ONLY on the already-open active sketch handed to ``_apply`` by the
``apply_sketch_edit`` orchestrator: it selects the seeds and fires the call,
and never opens/closes/rebuilds/saves the document (the orchestrator owns
that). Imports nothing live-COM at module scope, so ``propose`` validates the
params fully offline.

COM signature (``ISketchManager``, seat-confirmed, all 12 args):
    CreateLinearSketchStepAndRepeat(
        int NumX, int NumY, double SpacingX, double SpacingY,
        double AngleX, double AngleY, str DeleteInstances,
        bool XSpacingDim, bool YSpacingDim, bool AngleDim,
        bool CreateNumOfInstancesDimInXDir,
        bool CreateNumOfInstancesDimInYDir) -> bool

Units: spacing in METRES (``mm_to_m``), angles in RADIANS (``deg_to_rad``).
``DeleteInstances`` is a string of skipped instance indices (default ``""``).
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
    "required": ["entities", "num_x", "spacing_x_mm"],
    "properties": {
        "entities": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "integer", "minimum": 0},
            "description": "Indices of the seed sketch segments to pattern.",
        },
        "num_x": {
            "type": "integer",
            "minimum": 1,
            "description": "Number of instances along the X direction (incl. seed).",
        },
        "num_y": {
            "type": "integer",
            "minimum": 1,
            "default": 1,
            "description": "Number of instances along the Y direction (incl. seed).",
        },
        "spacing_x_mm": {
            "type": "number",
            "description": "Spacing between instances along X (millimetres).",
        },
        "spacing_y_mm": {
            "type": "number",
            "default": 0,
            "description": "Spacing between instances along Y (millimetres).",
        },
        "angle_x_deg": {
            "type": "number",
            "default": 0,
            "description": "Direction angle of the X axis (degrees).",
        },
        "angle_y_deg": {
            "type": "number",
            "default": 90,
            "description": "Direction angle of the Y axis (degrees).",
        },
        "delete_instances": {
            "type": "string",
            "default": "",
            "description": "Comma list of instance indices to skip (e.g. '1 3').",
        },
        "x_spacing_dim": {"type": "boolean", "default": False},
        "y_spacing_dim": {"type": "boolean", "default": False},
        "angle_dim": {"type": "boolean", "default": False},
        "num_x_dim": {"type": "boolean", "default": False},
        "num_y_dim": {"type": "boolean", "default": False},
    },
}


# ---------------------------------------------------------------------------
# Semantic validation (beyond the JSON schema)
# ---------------------------------------------------------------------------


def _validate(params: dict) -> None:
    """Reject param combinations the schema cannot express.

    A 1x1 pattern (``num_x * num_y < 2``) produces no copies — a guaranteed
    no-op — and an empty ``entities`` list has no seed to multiply.
    """
    entities = params.get("entities")
    if not entities:
        raise SketchEditError("sketch_pattern requires a non-empty 'entities' list")

    num_x = int(params.get("num_x", 1))
    num_y = int(params.get("num_y", 1))
    if num_x * num_y < 2:
        raise SketchEditError(
            "sketch_pattern requires num_x * num_y >= 2 "
            f"(got {num_x} x {num_y} = {num_x * num_y}; a 1x1 pattern is a no-op)"
        )


# ---------------------------------------------------------------------------
# Apply (operates on the OPEN active sketch — never open/close/rebuild/save)
# ---------------------------------------------------------------------------


def _apply(doc: Any, sk: Any, params: dict) -> dict:
    """Select the seed segments and fire the linear step-and-repeat.

    Returns ``{"ok": <COM call reported success>, "raw_return": <ret>}`` plus a
    selection diagnostic. The segment-count adjudication is ``_verify``'s job.
    """
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs) or not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}

    ret = doc.SketchManager.CreateLinearSketchStepAndRepeat(
        int(params["num_x"]),
        int(params.get("num_y", 1)),
        mm_to_m(params["spacing_x_mm"]),
        mm_to_m(params.get("spacing_y_mm", 0.0)),
        deg_to_rad(params.get("angle_x_deg", 0.0)),
        deg_to_rad(params.get("angle_y_deg", 90.0)),
        str(params.get("delete_instances", "")),
        bool(params.get("x_spacing_dim", False)),
        bool(params.get("y_spacing_dim", False)),
        bool(params.get("angle_dim", False)),
        bool(params.get("num_x_dim", False)),
        bool(params.get("num_y_dim", False)),
    )
    return {
        "ok": bool(ret),
        "raw_return": ret,
        "seeds_selected": len(params["entities"]),
    }


# ---------------------------------------------------------------------------
# Verify-the-EFFECT (segment-count delta — the gate)
# ---------------------------------------------------------------------------


def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    """A linear pattern of ``S`` seeds into an ``num_x * num_y`` grid adds
    ``S * (num_x * num_y - 1)`` new segments, so ``after > before``.
    """
    seeds = len(params.get("entities", []))
    num_x = int(params.get("num_x", 1))
    num_y = int(params.get("num_y", 1))
    expected = before + seeds * (num_x * num_y - 1)
    note = f"{before}->{after} (expected {expected}: +{seeds}*({num_x}*{num_y}-1))"
    return after > before, note


OP = SketchEditOp(
    op="sketch_pattern",
    schema=_SCHEMA,
    validate=_validate,
    apply=_apply,
    verify_effect=_verify,
)
