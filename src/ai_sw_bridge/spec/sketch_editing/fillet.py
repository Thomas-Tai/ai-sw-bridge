"""sketch_fillet — round the corner between two selected sketch entities (W61)."""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["radius_mm", "entities"],
    "properties": {
        "radius_mm": {"type": "number", "exclusiveMinimum": 0},
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0},
                     "minItems": 2, "maxItems": 2},
        "constrained_corners": {"type": "integer", "minimum": 0},
    },
}

def _validate(params: dict) -> None:
    if params.get("radius_mm", 0) <= 0:
        raise SketchEditError("sketch_fillet: radius_mm must be > 0")
    if len(params.get("entities", [])) != 2:
        raise SketchEditError("sketch_fillet: exactly 2 entities (two sides of a corner) required")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}
    ret = doc.SketchManager.CreateFillet(
        mm_to_m(params["radius_mm"]),
        int(params.get("constrained_corners", 0)),
    )
    return {"ok": ret is not None, "raw_return": str(ret)}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (fillet trims 2 sides + inserts an arc, net +1)"

OP = SketchEditOp(op="sketch_fillet", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
