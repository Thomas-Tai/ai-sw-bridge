"""sketch_convert — Convert Entities (project model edges onto the sketch) (W60)."""

from __future__ import annotations
from typing import Any
from ._base import SketchEditOp, SketchEditError, clear_selection
from ...selection._edge_ref import DurableEdgeRef
from ...selection.live import resolve_edge_ref, select_entity

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["refs"],
    "properties": {
        "refs": {"type": "array", "items": {"type": "object"}, "minItems": 1},
        "chain": {"type": "boolean"},
        "inner_loops": {"type": "boolean"},
    },
}


def _validate(params: dict) -> None:
    if not params.get("refs"):
        raise SketchEditError("sketch_convert: refs must be a non-empty list")


def _apply(doc: Any, sk: Any, params: dict) -> dict:
    clear_selection(doc)
    for j, ref_data in enumerate(params["refs"]):
        try:
            ref = DurableEdgeRef.from_dict(ref_data)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": f"invalid edge_ref[{j}]: {exc}"}
        res = resolve_edge_ref(doc, ref)
        edge = getattr(res, "entity", None)
        if edge is None:
            return {
                "ok": False,
                "error": f"ref[{j}] did not resolve ({getattr(res, 'note', '')})",
            }
        if not select_entity(edge, append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select ref[{j}]"}
    ret = doc.SketchManager.SketchUseEdge3(
        bool(params.get("chain", False)),
        bool(params.get("inner_loops", False)),
    )
    return {"ok": bool(ret), "raw_return": ret}


def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    return after > before, f"segments {before}->{after} (convert adds >=1)"


OP = SketchEditOp(
    op="sketch_convert",
    schema=_SCHEMA,
    validate=_validate,
    apply=_apply,
    verify_effect=_verify,
)
