"""Sketch relations: geometric constraints between sketch entities (W39).

Adds horizontal / vertical / parallel / perpendicular / equal / concentric
relations to the existing sketch grammar.

COM route (seat-validated on SW 2024 SP1):
  1. EditSketch on the named sketch
  2. Enumerate segments via ISketch.GetSketchSegments (PROPERTY, no parens)
  3. For each relation: ClearSelection → raw seg.Select2(append, mark) for
     each entity → doc.SketchAddConstraints(token)  [IModelDoc2, NOT SketchManager]
  4. Verify constraint applied (relation count delta via RelationManager)
  5. Close sketch, rebuild

Entity references are 0-based segment indices within the sketch, enumerated
in creation order. Construction segments (diagonals, centerlines) are
included in the index space.

Token map (RELATION_TOKENS): every value below is EFFECT-VERIFIED on the
seat (geometry actually moved). collinear / coincident / symmetric are
DEFERRED — their tokens could not be proven (see docs/DEFERRED.md).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Token map: relation type → SW SketchAddConstraints string token.
# Every entry is EFFECT-VERIFIED on SW 2024 SP1 (geometry moved, not just
# "no error"). The W21 no-op trap: SketchAddConstraints(badToken) silently
# does nothing — the only proof a token is real is that geometry moves.
#
# DEFERRED (tokens could not be proven — see docs/DEFERRED.md):
#   collinear  — both sgCOLLINEAR2D and sgCOLLINEAR no-op; token unknown
#   coincident — needs endpoint (not segment) selection; not yet characterized
#   symmetric  — 3-ref centerline selection order not yet proven
# ---------------------------------------------------------------------------
RELATION_TOKENS: dict[str, str] = {
    "horizontal": "sgHORIZONTAL2D",
    "vertical": "sgVERTICAL2D",
    "parallel": "sgPARALLEL",
    "perpendicular": "sgPERPENDICULAR2D",
    "equal": "sgSAMELENGTH",
    "concentric": "sgCONCENTRIC",
}

# Arity: number of entity references each relation type requires.
RELATION_ARITY: dict[str, int] = {
    "horizontal": 1,
    "vertical": 1,
    "parallel": 2,
    "perpendicular": 2,
    "equal": 2,
    "concentric": 2,
}

SUPPORTED_RELATION_TYPES = frozenset(RELATION_TOKENS)


class RelationError(Exception):
    """A relation could not be applied or validated."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_relation(rel: dict[str, Any], index: int) -> None:
    """Validate one relation entry. Raises RelationError on bad type/arity."""
    rtype = rel.get("type")
    if rtype not in SUPPORTED_RELATION_TYPES:
        raise RelationError(
            f"relations[{index}]: unknown type {rtype!r}; "
            f"supported: {sorted(SUPPORTED_RELATION_TYPES)}"
        )
    entities = rel.get("entities", [])
    expected = RELATION_ARITY[rtype]
    if len(entities) != expected:
        raise RelationError(
            f"relations[{index}]: type {rtype!r} requires {expected} "
            f"entities, got {len(entities)}"
        )
    for j, ref in enumerate(entities):
        if not isinstance(ref, int) or ref < 0:
            raise RelationError(
                f"relations[{index}].entities[{j}]: must be a non-negative "
                f"integer segment index, got {ref!r}"
            )
    if len(set(entities)) != len(entities):
        raise RelationError(
            f"relations[{index}]: duplicate entity references in {entities}"
        )


def validate_relations(relations: list[dict[str, Any]]) -> None:
    """Validate a list of relations. Raises RelationError on first bad entry."""
    if not isinstance(relations, list):
        raise RelationError("relations must be an array")
    for i, rel in enumerate(relations):
        if not isinstance(rel, dict):
            raise RelationError(f"relations[{i}]: must be an object")
        validate_relation(rel, i)


# ---------------------------------------------------------------------------
# COM helpers
# ---------------------------------------------------------------------------


def _find_sketch_feature(doc: Any, sketch_name: str) -> Any:
    """Find a sketch feature by name via FeatureByName. Returns None if absent."""
    try:
        feat = doc.FeatureByName(sketch_name)
        return feat
    except Exception:
        return None


def _open_sketch_for_edit(doc: Any, sketch_name: str) -> Any:
    """Open the named sketch for editing. Returns the ISketch object.

    Raises RelationError if the sketch cannot be found or opened.
    """
    feat = _find_sketch_feature(doc, sketch_name)
    if feat is None:
        raise RelationError(f"sketch feature '{sketch_name}' not found")
    feat.Select2(False, 0)
    doc.SketchManager.InsertSketch(True)
    sk = doc.GetActiveSketch2
    if sk is None:
        raise RelationError(f"could not open sketch '{sketch_name}' for editing")
    return sk


def _close_sketch(doc: Any) -> None:
    """Close the currently open sketch."""
    doc.SketchManager.InsertSketch(True)


def _get_sketch_segments(sk: Any) -> list[Any]:
    """Enumerate segments in an open sketch. Returns a list in index order.

    Seat-validated: ``GetSketchSegments`` is a PROPERTY on late-bound COM —
    reading it auto-invokes to a tuple. Calling it with ``()`` raises
    "'tuple' object is not callable" (the W29 Count family). Same pattern
    as ``GetActiveSketch2``.
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


def _select_segment(seg: Any, *, append: bool = False, mark: int = 0) -> bool:
    """Select a sketch segment via raw ``seg.Select2(append, mark)``.

    Seat-validated: raw Select2 works reliably. The typed
    ``earlybind.typed(seg, "IEntity").Select2(...)`` FAILS with "Invalid
    number of parameters" (makepy sig mismatch) — so we go raw-first.
    Selection survives to the subsequent SketchAddConstraints call.
    """
    try:
        return bool(seg.Select2(append, mark))
    except Exception:
        return False


def _count_relations(sk: Any) -> int:
    """Count relations in the currently open sketch via RelationManager."""
    try:
        rm = sk.RelationManager
        if rm is None:
            return 0
        rels = rm.GetRelations(0)
        if rels is None:
            return 0
        try:
            return len(list(rels))
        except TypeError:
            return 1
    except Exception:
        return 0


def _read_segment_lengths(segments: list[Any]) -> list[float]:
    """Read the length of each line segment. Returns 0.0 for non-lines."""
    lengths: list[float] = []
    for seg in segments:
        try:
            sp = seg.GetStartPoint2
            ep = seg.GetEndPoint2
            if sp is None or ep is None:
                lengths.append(0.0)
                continue
            dx = ep.X - sp.X
            dy = ep.Y - sp.Y
            lengths.append((dx * dx + dy * dy) ** 0.5)
        except Exception:
            lengths.append(0.0)
    return lengths


# ---------------------------------------------------------------------------
# Apply relations to an open sketch (the COM recipe)
# ---------------------------------------------------------------------------


def apply_relations_in_open_sketch(
    doc: Any,
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply relations to the CURRENTLY OPEN sketch.

    Caller must have already opened the sketch (EditSketch). This function
    does NOT open or close the sketch — it operates on the active sketch.

    Seat-validated recipe:
      - Select via raw ``seg.Select2(append, mark)`` (NOT typed IEntity)
      - Apply via ``doc.SketchAddConstraints(token)`` (IModelDoc2, NOT SketchManager)
      - Verify via RelationManager.GetRelations count delta

    Returns a results dict with per-relation outcomes.
    """
    sk = doc.GetActiveSketch2
    if sk is None:
        raise RelationError("no active sketch")

    segments = _get_sketch_segments(sk)
    if not segments:
        raise RelationError("sketch has no segments")

    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for i, rel in enumerate(relations):
        rtype = rel["type"]
        entity_indices = rel["entities"]
        token = RELATION_TOKENS[rtype]

        # Bounds check
        for idx in entity_indices:
            if idx >= len(segments):
                err = (
                    f"relations[{i}]: entity index {idx} out of range "
                    f"(sketch has {len(segments)} segments)"
                )
                errors.append(err)
                results.append(
                    {
                        "index": i,
                        "type": rtype,
                        "ok": False,
                        "error": err,
                    }
                )
                continue

        if errors:
            continue

        # Count relations before
        count_before = _count_relations(sk)

        # Select entities via raw seg.Select2(append, mark)
        doc.ClearSelection2(True)
        for j, idx in enumerate(entity_indices):
            if not _select_segment(segments[idx], append=(j > 0), mark=0):
                err = f"relations[{i}]: could not select segment at index {idx}"
                errors.append(err)
                results.append(
                    {
                        "index": i,
                        "type": rtype,
                        "ok": False,
                        "error": err,
                    }
                )
                break
        else:
            # Apply constraint via IModelDoc2.SketchAddConstraints
            # (NOT SketchManager — that object has no Constraint members)
            try:
                doc.SketchAddConstraints(token)
            except Exception as exc:
                err = (
                    f"relations[{i}]: SketchAddConstraints({token!r}) "
                    f"failed: {exc!r}"
                )
                errors.append(err)
                results.append(
                    {
                        "index": i,
                        "type": rtype,
                        "ok": False,
                        "error": err,
                    }
                )
                continue

            # Verify: relation count increased
            count_after = _count_relations(sk)
            constrained = count_after > count_before

            results.append(
                {
                    "index": i,
                    "type": rtype,
                    "token": token,
                    "ok": True,
                    "relation_count_before": count_before,
                    "relation_count_after": count_after,
                    "constrained": constrained,
                }
            )

    return {
        "ok": len(errors) == 0,
        "relations_applied": len([r for r in results if r.get("ok")]),
        "relations_failed": len(errors),
        "errors": errors,
        "details": results,
        "segment_count": len(segments),
    }


def apply_relations_to_sketch(
    doc: Any,
    sketch_name: str,
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply relations to a named sketch in an open document.

    Opens the sketch, applies relations, closes the sketch, rebuilds.
    Returns a results dict.

    Raises RelationError if the sketch cannot be opened.
    """
    validate_relations(relations)

    # Measure geometry before (for DOF proof)
    _open_sketch_for_edit(doc, sketch_name)
    sk = doc.GetActiveSketch2
    segments = _get_sketch_segments(sk)
    lengths_before = _read_segment_lengths(segments)
    _close_sketch(doc)

    # Re-open and apply
    _open_sketch_for_edit(doc, sketch_name)
    result = apply_relations_in_open_sketch(doc, relations)
    _close_sketch(doc)

    # Rebuild
    try:
        doc.EditRebuild3
    except Exception:
        pass

    # Measure geometry after (for DOF proof)
    _open_sketch_for_edit(doc, sketch_name)
    sk = doc.GetActiveSketch2
    segments_after = _get_sketch_segments(sk)
    lengths_after = _read_segment_lengths(segments_after)
    _close_sketch(doc)

    result["lengths_before"] = lengths_before
    result["lengths_after"] = lengths_after
    result["geometry_moved"] = any(
        abs(a - b) > 1e-9 for a, b in zip(lengths_before, lengths_after)
    )

    return result


# ---------------------------------------------------------------------------
# Spec schema for the relations spec (CLI mutation pathway)
# ---------------------------------------------------------------------------

RELATIONS_SPEC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ai-sw-bridge sketch relations spec",
    "type": "object",
    "additionalProperties": False,
    "required": ["sketch", "relations"],
    "properties": {
        "sketch": {
            "type": "string",
            "minLength": 1,
            "description": "Name of the sketch feature to constrain.",
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "entities"],
                "properties": {
                    "type": {
                        "enum": sorted(SUPPORTED_RELATION_TYPES),
                        "description": "Geometric relation type.",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0},
                        "minItems": 1,
                        "maxItems": 3,
                        "description": (
                            "Segment indices within the sketch (0-based, "
                            "creation order). Arity depends on type."
                        ),
                    },
                },
            },
            "description": "Geometric relations to apply to the sketch.",
        },
    },
}
