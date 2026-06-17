"""sketch_move_copy — copy selected sketch entities to a new location (W61).

Uses IModelDocExtension.MoveOrCopy with Copy=True (the verifiable mode: it adds
NumCopies * selected segments). Pure move (Copy=False) transforms in place with
NO segment-count change (delta 0) and is out of scope for the count-delta verify
doctrine, so this op always copies.
"""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment, mm_to_m,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "dest_mm"],
    "properties": {
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1},
        "num_copies": {"type": "integer", "minimum": 1},
        "base_mm": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "dest_mm": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "keep_relations": {"type": "boolean"},
    },
}

def _validate(params: dict) -> None:
    if not params.get("entities"):
        raise SketchEditError("sketch_move_copy: entities must be a non-empty list")
    if len(params.get("dest_mm", [])) != 3:
        raise SketchEditError("sketch_move_copy: dest_mm must be [x, y, z] mm")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}
    base = params.get("base_mm", [0.0, 0.0, 0.0])
    dest = params["dest_mm"]
    # MoveOrCopy returns void -> NEVER trust a return; the orchestrator's count
    # delta is the gate. (Copy, NumCopies, KeepRelations, bx,by,bz, dx,dy,dz)
    doc.Extension.MoveOrCopy(
        True,
        int(params.get("num_copies", 1)),
        bool(params.get("keep_relations", False)),
        mm_to_m(base[0]), mm_to_m(base[1]), mm_to_m(base[2]),
        mm_to_m(dest[0]), mm_to_m(dest[1]), mm_to_m(dest[2]),
    )
    return {"ok": True, "raw_return": "void"}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (copy adds num_copies*selected)"

OP = SketchEditOp(op="sketch_move_copy", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
