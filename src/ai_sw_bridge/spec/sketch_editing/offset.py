"""W60 sketch-editing lane: ``sketch_offset`` (ISketchManager.SketchOffset2).

Offsets a set of seed sketch segments (selected by index in the OPEN active
sketch) by a signed distance, producing one or more NEW segments. This is an
ISketchManager primitive — the op selects the seeds, fires ``SketchOffset2``,
and returns the raw COM verdict. The orchestrator (``_base.apply_sketch_edit``)
owns open/snapshot/close/rebuild; this module operates ONLY on the already-open
active sketch and NEVER opens, closes, rebuilds, or saves.

Verify-the-EFFECT (the W21/W42 ghost trap): success is a sketch-segment COUNT
delta, never the COM ``True`` return. An offset adds >= 1 new segment
(``both_directions`` adds two copies), so ``_verify`` gates on ``after > before``.

COM signature (``ISketchManager``, DLL-validated — docs/sw_api_full.md):

    SketchOffset2(double Offset, bool BothDirections, bool Chain,
                  int CapEnds, int MakeConstruction, bool AddDimensions) -> bool

  * ``Offset`` is in METRES (use ``mm_to_m``).
  * ``MakeConstruction`` and ``CapEnds`` are Int32 (0 = off), NOT bool.

Offline-importable: imports only from ``._base`` + stdlib at module scope (no
``get_sw_app``), so ``propose`` validates fully offline.
"""

from __future__ import annotations

from typing import Any

from ._base import (
    SketchEditError,
    SketchEditOp,
    clear_selection,
    get_segments,
    mm_to_m,
    select_segment,
)

# ---------------------------------------------------------------------------
# Params schema (additionalProperties: false — propose-time gate)
# ---------------------------------------------------------------------------

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["distance_mm", "entities"],
    "properties": {
        "distance_mm": {
            "type": "number",
            "description": "Offset distance in millimetres (metres on the wire); != 0.",
        },
        "entities": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "integer", "minimum": 0},
            "description": "Indices of the seed sketch segments to offset.",
        },
        "both_directions": {
            "type": "boolean",
            "default": False,
            "description": "Offset to both sides (adds two copies).",
        },
        "chain": {
            "type": "boolean",
            "default": False,
            "description": "Offset the whole connected chain, not just the seeds.",
        },
        "cap_ends": {
            "type": "integer",
            "default": 0,
            "description": "End-cap style (swSkOffsetCapEnds_e; 0 = off). Int32.",
        },
        "make_construction": {
            "type": "boolean",
            "default": False,
            "description": "Make the offset geometry construction.",
        },
        "add_dimensions": {
            "type": "boolean",
            "default": False,
            "description": "Add a driving offset dimension.",
        },
    },
}


# ---------------------------------------------------------------------------
# Semantic validation (beyond the schema; propose-time + defensive pre-apply)
# ---------------------------------------------------------------------------


def _validate(params: dict) -> None:
    """Reject a zero offset distance and an empty seed set (silent no-ops)."""
    distance = params.get("distance_mm")
    if distance is None or float(distance) == 0.0:
        raise SketchEditError("distance_mm must be non-zero")
    entities = params.get("entities")
    if not entities:
        raise SketchEditError("entities must list at least one seed segment index")


# ---------------------------------------------------------------------------
# Apply — operate on the OPEN active sketch via ISketchManager
# ---------------------------------------------------------------------------


def _apply(doc: Any, sk: Any, params: dict) -> dict:
    """Select the seed segments and fire ``SketchOffset2`` on the open sketch.

    Returns ``{"ok": <COM verdict>, "raw_return": <ret>}``; on a selection
    failure returns ``{"ok": False, "error": ...}`` so the orchestrator records
    the call as failed. NEVER opens/closes/rebuilds (the orchestrator owns that).
    """
    clear_selection(doc)
    segs = get_segments(sk)
    for j, idx in enumerate(params["entities"]):
        if idx >= len(segs) or not select_segment(segs[idx], append=(j > 0), mark=0):
            return {"ok": False, "error": f"could not select segment {idx}"}
    ret = doc.SketchManager.SketchOffset2(
        mm_to_m(params["distance_mm"]),
        bool(params.get("both_directions", False)),
        bool(params.get("chain", False)),
        int(params.get("cap_ends", 0)),
        1 if params.get("make_construction", False) else 0,
        bool(params.get("add_dimensions", False)),
    )
    return {"ok": bool(ret), "raw_return": ret}


# ---------------------------------------------------------------------------
# Verify-the-EFFECT — adjudicate the segment-count delta
# ---------------------------------------------------------------------------


def _verify(before: int, after: int, params: dict) -> tuple[bool, str]:
    """An offset adds >= 1 segment (both_directions adds two): ``after > before``."""
    note = f"segments {before}->{after} (offset adds >=1 new segment)"
    return after > before, note


OP = SketchEditOp(
    op="sketch_offset",
    schema=_SCHEMA,
    validate=_validate,
    apply=_apply,
    verify_effect=_verify,
)
