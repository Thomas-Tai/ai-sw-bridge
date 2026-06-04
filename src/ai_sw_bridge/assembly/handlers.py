"""Assembly COM handlers — placement + mating (Wave-9 Phase 1, Slices 4-5).

De-advertised handlers for placing components and creating mates in an
assembly document. Both use the W8 seat-proven COM recipes:

  - **Placement:** ``typed(sw, "ISldWorks").OpenDoc6(part_path)`` (mandatory
    pre-open) → ``typed(asm, "IAssemblyDoc").AddComponent4(path, "", x, y, z)``
    → real ``IComponent2`` with B-rep.

  - **Coincident mate:** ``CreateMateData(0)`` → ``typed_qi(
    ICoincidentMateFeatureData)`` → ``EntitiesToMate = VARIANT(VT_ARRAY |
    VT_DISPATCH, (f1, f2))`` → ``MateAlignment`` → ``CreateMate(data)``.
    Faces from ``comp.GetBodies(0).GetFaces()`` (component context).
"""

from __future__ import annotations

import math
from typing import Any

import pythoncom
import win32com.client as w32

from ..com.earlybind import typed, typed_qi, typed_extension
from ..com.sw_type_info import wrapper_module

from .face_resolver import resolve_component_face


def place_components(
    sw: Any,
    asm_doc: Any,
    components: list[dict[str, Any]],
    *,
    mod: Any | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Place all components into an assembly document.

    Phase 1 is **translation-only**: ``AddComponent4`` places at ``xyz_mm``;
    rotation (``rpy_deg``) is rejected at validation (rotation via
    ``MathTransform``/``IComponent2.Transform2`` is unproven and deferred), so a
    placed component is never silently mis-oriented.

    For each component:
      1. ``OpenDoc6(part_path)`` — mandatory pre-open (its absence was the E4 wall).
      2. ``AddComponent4(path, "", x, y, z)`` at the transform.
      3. Verify: ``GetModelDoc2().GetBodies2(0, True)`` ≥ 1 solid body.

    Args:
        sw: the ``SldWorks.Application`` COM object.
        asm_doc: the assembly document (``IModelDoc2``).
        components: list of component dicts from the assembly spec
            (``id``, ``part``/``part_spec``, ``transform``).
        mod: the gen_py wrapper module.

    Returns:
        ``(placed, error)`` where ``placed`` maps ``id → IComponent2`` and
        ``error`` is ``None`` on success or a message on the first failure.
    """
    if mod is None:
        mod = wrapper_module()

    typed_sw = typed(sw, "ISldWorks", module=mod)
    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    placed: dict[str, Any] = {}

    for comp_spec in components:
        cid = comp_spec["id"]
        part_path = comp_spec.get("part") or comp_spec.get("part_spec_path")
        if not part_path:
            return placed, f"component {cid!r} has no resolved part path"

        # Pre-open (mandatory — without this AddComponent4 silently returns None)
        try:
            open_ret = typed_sw.OpenDoc6(part_path, 1, 1, "", 0, 0)
            if isinstance(open_ret, tuple):
                part_doc = open_ret[0]
            else:
                part_doc = open_ret
        except Exception as exc:
            return placed, f"component {cid!r}: OpenDoc6 failed: {exc!r}"

        if part_doc is None:
            return placed, f"component {cid!r}: OpenDoc6 returned None"

        # Compute placement coordinates
        transform = comp_spec.get("transform", {})
        xyz = transform.get("xyz_mm", [0, 0, 0])
        x_m = float(xyz[0]) / 1000.0
        y_m = float(xyz[1]) / 1000.0
        z_m = float(xyz[2]) / 1000.0

        # Place the component
        try:
            comp = typed_asm.AddComponent4(part_path, "", x_m, y_m, z_m)
        except Exception as exc:
            return placed, f"component {cid!r}: AddComponent4 failed: {exc!r}"

        if comp is None or isinstance(comp, int):
            return placed, f"component {cid!r}: AddComponent4 returned None"

        # Verify real B-rep
        try:
            model_doc = comp.GetModelDoc2()
            if model_doc is not None:
                bodies = model_doc.GetBodies2(0, True)
                body_count = len(bodies) if bodies else 0
                if body_count < 1:
                    return placed, (
                        f"component {cid!r}: no solid bodies "
                        f"(GetBodies2 returned {body_count})"
                    )
        except Exception as exc:
            return placed, f"component {cid!r}: B-rep verify failed: {exc!r}"

        placed[cid] = comp

    return placed, None


def create_coincident_mate(
    asm_doc: Any,
    placed: dict[str, Any],
    mate_spec: dict[str, Any],
    *,
    mod: Any | None = None,
) -> tuple[Any | None, str | None]:
    """Create a coincident mate between two component faces.

    Uses the W8 seat-proven recipe:
      1. Resolve both face_refs against their component bodies.
      2. ``CreateMateData(0)`` (COINCIDENT).
      3. ``typed_qi(ICoincidentMateFeatureData)``.
      4. ``EntitiesToMate = VARIANT(VT_ARRAY | VT_DISPATCH, (f1, f2))``.
      5. ``MateAlignment`` from the spec's alignment field.
      6. ``CreateMate(data)`` → verify returned IFeature.

    Args:
        asm_doc: the assembly document.
        placed: map of ``component_id → IComponent2`` from ``place_components``.
        mate_spec: a mate dict from the assembly spec.
        mod: the gen_py wrapper module.

    Returns:
        ``(mate_feature, error)`` — the mate IFeature on success, or ``(None,
        message)`` on failure.
    """
    if mod is None:
        mod = wrapper_module()

    alignment_map = {"aligned": 0, "anti_aligned": 1, "closest": 2}
    alignment_str = mate_spec.get("alignment", "aligned")
    alignment = alignment_map.get(alignment_str, 0)

    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)

    # Resolve both face entities
    faces = []
    for ref_key in ("a", "b"):
        ref = mate_spec[ref_key]
        cid = ref["component"]
        face_ref = ref["face_ref"]

        comp = placed.get(cid)
        if comp is None:
            return None, f"mate {ref_key}: component {cid!r} not placed"

        resolution = resolve_component_face(asm_doc, comp, face_ref, mod=mod)
        if not resolution.ok:
            return None, (
                f"mate {ref_key}: face unresolved on {cid!r} "
                f"(method={resolution.method}, error={resolution.error})"
            )
        faces.append(resolution.entity)

    # CreateMateData + EntitiesToMate SAFEARRAY + CreateMate
    try:
        mate_data = typed_asm.CreateMateData(0)  # 0 = swMateCOINCIDENT
        if mate_data is None:
            return None, "CreateMateData returned None"

        coin_data = typed_qi(
            mate_data, "ICoincidentMateFeatureData", module=mod
        )
        face_arr = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(faces)
        )
        coin_data.EntitiesToMate = face_arr
        coin_data.MateAlignment = alignment

        mate_ret = typed_asm.CreateMate(mate_data)
    except Exception as exc:
        return None, f"mate pipeline failed: {exc!r}"

    if mate_ret is None or isinstance(mate_ret, int):
        try:
            mfd = typed_qi(mate_data, "IMateFeatureData", module=mod)
            es = mfd.ErrorStatus
        except Exception:
            es = "?"
        return None, f"CreateMate returned None (ErrorStatus={es})"

    # Verify: cast to IFeature and check type
    try:
        ifeat = typed(mate_ret, "IFeature", module=mod)
        mate_type = ifeat.GetTypeName2()
        if "Mate" not in mate_type and "mate" not in mate_type.lower():
            return None, f"unexpected feature type: {mate_type}"
    except Exception as exc:
        return None, f"mate verification failed: {exc!r}"

    return mate_ret, None
