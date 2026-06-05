"""Assembly COM handlers — placement + mating (Wave-9 Phase 1, Slices 4-5).

De-advertised handlers for placing components and creating mates in an
assembly document. Both use the W8 seat-proven COM recipes:

  - **Placement:** ``typed(sw, "ISldWorks").OpenDoc6(part_path)`` (mandatory
    pre-open) → ``typed(asm, "IAssemblyDoc").AddComponent4(path, "", x, y, z)``
    → real ``IComponent2`` with B-rep.

  - **Mate:** ``CreateMateData(type)`` → ``typed_qi(I<Type>MateFeatureData)``
    (where available) → ``EntitiesToMate = VARIANT(VT_ARRAY | VT_DISPATCH,
    (f1, f2))`` → ``MateAlignment`` → ``CreateMate(data)``. Faces from
    ``comp.GetBodies(0).GetFaces()`` (component context).
"""

from __future__ import annotations

import math
from typing import Any

import pythoncom
import win32com.client as w32

from ..com.earlybind import typed, typed_qi, typed_extension
from ..com.sw_type_info import wrapper_module

from .face_resolver import resolve_component_face


# swMateType_e enum values (typelib-verified; COINCIDENT=0 is Phase-1 proven).
# Phase-2 values (CONCENTRIC, PERPENDICULAR, PARALLEL, DISTANCE) are from
# SolidWorks API documentation and will be empirically verified during PAE.
MATE_TYPE_ENUMS = {
    "coincident": 0,       # swMateCOINCIDENT (Phase-1 anchor)
    "concentric": 1,       # swMateCONCENTRIC
    "perpendicular": 2,    # swMatePERPENDICULAR
    "parallel": 3,         # swMatePARALLEL
    "tangent": 4,          # swMateTANGENT (not in Phase-2 scope)
    "distance": 5,         # swMateDISTANCE
    "angle": 6,            # swMateANGLE (not in Phase-2 scope)
}

# Typed interface names per mate type (from typelib dump).
# Where a typed interface exists, we QI it to set type-specific properties.
# Where it doesn't, we use the base IMateFeatureData path.
MATE_TYPE_INTERFACES = {
    "coincident": "ICoincidentMateFeatureData",
    "concentric": "IConcentricMateFeatureData",
    "perpendicular": "IPerpendicularMateFeatureData",
    "parallel": "IParallelMateFeatureData",
    "tangent": "ITangentMateFeatureData",
    "distance": "IDistanceMateFeatureData",
    "angle": "IAngleMateFeatureData",
}


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


def create_mate(
    asm_doc: Any,
    placed: dict[str, Any],
    mate_spec: dict[str, Any],
    *,
    mod: Any | None = None,
) -> tuple[Any | None, str | None]:
    """Create a mate between two component faces.

    Generalized from the Phase-1 coincident-only handler to support all five
    mate types (coincident, distance, concentric, parallel, perpendicular).

    Uses the W8 seat-proven recipe:
      1. Resolve both face_refs against their component bodies.
      2. ``CreateMateData(type_enum)`` for the mate type.
      3. ``typed_qi(I<Type>MateFeatureData)`` where a typed interface exists.
      4. ``EntitiesToMate = VARIANT(VT_ARRAY | VT_DISPATCH, (f1, f2))``.
      5. ``MateAlignment`` from the spec's alignment field.
      6. Set type-specific properties (e.g., ``Distance`` for distance mates).
      7. ``CreateMate(data)`` → verify returned IFeature.

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

    mate_type_str = mate_spec.get("type", "coincident")
    mate_type_enum = MATE_TYPE_ENUMS.get(mate_type_str)
    if mate_type_enum is None:
        return None, f"unsupported mate type: {mate_type_str!r}"

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
        mate_data = typed_asm.CreateMateData(mate_type_enum)
        if mate_data is None:
            return None, f"CreateMateData({mate_type_enum}) returned None"

        # ALWAYS use the typed interface for EntitiesToMate and MateAlignment.
        # All five typed interfaces (ICoincidentMateFeatureData,
        # IDistanceMateFeatureData, IConcentricMateFeatureData,
        # IParallelMateFeatureData, IPerpendicularMateFeatureData) expose
        # these properties. The base IMateFeatureData does NOT.
        typed_iface_name = MATE_TYPE_INTERFACES.get(mate_type_str)
        if typed_iface_name is None:
            return None, f"no typed interface for mate type {mate_type_str!r}"

        typed_iface = typed_qi(mate_data, typed_iface_name, module=mod)
        face_arr = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(faces)
        )
        typed_iface.EntitiesToMate = face_arr

        # MateAlignment: not all typed interfaces support it (e.g. perpendicular
        # mates have no alignment concept). Set only when available.
        try:
            typed_iface.MateAlignment = alignment
        except AttributeError:
            pass

        # Set type-specific scalar properties
        if mate_type_str == "distance":
            value_mm = mate_spec.get("value_mm")
            if value_mm is not None:
                distance_m = float(value_mm) / 1000.0
                typed_iface.Distance = distance_m

        if mate_type_str == "angle":
            value_deg = mate_spec.get("value_deg")
            if value_deg is not None:
                typed_iface.Angle = math.radians(float(value_deg))

        # Limit mates: min/max variation on distance or angle
        limit = mate_spec.get("limit")
        if limit is not None:
            if mate_type_str == "distance":
                if "min_mm" in limit:
                    typed_iface.MinimumDistance = float(limit["min_mm"]) / 1000.0
                if "max_mm" in limit:
                    typed_iface.MaximumDistance = float(limit["max_mm"]) / 1000.0
            elif mate_type_str == "angle":
                if "min_deg" in limit:
                    typed_iface.MinimumAngle = math.radians(float(limit["min_deg"]))
                if "max_deg" in limit:
                    typed_iface.MaximumAngle = math.radians(float(limit["max_deg"]))

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
        feat_type = ifeat.GetTypeName2()
        if "Mate" not in feat_type and "mate" not in feat_type.lower():
            return None, f"unexpected feature type: {feat_type}"
    except Exception as exc:
        return None, f"mate verification failed: {exc!r}"

    return mate_ret, None


# Backward compatibility: Phase-1 code calls create_coincident_mate
def create_coincident_mate(
    asm_doc: Any,
    placed: dict[str, Any],
    mate_spec: dict[str, Any],
    *,
    mod: Any | None = None,
) -> tuple[Any | None, str | None]:
    """Backward-compatible wrapper for coincident mates (Phase-1 API)."""
    return create_mate(asm_doc, placed, mate_spec, mod=mod)


def verify_mates(
    asm_doc: Any,
    *,
    mod: Any | None = None,
) -> list[dict[str, Any]]:
    """Three-layer solver verification for all mates in an assembly.

    Traverses the flat feature list via ``FeatureManager.GetFeatures(False)``
    (``TopLevelOnly=False``) and identifies mate features by their type name.
    For each mate:

      - **Layer 1 (existence):** Mate appears with a valid type name
        (``startswith("Mate")``, not ``MateGroup``, not ``Material``).
      - **Layer 2 (error code):** ``GetErrorCode2()`` returns clean (0).
      - **Layer 3 (solver health):** After ``ForceRebuild3(False)``, the mate is
        not suppressed-due-to-error.

    Args:
        asm_doc: the assembly document (``IModelDoc2``).
        mod: the gen_py wrapper module.

    Returns:
        A list of per-mate result dicts, each with::

            {
                "name": str,          # feature name (e.g. "Coincident1")
                "type": str,          # type name (e.g. "MateDistance")
                "error_code": int,    # GetErrorCode2() value
                "solved": bool,       # True if mate is healthy and solved
                "suppressed": bool,   # True if suppressed due to error
            }
    """
    if mod is None:
        mod = wrapper_module()

    # Force rebuild first to ensure solver has processed all mates
    try:
        asm_doc.ForceRebuild3(True)
    except Exception:
        pass

    results: list[dict[str, Any]] = []

    # Flat enumeration: GetFeatures(False) returns individual mate features
    # as their own entries (not collapsed into the MateGroup folder).
    try:
        fm = asm_doc.FeatureManager
        feats = fm.GetFeatures(False)
    except Exception:
        return results

    if not feats:
        return results

    for feat in feats:
        try:
            ifeat = typed(feat, "IFeature", module=mod)
            type_name = ifeat.GetTypeName2()

            # Keep only mate features: startswith("Mate"), not MateGroup, not Material
            if not type_name.startswith("Mate"):
                continue
            if type_name == "MateGroup":
                continue
            if "Material" in type_name:
                continue

            mate_result: dict[str, Any] = {
                "name": ifeat.Name,
                "type": type_name,
                "error_code": -1,
                "solved": False,
                "suppressed": False,
            }

            # Check if suppressed
            # Note: GetSuppression2 may not exist on all IFeature wrappers.
            # Fall back to IsSuppressed2 or treat as not suppressed.
            try:
                suppress_state = ifeat.GetSuppression2()
                if isinstance(suppress_state, tuple):
                    suppress_state = suppress_state[0]
                mate_result["suppressed"] = suppress_state == 0
            except Exception:
                try:
                    suppress_state = ifeat.IsSuppressed2()
                    if isinstance(suppress_state, tuple):
                        suppress_state = suppress_state[0]
                    mate_result["suppressed"] = bool(suppress_state)
                except Exception:
                    pass

            # Check error code
            # GetErrorCode2 returns (code, has_error_flag) tuple.
            # The has_error_flag is True when the code represents an actual error.
            # When False, the code is a status/info code (not an error).
            has_error = True  # default to assuming error
            try:
                error_result = ifeat.GetErrorCode2()
                if isinstance(error_result, tuple):
                    error_code = error_result[0]
                    has_error = error_result[1]
                else:
                    error_code = error_result
                mate_result["error_code"] = error_code
            except Exception:
                try:
                    error_code = ifeat.GetErrorCode()
                    if isinstance(error_code, tuple):
                        error_code = error_code[0]
                    mate_result["error_code"] = error_code
                except Exception:
                    pass

            # Solved = not suppressed AND (no error flag OR error_code == 0)
            mate_result["solved"] = (
                not mate_result["suppressed"]
                and (not has_error or mate_result["error_code"] == 0)
            )

            results.append(mate_result)
        except Exception:
            continue

    return results
