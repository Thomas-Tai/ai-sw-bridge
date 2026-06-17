"""Sketch-editing op base: shared COM recipe + op-registry + orchestrator (W60).

This is the W0-owned contract that every sketch-editing op module (offset /
convert / trim / pattern) is authored against. It lifts the seat-proven W39
sketch-relations recipe (open-edit / GetSketchSegments-property /
raw-Select2 / close+rebuild) and adds:

  * ``count_segments`` — the uniform verify-the-EFFECT metric for this
    cluster. Sketch-editing success is a *sketch-segment count delta* that
    survives close+rebuild (offset/convert/pattern add segments, trim
    removes/splits them). A True return or a non-None handle is NEVER proof
    (the W21/W42 ghost trap).
  * ``SketchEditOp`` — the per-op descriptor each lane module exports as
    ``OP``. W0 registers it in ``__init__.py`` (one line per lane, mirroring
    ``features.HANDLER_REGISTRY``).
  * ``apply_sketch_edit`` — the orchestrator: open the named sketch, snapshot
    the segment count, dispatch the op against the OPEN sketch, snapshot
    again, close + rebuild, then ask the op to adjudicate its own effect.

Op modules import ONLY from this module + the stdlib at import time (no
``get_sw_app`` at module scope) so ``propose`` validates fully offline.

COM route (seat-validated on SW 2024 SP1, lifted from ``_sketch_relations``):
  1. EditSketch the named sketch (FeatureByName -> Select2 -> InsertSketch)
  2. Enumerate / count segments via ISketch.GetSketchSegments (PROPERTY)
  3. Op operates on the active sketch through ISketchManager
  4. Verify segment-count delta, close (InsertSketch toggle), rebuild
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Error type (structural failures raise; op-level failures ride in the dict)
# ---------------------------------------------------------------------------


class SketchEditError(Exception):
    """A sketch-edit op could not be applied or validated (structural)."""


# ---------------------------------------------------------------------------
# COM helpers — lifted verbatim from the seat-proven W39 _sketch_relations
# recipe. The recipe is load-bearing: GetSketchSegments is a PROPERTY (no
# parens), and raw seg.Select2 is reliable where typed IEntity.Select2 fails.
# ---------------------------------------------------------------------------


def _find_sketch_feature(doc: Any, sketch_name: str) -> Any:
    """Find a sketch feature by name via FeatureByName. Returns None if absent."""
    try:
        return doc.FeatureByName(sketch_name)
    except Exception:
        return None


def open_sketch_for_edit(doc: Any, sketch_name: str) -> Any:
    """Open the named sketch for editing. Returns the active ISketch object.

    Raises SketchEditError if the sketch cannot be found or opened. Seat
    recipe: FeatureByName -> feat.Select2(False, 0) ->
    SketchManager.InsertSketch(True) -> GetActiveSketch2.
    """
    feat = _find_sketch_feature(doc, sketch_name)
    if feat is None:
        raise SketchEditError(f"sketch feature '{sketch_name}' not found")
    feat.Select2(False, 0)
    doc.SketchManager.InsertSketch(True)
    sk = doc.GetActiveSketch2
    if sk is None:
        raise SketchEditError(f"could not open sketch '{sketch_name}' for editing")
    return sk


def close_sketch(doc: Any) -> None:
    """Close the currently open sketch (InsertSketch toggle)."""
    doc.SketchManager.InsertSketch(True)


def get_segments(sk: Any) -> list[Any]:
    """Enumerate segments in an open sketch. Returns a list in index order.

    Seat-validated: ``GetSketchSegments`` is a PROPERTY on late-bound COM —
    reading it auto-invokes to a tuple. Calling it with ``()`` raises
    "'tuple' object is not callable". Same family as ``GetActiveSketch2``.
    """
    try:
        raw = sk.GetSketchSegments
        if raw is None:
            return []
        try:
            return list(raw)
        except TypeError:
            return [raw]
    except Exception:
        return []


def count_segments(sk: Any) -> int:
    """Count segments in an open sketch — the verify-the-EFFECT metric.

    Read live each call (GetSketchSegments is re-invoked), so before/after
    snapshots taken around an op reflect the real delta.
    """
    return len(get_segments(sk))


def select_segment(seg: Any, *, append: bool = False, mark: int = 0) -> bool:
    """Select a sketch segment via raw ``seg.Select2(append, mark)``.

    Seat-validated: raw Select2 works; the typed
    ``earlybind.typed(seg, "IEntity").Select2(...)`` FAILS ("Invalid number
    of parameters", makepy sig mismatch) — go raw-first.
    """
    try:
        return bool(seg.Select2(append, mark))
    except Exception:
        return False


def clear_selection(doc: Any) -> None:
    """Clear the current selection set (ClearSelection2(True))."""
    try:
        doc.ClearSelection2(True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Unit conversions (op modules convert their own length/angle params)
# ---------------------------------------------------------------------------


def mm_to_m(value: float) -> float:
    """Millimetres -> metres (SW API length unit)."""
    return float(value) / 1000.0


def deg_to_rad(value: float) -> float:
    """Degrees -> radians (SW API angle unit)."""
    from math import pi

    return float(value) * pi / 180.0


# ---------------------------------------------------------------------------
# Op descriptor + registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SketchEditOp:
    """Descriptor a lane module exports as ``OP`` and W0 registers.

    Fields:
      op             token, e.g. ``"sketch_offset"`` (matches spec["op"]).
      schema         JSON-schema fragment validating ``spec["params"]``
                     (``additionalProperties: false``).
      validate       ``(params) -> None`` — extra semantic checks beyond the
                     schema; raise ``SketchEditError`` on bad params. Runs at
                     propose-time (offline) AND defensively before apply.
      apply          ``(doc, sk, params) -> dict`` — operate on the OPEN
                     sketch via ISketchManager. Return at least ``{"ok": bool}``
                     plus any op-specific diagnostics; do NOT open/close/rebuild
                     (the orchestrator owns that). Return ``ok`` = did the COM
                     call report success; the segment-count adjudication is
                     ``verify_effect``'s job.
      verify_effect  ``(before, after, params) -> (ok, note)`` — adjudicate the
                     segment-count delta. This is the verify-the-EFFECT gate;
                     offset/convert/pattern expect ``after > before``, trim
                     expects a definite change in the fixture-determined
                     direction.
    """

    op: str
    schema: dict
    validate: Callable[[dict], None]
    apply: Callable[[Any, Any, dict], dict]
    verify_effect: Callable[[int, int, dict], "tuple[bool, str]"]


# token -> SketchEditOp. Populated by per-lane modules via register() (wired
# in __init__.py, one line per lane). Ships EMPTY until the first op lands,
# exactly like features.HANDLER_REGISTRY.
OP_REGISTRY: dict[str, SketchEditOp] = {}


def register(op: SketchEditOp) -> None:
    """Register a sketch-edit op. Raises on duplicate/invalid token."""
    if not isinstance(op, SketchEditOp):
        raise SketchEditError(f"register() expects a SketchEditOp, got {op!r}")
    if not op.op or not isinstance(op.op, str):
        raise SketchEditError(f"op token must be a non-empty string, got {op.op!r}")
    if op.op in OP_REGISTRY:
        raise SketchEditError(f"op {op.op!r} already registered")
    OP_REGISTRY[op.op] = op


# ---------------------------------------------------------------------------
# Validation (propose-time, fully offline)
# ---------------------------------------------------------------------------


def sketch_edit_spec_schema() -> dict[str, Any]:
    """Top-level spec schema. ``op`` enum is dynamic over the live registry."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ai-sw-bridge sketch-editing spec",
        "type": "object",
        "additionalProperties": False,
        "required": ["op", "sketch"],
        "properties": {
            "op": {
                "enum": sorted(OP_REGISTRY),
                "description": "Sketch-editing op token.",
            },
            "sketch": {
                "type": "string",
                "minLength": 1,
                "description": "Name of the sketch feature to edit.",
            },
            "params": {
                "type": "object",
                "description": "Op-specific parameters (validated per-op).",
            },
        },
    }


def validate_sketch_edit_spec(spec: Any) -> None:
    """Validate a sketch-edit spec offline. Raises SketchEditError on any fault.

    Checks the top-level shape, resolves the op from the registry, then
    jsonschema-validates ``params`` against the op's schema and runs the op's
    own semantic ``validate``.
    """
    if not isinstance(spec, dict):
        raise SketchEditError("spec must be an object")
    op_token = spec.get("op")
    if op_token not in OP_REGISTRY:
        raise SketchEditError(
            f"unknown op {op_token!r}; registered: {sorted(OP_REGISTRY)}"
        )
    sketch = spec.get("sketch")
    if not isinstance(sketch, str) or not sketch:
        raise SketchEditError("spec.sketch must be a non-empty string")
    params = spec.get("params", {})
    if not isinstance(params, dict):
        raise SketchEditError("spec.params must be an object")

    op = OP_REGISTRY[op_token]

    import jsonschema

    try:
        jsonschema.validate(params, op.schema)
    except jsonschema.ValidationError as exc:
        raise SketchEditError(f"params schema validation failed: {exc.message}")

    op.validate(params)


# ---------------------------------------------------------------------------
# Orchestrator (the COM recipe — open / dispatch / count / close / rebuild)
# ---------------------------------------------------------------------------


def apply_sketch_edit(
    doc: Any,
    sketch_name: str,
    op_token: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Apply one sketch-edit op to a named sketch in an open document.

    Opens the sketch, snapshots the segment count, dispatches the op against
    the OPEN sketch, snapshots again, closes the sketch, rebuilds, then asks
    the op to adjudicate its segment-count delta.

    Structural failures (unknown op, sketch not found, op raised) raise
    SketchEditError. An op that reports a clean COM failure rides back in the
    result dict with ``ok=False``. Always closes the sketch (never leaves SW
    mid-edit — that corrupts subsequent ops in the session).
    """
    op = OP_REGISTRY.get(op_token)
    if op is None:
        raise SketchEditError(
            f"unknown op {op_token!r}; registered: {sorted(OP_REGISTRY)}"
        )

    # Defensive re-validate (the CLI already validated at propose-time).
    op.validate(params)

    sk = open_sketch_for_edit(doc, sketch_name)
    before = count_segments(sk)

    op_result: dict[str, Any] | None = None
    op_error: Exception | None = None
    try:
        op_result = op.apply(doc, sk, params)
        after = count_segments(sk)
    except Exception as exc:  # noqa: BLE001 — re-raised as SketchEditError below
        after = count_segments(sk)
        op_error = exc
    finally:
        # Always leave sketch-edit mode, even on failure.
        try:
            close_sketch(doc)
        except Exception:
            pass

    # Rebuild so the edit persists into the model (property read, no parens).
    try:
        doc.EditRebuild3
    except Exception:
        pass

    if op_error is not None:
        raise SketchEditError(f"op {op_token!r} raised: {op_error!r}")
    if not isinstance(op_result, dict):
        raise SketchEditError(
            f"op {op_token!r}.apply returned {type(op_result).__name__}, "
            "expected dict"
        )

    ok_effect, effect_note = op.verify_effect(before, after, params)
    call_ok = bool(op_result.get("ok", True))

    result: dict[str, Any] = {
        "ok": call_ok and ok_effect,
        "op": op_token,
        "sketch": sketch_name,
        "segments_before": before,
        "segments_after": after,
        "segment_delta": after - before,
        "call_ok": call_ok,
        "effect_verified": ok_effect,
        "effect_note": effect_note,
    }
    # Merge op-specific diagnostics without clobbering the reserved keys.
    for key, value in op_result.items():
        if key not in result:
            result[key] = value
    return result
