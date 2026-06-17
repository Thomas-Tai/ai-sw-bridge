"""W60 — ``sketch_convert`` lane (Convert Entities via ``SketchUseEdge3``).

The HIGHEST-RISK W60 sketch-editing lane: its seeds are **model edges/faces**,
not sketch segments, so it leans on the project's durable-topology selection
infra (proven by hem/thread) to anchor each seed across rebuild and the
out-of-process marshaling boundary. ``ISketchManager.SketchUseEdge3(Chain,
InnerLoops)`` projects the **currently-selected model topology** onto the active
sketch plane (Convert Entities), so ``_apply`` must select every seed edge
*before* the call.

Selection seam (mirrors ``features/hem.py:37-38``): the durable-selection
helpers are offline-importable (the whole offline suite imports them via
``features/``), so importing them at MODULE level keeps this op offline-safe
AND lets the offline tests monkeypatch ``resolve_edge_ref`` / ``select_entity``
on this module's namespace. Everything else stays lazy.

Verify-the-EFFECT (W21/W42 doctrine): success = sketch-segment COUNT delta,
never the COM return. Each converted edge projects to one new sketch segment,
so ``_verify`` adjudicates ``after > before``. A clean ``True`` return with a
zero delta is the out-of-process no-op wall signature (cf. rib / move-copy) —
the spike classifies it as NO_OP and STOPs, never papers over it.
"""

from __future__ import annotations

from typing import Any

from ._base import SketchEditError, SketchEditOp, clear_selection

# Module-level durable-selection import (mirrors hem.py:37-38). `selection.live`
# is offline-importable, so this keeps `convert` offline-safe while exposing the
# `resolve_edge_ref` / `select_entity` seam for the offline tests to monkeypatch.
from ...selection._edge_ref import DurableEdgeRef
from ...selection.live import resolve_edge_ref, select_entity


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["refs"],
    "properties": {
        "refs": {
            "type": "array",
            "minItems": 1,
            "description": (
                "Serialized DurableEdgeRef dicts (same shape hem's edge_ref "
                "accepts) naming the model edges to Convert onto the sketch."
            ),
            "items": {"type": "object"},
        },
        "chain": {
            "type": "boolean",
            "default": False,
            "description": "Convert the full chain connected to each seed edge.",
        },
        "inner_loops": {
            "type": "boolean",
            "default": False,
            "description": "Also convert inner loops of a converted face.",
        },
    },
}


def _validate(params: dict) -> None:
    """Semantic checks beyond the schema. Raise SketchEditError on bad params."""
    refs = params.get("refs")
    if not isinstance(refs, list) or not refs:
        raise SketchEditError("sketch_convert requires a non-empty 'refs' array")


def _apply(doc: Any, sk: Any, params: dict) -> dict:
    """Select each durable seed edge, then Convert it onto the OPEN sketch.

    Operates ONLY on the already-open active sketch (the orchestrator owns
    open/close/rebuild). Fail-closed on any ref that does not parse, resolve,
    or select.
    """
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
    """Each converted edge projects to a new sketch segment → ``after > before``."""
    n_refs = len(params.get("refs", []))
    return (
        after > before,
        f"convert {n_refs} edge(s): segments {before}->{after} (delta {after - before})",
    )


OP = SketchEditOp(
    op="sketch_convert",
    schema=_SCHEMA,
    validate=_validate,
    apply=_apply,
    verify_effect=_verify,
)
