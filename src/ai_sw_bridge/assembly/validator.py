"""Assembly spec validator (Wave-9 Phase 1).

Two-layer validation on top of the JSON-schema structural check:

  1. **Component integrity:** each component ``id`` is unique; exactly one of
     ``part`` / ``part_spec`` is provided (XOR); transforms are well-formed.
  2. **Mate references:** every mate's ``a.component`` / ``b.component`` cites
     an existing component ``id``; mate ``type`` and ``alignment`` are in the
     known sets; coincident mates require ``alignment``.

All errors surface as :class:`AssemblyValidationError` with a human-readable
message and a JSON-pointer-style ``path``.
"""

from __future__ import annotations

from typing import Any

from .schema import MATE_ALIGNMENTS, MATE_TYPES


class AssemblyValidationError(Exception):
    """Raised when an assembly spec fails semantic validation.

    Attributes:
        message: Human-readable error description.
        path: JSON-pointer-style path to the offending element.
    """

    def __init__(self, message: str, path: str = "") -> None:
        self.message = message
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


def validate_assembly(spec: dict[str, Any]) -> None:
    """Validate an assembly spec beyond the structural JSON-schema check.

    Raises :class:`AssemblyValidationError` on the first semantic error found.
    The structural check (``jsonschema.validate`` against ``ASSEMBLY_SCHEMA``)
    is assumed to have already passed — this function checks cross-reference
    integrity and business rules.
    """
    if not isinstance(spec, dict):
        raise AssemblyValidationError("spec must be a dict")

    components = spec.get("components")
    if not isinstance(components, list) or not components:
        raise AssemblyValidationError(
            "components must be a non-empty array", "/components"
        )

    _check_components(components)
    component_ids = {c["id"] for c in components}

    mates = spec.get("mates")
    if mates is not None:
        if not isinstance(mates, list):
            raise AssemblyValidationError("mates must be an array", "/mates")
        _check_mates(mates, component_ids)


def _check_components(components: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    for i, comp in enumerate(components):
        path = f"/components/{i}"
        if not isinstance(comp, dict):
            raise AssemblyValidationError("component must be a dict", path)

        cid = comp.get("id")
        if not isinstance(cid, str) or not cid:
            raise AssemblyValidationError(
                "component id must be a non-empty string", path
            )
        if cid in seen_ids:
            raise AssemblyValidationError(
                f"duplicate component id {cid!r}", path
            )
        seen_ids.add(cid)

        has_part = "part" in comp and comp["part"] is not None
        has_part_spec = "part_spec" in comp and comp["part_spec"] is not None
        if has_part and has_part_spec:
            raise AssemblyValidationError(
                f"component {cid!r} has both 'part' and 'part_spec'; "
                "exactly one is required",
                path,
            )
        if not has_part and not has_part_spec:
            raise AssemblyValidationError(
                f"component {cid!r} must have either 'part' or 'part_spec'",
                path,
            )

        transform = comp.get("transform")
        if transform is not None:
            _check_transform(transform, cid, path)


def _check_transform(
    transform: Any, cid: str, parent_path: str
) -> None:
    path = f"{parent_path}/transform"
    if not isinstance(transform, dict):
        raise AssemblyValidationError(
            f"component {cid!r} transform must be a dict", path
        )

    xyz = transform.get("xyz_mm")
    if xyz is not None:
        if (
            not isinstance(xyz, (list, tuple))
            or len(xyz) != 3
            or not all(isinstance(v, (int, float)) for v in xyz)
        ):
            raise AssemblyValidationError(
                f"component {cid!r} xyz_mm must be a 3-element numeric array",
                path,
            )

    rpy = transform.get("rpy_deg")
    if rpy is not None:
        if (
            not isinstance(rpy, (list, tuple))
            or len(rpy) != 3
            or not all(isinstance(v, (int, float)) for v in rpy)
        ):
            raise AssemblyValidationError(
                f"component {cid!r} rpy_deg must be a 3-element numeric array",
                path,
            )
        # Phase 1 is translation-only: AddComponent4 places at xyz, and rotation
        # via MathTransform/IComponent2.Transform2 is unproven (W8 only placed at
        # xyz). Fail closed on any non-zero rotation rather than silently drop it.
        if any(float(v) != 0.0 for v in rpy):
            raise AssemblyValidationError(
                f"component {cid!r}: rotation (rpy_deg) is not supported in "
                f"Phase 1 (translation-only); use [0, 0, 0] or omit it",
                path,
            )


def _check_mates(
    mates: list[dict[str, Any]], component_ids: set[str]
) -> None:
    for i, mate in enumerate(mates):
        path = f"/mates/{i}"
        if not isinstance(mate, dict):
            raise AssemblyValidationError("mate must be a dict", path)

        mtype = mate.get("type")
        if mtype not in MATE_TYPES:
            raise AssemblyValidationError(
                f"mate type {mtype!r} not in {sorted(MATE_TYPES)}", path
            )

        alignment = mate.get("alignment")
        if alignment is not None and alignment not in MATE_ALIGNMENTS:
            raise AssemblyValidationError(
                f"mate alignment {alignment!r} not in {sorted(MATE_ALIGNMENTS)}",
                path,
            )

        if mtype == "coincident" and alignment is None:
            raise AssemblyValidationError(
                "coincident mate requires 'alignment'", path
            )

        value_mm = mate.get("value_mm")
        if mtype == "distance":
            if value_mm is None:
                raise AssemblyValidationError(
                    "distance mate requires 'value_mm'", path
                )
            if not isinstance(value_mm, (int, float)) or value_mm <= 0:
                raise AssemblyValidationError(
                    f"distance mate value_mm must be a positive number, got {value_mm!r}",
                    path,
                )
        elif mtype in ("concentric", "parallel", "perpendicular"):
            if value_mm is not None:
                raise AssemblyValidationError(
                    f"{mtype} mate does not accept 'value_mm' (geometric constraint)",
                    path,
                )

        for ref_key in ("a", "b"):
            ref = mate.get(ref_key)
            ref_path = f"{path}/{ref_key}"
            if not isinstance(ref, dict):
                raise AssemblyValidationError(
                    f"mate {ref_key} must be a dict", ref_path
                )
            ref_comp = ref.get("component")
            if not isinstance(ref_comp, str) or not ref_comp:
                raise AssemblyValidationError(
                    f"mate {ref_key}.component must be a non-empty string",
                    ref_path,
                )
            if ref_comp not in component_ids:
                raise AssemblyValidationError(
                    f"mate {ref_key}.component {ref_comp!r} not found in "
                    f"component ids {sorted(component_ids)}",
                    ref_path,
                )
            face_ref = ref.get("face_ref")
            if not isinstance(face_ref, dict) or not face_ref:
                raise AssemblyValidationError(
                    f"mate {ref_key}.face_ref must be a non-empty dict",
                    ref_path,
                )
