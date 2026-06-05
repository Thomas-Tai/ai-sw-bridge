"""Assembly edit operations (Wave-15).

Immutable, declarative edit-op model: one op per call produces a **new full
spec** that re-enters the existing ``validate → propose → dry_run → commit``
pipeline. No COM, no in-place mutation.

Four ops (v1):

  - ``add_component`` — append a component to ``components[]``.
  - ``remove_component`` — remove by ``id``; **fail-closed** if any mate
    still references it (error lists blocking mate indices + ref keys).
  - ``add_mate`` — append a mate to ``mates[]``.
  - ``remove_mate`` — remove ``mates[index]`` (0-based).

All ops deep-copy the input spec before mutating, so the caller's dict is
never modified.
"""

from __future__ import annotations

import copy
from typing import Any


class AssemblyEditError(Exception):
    """Raised when an edit op is malformed or fails a safety check."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


_KNOWN_OPS = frozenset({
    "add_component",
    "remove_component",
    "add_mate",
    "remove_mate",
})


def apply_edit_op(spec: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """Apply a single declarative edit op to an assembly spec.

    Returns a **new** spec dict (the input is never mutated). The new spec
    is ready for ``validate_assembly`` → ``sw_propose_assembly``.

    Args:
        spec: the current assembly spec (must have ``kind: "assembly"``,
              ``components[]``, and optionally ``mates[]``).
        op: a dict with ``"op"`` key and op-specific fields.

    Raises:
        AssemblyEditError: on malformed op, unknown op, missing fields,
            out-of-range index, or cascade-blocked remove_component.
    """
    if not isinstance(op, dict):
        raise AssemblyEditError("op must be a dict")

    op_name = op.get("op")
    if not isinstance(op_name, str) or op_name not in _KNOWN_OPS:
        raise AssemblyEditError(
            f"unknown op {op_name!r}; expected one of {sorted(_KNOWN_OPS)}"
        )

    if not isinstance(spec, dict):
        raise AssemblyEditError("spec must be a dict")

    new_spec = copy.deepcopy(spec)

    if op_name == "add_component":
        return _add_component(new_spec, op)
    elif op_name == "remove_component":
        return _remove_component(new_spec, op)
    elif op_name == "add_mate":
        return _add_mate(new_spec, op)
    else:
        return _remove_mate(new_spec, op)


def _add_component(
    spec: dict[str, Any], op: dict[str, Any]
) -> dict[str, Any]:
    component = op.get("component")
    if not isinstance(component, dict):
        raise AssemblyEditError("add_component requires 'component' dict")

    cid = component.get("id")
    if not isinstance(cid, str) or not cid:
        raise AssemblyEditError(
            "add_component: component must have a non-empty 'id'"
        )

    components = spec.setdefault("components", [])
    existing_ids = {c.get("id") for c in components}
    if cid in existing_ids:
        raise AssemblyEditError(
            f"add_component: id {cid!r} already exists in components"
        )

    components.append(component)
    return spec


def _remove_component(
    spec: dict[str, Any], op: dict[str, Any]
) -> dict[str, Any]:
    cid = op.get("id")
    if not isinstance(cid, str) or not cid:
        raise AssemblyEditError(
            "remove_component requires a non-empty 'id' string"
        )

    components = spec.get("components", [])
    idx = next(
        (i for i, c in enumerate(components) if c.get("id") == cid), None
    )
    if idx is None:
        raise AssemblyEditError(
            f"remove_component: id {cid!r} not found in components"
        )

    # Fail-closed: check for blocking mate references
    blocking = _find_blocking_mates(spec, cid)
    if blocking:
        refs = ", ".join(
            f"mate[{i}].{ref}" for i, ref in blocking
        )
        raise AssemblyEditError(
            f"remove_component: {cid!r} is still referenced by mates: "
            f"{refs}. Remove those mates first."
        )

    components.pop(idx)
    return spec


def _find_blocking_mates(
    spec: dict[str, Any], cid: str
) -> list[tuple[int, str]]:
    """Scan all mates for references to a component id.

    Checks ``a.component``, ``b.component`` (symmetric mates) and
    ``width_faces[*].component``, ``tab_faces[*].component`` (width mates).

    Returns a list of ``(mate_index, ref_key)`` tuples.
    """
    blocking: list[tuple[int, str]] = []
    mates = spec.get("mates", [])

    for i, mate in enumerate(mates):
        # Symmetric mates: a / b
        for ref_key in ("a", "b"):
            ref = mate.get(ref_key)
            if isinstance(ref, dict) and ref.get("component") == cid:
                blocking.append((i, ref_key))

        # Width mates: width_faces / tab_faces arrays
        for set_key in ("width_faces", "tab_faces"):
            face_set = mate.get(set_key)
            if isinstance(face_set, list):
                for j, ref in enumerate(face_set):
                    if isinstance(ref, dict) and ref.get("component") == cid:
                        blocking.append((i, f"{set_key}[{j}]"))

    return blocking


def _add_mate(
    spec: dict[str, Any], op: dict[str, Any]
) -> dict[str, Any]:
    mate = op.get("mate")
    if not isinstance(mate, dict):
        raise AssemblyEditError("add_mate requires 'mate' dict")

    if "type" not in mate:
        raise AssemblyEditError("add_mate: mate must have a 'type' field")

    mates = spec.setdefault("mates", [])
    mates.append(mate)
    return spec


def _remove_mate(
    spec: dict[str, Any], op: dict[str, Any]
) -> dict[str, Any]:
    index = op.get("index")
    if not isinstance(index, int) or isinstance(index, bool):
        raise AssemblyEditError(
            "remove_mate requires an integer 'index'"
        )

    mates = spec.get("mates", [])
    if index < 0 or index >= len(mates):
        raise AssemblyEditError(
            f"remove_mate: index {index} out of range "
            f"(mates has {len(mates)} entries)"
        )

    mates.pop(index)
    return spec
