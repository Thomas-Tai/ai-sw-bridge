"""sketch_mirror — mirror selected sketch entities about a centerline (W61).

IModelDoc2.SketchMirror() takes NO args; it mirrors the currently-selected
entities about the selected centerline. Protocol (W0 validates on the seat):
select the entities to mirror, then select the centerline LAST.
"""
from __future__ import annotations
from typing import Any
from ._base import (
    SketchEditOp, SketchEditError,
    clear_selection, get_segments, select_segment,
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "centerline"],
    "properties": {
        "entities": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1},
        "centerline": {"type": "integer", "minimum": 0},
    },
}

def _validate(params: dict) -> None:
    if not params.get("entities"):
        raise SketchEditError("sketch_mirror: entities must be a non-empty list")
    if params.get("centerline") is None:
        raise SketchEditError("sketch_mirror: centerline index required")
    if params["centerline"] in params["entities"]:
        raise SketchEditError("sketch_mirror: centerline must not be among the mirrored entities")

def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    segs = get_segments(sk)
    for idx in list(params["entities"]) + [params["centerline"]]:
        if idx >= len(segs):
            return {"ok": False, "error": f"entity index {idx} out of range ({len(segs)} segments)"}
    # entities to mirror first, then the centerline LAST (all appended, mark 0)
    for j, idx in enumerate(params["entities"]):
        if not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select mirror entity {idx}"}
    if not select_segment(segs[params["centerline"]], append=True, mark=0):
        return {"ok": False, "error": "could not select centerline"}
    # SketchMirror is on IModelDoc2 (the doc), NOT SketchManager. Returns void.
    doc.SketchMirror()
    return {"ok": True, "raw_return": "void"}

def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (mirror duplicates entities across the line)"

OP = SketchEditOp(op="sketch_mirror", schema=_SCHEMA,
                  validate=_validate, apply=_apply, verify_effect=_verify)
