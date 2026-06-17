"""sketch_chamfer — chamfer the corner between two selected sketch entities (W61)."""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m,
)

# swSketchChamferType_e (DLL-verified): 0 DistanceAngle, 1 DistanceDistance, 2 DistanceEqual.
# This op supports the DISTANCE modes (1, 2) only; angle mode (0) is deferred
# (its second arg is an angle in radians, not a distance).
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["dist1_mm", "entities"],
    "properties": {
        "chamfer_type": {"type": "integer", "enum": [1, 2]},
        "dist1_mm": {"type": "number", "exclusiveMinimum": 0},
        "dist2_mm": {"type": "number", "exclusiveMinimum": 0},
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0},
                     "minItems": 2, "maxItems": 2},
    },
}

def _validate(params: dict) -> None:
    if params.get("dist1_mm", 0) <= 0:
        raise SketchEditError("sketch_chamfer: dist1_mm must be > 0")
    if len(params.get("entities", [])) != 2:
        raise SketchEditError("sketch_chamfer: exactly 2 entities required")
    if params.get("chamfer_type", 1) not in (1, 2):
        raise SketchEditError("sketch_chamfer: chamfer_type must be 1 (DistanceDistance) or 2 (DistanceEqual)")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}
    ctype = int(params.get("chamfer_type", 1))
    d1 = mm_to_m(params["dist1_mm"])
    d2 = mm_to_m(params.get("dist2_mm", params["dist1_mm"]))  # CreateChamfer 3rd arg = 2nd distance
    ret = doc.SketchManager.CreateChamfer(ctype, d1, d2)
    return {"ok": ret is not None, "raw_return": str(ret)}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (chamfer inserts a line, net +1)"

OP = SketchEditOp(op="sketch_chamfer", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
