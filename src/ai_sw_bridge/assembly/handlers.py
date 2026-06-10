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
from pathlib import Path
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
    "width": 11,           # swMateWIDTH (two-reference-set, W12)
    # Mechanical/kinematic mates (W46 Tier-1) — typelib-verified from
    # swconst.tlb v32 (NOT API-doc guesses: gear was 10 not the doc's 12;
    # 12=LOCKTOSKETCH would silently misfire).
    "gear": 10,            # swMateGEAR
    # NOTE: screw (swMateSCREW=17) is FROZEN — the pitch parameter is not
    # controllable out-of-process (clamps to the 1 mm kernel default via all
    # three characterized paths). See docs/DEFERRED.md "W46 screw mate".
    # Mechanical mates (W47 Tier-2) — asymmetric reference sets, typelib-verified.
    "rackpinion": 13,      # swMateRACKPINION
    "camfollower": 9,      # swMateCAMFOLLOWER
}

# swRackPinionMateDistanceOptions_e (swconst.tlb): gates how DiameterVal reads.
_RP_PINION_PITCH_DIA = 0     # swPinionPitchDiameter
_RP_RACK_TRAVEL_PER_REV = 1  # swRackTravelPerRevolution

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
    "width": "IWidthMateFeatureData",
    "gear": "IGearMateFeatureData",
    # screw FROZEN (W46) — see MATE_TYPE_ENUMS note + docs/DEFERRED.md.
    "rackpinion": "IRackPinionMateFeatureData",
    "camfollower": "ICamFollowerMateFeatureData",
}


def _rpy_to_transform(
    roll_deg: float, pitch_deg: float, yaw_deg: float,
    tx_m: float, ty_m: float, tz_m: float,
) -> list[float]:
    """Build 16-element SW IMathTransform array: R = Rz . Ry . Rx, row-major.

    Layout: [r00,r01,r02, r10,r11,r12, r20,r21,r22, tx,ty,tz, scale, 0,0,0]
    Translation is in metres. Convention pinned in W13 spike.
    """
    rx, ry, rz = (
        math.radians(roll_deg),
        math.radians(pitch_deg),
        math.radians(yaw_deg),
    )
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    return [
        cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx,
        sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx,
        -sy,     cy * sx,               cy * cx,
        tx_m, ty_m, tz_m,
        1.0, 0.0, 0.0, 0.0,
    ]


def place_components(
    sw: Any,
    asm_doc: Any,
    components: list[dict[str, Any]],
    *,
    mod: Any | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Place all components into an assembly document.

    Placement is **translation + rotation** (W13): ``AddComponent4`` places at
    ``xyz_mm``; a non-zero ``rpy_deg`` is then applied via
    ``IMathUtility.CreateTransform`` → ``IComponent2.SetTransformAndSolve``
    (seat-proven — a bare ``Transform2`` propput does NOT move geometry).
    A zero/absent ``rpy_deg`` stays on the fast translation-only path.

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

        # Apply rotation if rpy_deg is present and non-zero
        rpy = transform.get("rpy_deg")
        if rpy is not None and any(float(v) != 0.0 for v in rpy):
            try:
                mu = typed(sw.GetMathUtility, "IMathUtility", module=mod)
                arr = _rpy_to_transform(
                    float(rpy[0]), float(rpy[1]), float(rpy[2]),
                    x_m, y_m, z_m,
                )
                varr = w32.VARIANT(
                    pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(arr)
                )
                xform = mu.CreateTransform(varr)
                comp_typed = typed_qi(comp, "IComponent2", module=mod)
                comp_typed.Transform2 = xform
                comp_typed.SetTransformAndSolve(xform)
            except Exception as exc:
                return placed, (
                    f"component {cid!r}: rotation transform failed: {exc!r}"
                )

        placed[cid] = comp

    return placed, None


def _create_width_mate(
    asm_doc: Any,
    typed_asm: Any,
    placed: dict[str, Any],
    mate_spec: dict[str, Any],
    mod: Any,
) -> tuple[Any | None, str | None]:
    """Width mate handler — two reference sets via WidthSelection/TabSelection.

    Lifted from the seat-proven spike_phase3_2C recipe. Width is a structural
    departure from the symmetric a/b types: it takes two SAFEARRAYs of 2 faces
    each (groove faces → WidthSelection, tab faces → TabSelection) and does
    NOT use EntitiesToMate or MateAlignment.
    """
    width_refs = mate_spec.get("width_faces", [])
    tab_refs = mate_spec.get("tab_faces", [])

    def _resolve_set(
        refs: list[dict[str, Any]], label: str
    ) -> tuple[list[Any], str | None]:
        entities: list[Any] = []
        for j, ref in enumerate(refs):
            cid = ref["component"]
            comp = placed.get(cid)
            if comp is None:
                return [], f"{label}[{j}]: component {cid!r} not placed"
            resolution = resolve_component_face(
                asm_doc, comp, ref["face_ref"], mod=mod
            )
            if not resolution.ok:
                return [], (
                    f"{label}[{j}]: face unresolved on {cid!r} "
                    f"(method={resolution.method}, error={resolution.error})"
                )
            entities.append(resolution.entity)
        return entities, None

    width_entities, w_err = _resolve_set(width_refs, "width_faces")
    if w_err:
        return None, w_err

    tab_entities, t_err = _resolve_set(tab_refs, "tab_faces")
    if t_err:
        return None, t_err

    try:
        mate_data = typed_asm.CreateMateData(11)
        if mate_data is None:
            return None, "CreateMateData(11) returned None"

        w_iface = typed_qi(
            mate_data, "IWidthMateFeatureData", module=mod
        )

        width_arr = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
            tuple(width_entities),
        )
        tab_arr = w32.VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
            tuple(tab_entities),
        )
        w_iface.WidthSelection = width_arr
        w_iface.TabSelection = tab_arr

        mate_ret = typed_asm.CreateMate(mate_data)
    except Exception as exc:
        return None, f"width mate pipeline failed: {exc!r}"

    if mate_ret is None or isinstance(mate_ret, int):
        try:
            mfd = typed_qi(mate_data, "IMateFeatureData", module=mod)
            es = mfd.ErrorStatus
        except Exception:
            es = "?"
        return None, f"CreateMate returned None (ErrorStatus={es})"

    try:
        ifeat = typed(mate_ret, "IFeature", module=mod)
        feat_type = ifeat.GetTypeName2()
        if "Mate" not in feat_type and "mate" not in feat_type.lower():
            return None, f"unexpected feature type: {feat_type}"
    except Exception as exc:
        return None, f"mate verification failed: {exc!r}"

    return mate_ret, None


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

    # Width mate: two reference sets (width_faces → WidthSelection,
    # tab_faces → TabSelection). Never touches the symmetric a/b path.
    if mate_type_str == "width":
        return _create_width_mate(asm_doc, typed_asm, placed, mate_spec, mod)

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
        # Symmetric mates expose a settable EntitiesToMate ARRAY property; the
        # asymmetric mechanical mates (rack-pinion, cam-follower) expose only the
        # indexed PROPPUT, which makepy surfaces as the method
        # SetEntitiesToMate(index, entity) — assigning the array raises
        # AttributeError there. Try the array form, fall back per-index (W47).
        try:
            typed_iface.EntitiesToMate = w32.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(faces)
            )
        except AttributeError:
            for _i, _ent in enumerate(faces):
                typed_iface.SetEntitiesToMate(_i, _ent)

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

        # Gear (W46): ratio is a NUMERATOR/DENOMINATOR pair. A zero/unset ratio
        # makes CreateMate return None, so this MUST precede CreateMate.
        #
        # TRANSPOSED SETTER (seat-proven, spikes/v0_2x/mech_mate_gear_transform):
        # SW's COM property setters are crossed — assigning .GearRatioNumerator
        # writes the DENOMINATOR slot and vice versa (the makepy-mistype family).
        # The transform is deterministic and geometry-independent: set(2,1)
        # persisted (1,2), set(1,2)->(2,1), set(3,2)->(2,3) — always the
        # transpose, identical under both EntitiesToMate orders. So we swap the
        # assignment to compensate: the user's numerator is fed through the
        # .GearRatioDenominator setter (which writes the numerator slot), and
        # vice versa, making the PERSISTED ratio == the requested numerator:
        # denominator. Verified end-to-end by spikes/v0_2x/mech_mate_gear_pae.
        if mate_type_str == "gear":
            ratio = mate_spec.get("ratio") or {}
            num = ratio.get("numerator")
            den = ratio.get("denominator")
            if num is not None:
                typed_iface.GearRatioDenominator = float(num)
            if den is not None:
                typed_iface.GearRatioNumerator = float(den)

        # Rack-pinion (W47): DiameterType (swRackPinionMateDistanceOptions_e)
        # gates how DiameterVal reads — it MUST be set BEFORE the scalar or the
        # kernel reverts it (the screw-toggle lesson). Exactly one of
        # pitch_diameter_mm / rack_travel_per_rev_mm is provided (validator-
        # enforced); it selects the DiameterType. The scalar round-trips
        # faithfully (seat-proven, spikes/v0_2x/mech_mate_tier2_rack_cam) — no
        # transpose, unlike gear. Entities go in via SetEntitiesToMate above:
        # rack (linear_edge) at index 0, pinion (cylinder) at index 1.
        if mate_type_str == "rackpinion":
            pitch_dia_mm = mate_spec.get("pitch_diameter_mm")
            travel_mm = mate_spec.get("rack_travel_per_rev_mm")
            if pitch_dia_mm is not None:
                typed_iface.DiameterType = _RP_PINION_PITCH_DIA
                typed_iface.DiameterVal = float(pitch_dia_mm) / 1000.0
            elif travel_mm is not None:
                typed_iface.DiameterType = _RP_RACK_TRAVEL_PER_REV
                typed_iface.DiameterVal = float(travel_mm) / 1000.0

        # Cam-follower (W47): no coupling scalar — EntitiesToMate (cam non-planar
        # face at index 0, follower cylinder at index 1) + MateAlignment only.

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


PLANE_FULL_NAME = {
    "front": "Front Plane",
    "top": "Top Plane",
    "right": "Right Plane",
}


def mirror_components(
    sw: Any,
    asm_doc: Any,
    placed: dict[str, Any],
    patterns: list[dict[str, Any]],
    output_path: str,
    *,
    mod: Any | None = None,
) -> tuple[int, str | None]:
    """Mirror seed components about a reference plane.

    Uses the seat-proven W22 recipe: ``IAssemblyDoc.MirrorComponents`` (v1,
    9 args) with raw ``PyIDispatch`` pointers (``_oleobj_``). The assembly
    must be saved before mirroring (mirror creates new part files on disk).

    Args:
        sw: the ``SldWorks.Application`` COM object.
        asm_doc: the assembly document (``IModelDoc2``).
        placed: map of ``component_id → IComponent2`` from ``place_components``.
        patterns: list of mirror pattern dicts (``seed``, ``plane``,
            optional ``name_modifier``).
        output_path: the assembly ``.sldasm`` path (used to determine the
            mirror file output directory).
        mod: the gen_py wrapper module.

    Returns:
        ``(mirrored_count, error)`` — the number of components successfully
        mirrored, or ``(0, message)`` on the first failure.
    """
    if mod is None:
        mod = wrapper_module()

    import pythoncom
    from win32com.client import VARIANT

    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
    asm_dir = str(Path(output_path).parent)

    # Save assembly before mirror (mirror creates new part files)
    try:
        asm_doc.SaveAs3(output_path, 0, 2)
    except Exception as exc:
        return 0, f"SaveAs3 before mirror failed: {exc!r}"

    mirrored = 0
    for i, pat in enumerate(patterns):
        seed_id = pat["seed"]
        comp = placed.get(seed_id)
        if comp is None:
            return mirrored, f"pattern[{i}]: seed {seed_id!r} not placed"

        plane_name = PLANE_FULL_NAME[pat["plane"]]

        # Select mirror plane to get the raw entity
        asm_doc.ClearSelection2(True)
        try:
            ok = asm_doc.SelectByID(plane_name, "PLANE", 0, 0, 0)
        except Exception as exc:
            return mirrored, f"pattern[{i}]: SelectByID plane: {exc!r}"
        if not ok:
            return mirrored, f"pattern[{i}]: could not select plane {plane_name!r}"

        sel_mgr = asm_doc.SelectionManager
        plane_entity = sel_mgr.GetSelectedObject6(1, -1)
        if plane_entity is None:
            return mirrored, f"pattern[{i}]: plane entity is None"

        # Raw PyIDispatch pointers (gen_py wrappers cannot be marshaled)
        raw_plane = plane_entity._oleobj_
        raw_comp = comp._oleobj_

        comp_array = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, (raw_comp,)
        )

        name_modifier = pat.get("name_modifier", 0)

        try:
            ret = typed_asm.MirrorComponents(
                raw_plane,
                comp_array,
                comp_array,
                None,
                False,
                int(name_modifier),
                "",
                asm_dir,
                False,
            )
        except Exception as exc:
            return mirrored, f"pattern[{i}]: MirrorComponents raised: {exc!r}"

        if ret is None:
            return mirrored, (
                f"pattern[{i}]: MirrorComponents returned None "
                f"(seed={seed_id!r}, plane={pat['plane']!r})"
            )

        mirrored += 1

    return mirrored, None


# Map direction spec values to assembly reference plane names for SelectByID2.
# SW default planes: Front = XY (Z normal), Top = XZ (Y normal), Right = YZ (X normal).
_DIRECTION_TO_PLANE = {
    "front": "Front Plane",
    "top": "Top Plane",
    "right": "Right Plane",
}


def create_exploded_view(
    asm_doc: Any,
    placed: dict[str, Any],
    view_spec: dict[str, Any],
    *,
    mod: Any | None = None,
) -> tuple[int, str | None]:
    """Create an exploded view with one or more explode steps.

    Recipe (seat-proven W32v):
      1. ``IAssemblyDoc.CreateExplodedView()`` → creates empty view.
      2. For each step:
         a. ``IComponent2.Select2(False, 1)`` → select component to explode.
         b. ``SelectByID2("<PlaneName>@<AsmName>", "PLANE", 0,0,0, True, 0, None, 0)``
            → append direction reference (assembly ref plane).
         c. ``IConfiguration.AddExplodeStep(dist_m, False, False, False)``
            → returns IExplodeStep with component auto-populated from selection.

    Args:
        asm_doc: the assembly document (``IModelDoc2``).
        placed: mapping of ``id → IComponent2`` from ``place_components``.
        view_spec: exploded view spec dict with ``name`` and ``steps[]``.
        mod: the gen_py wrapper module.

    Returns:
        ``(step_count, error)`` where ``step_count`` is the number of
        successfully created steps and ``error`` is ``None`` on success.
    """
    if mod is None:
        mod = wrapper_module()

    typed_asm = typed(asm_doc, "IAssemblyDoc", module=mod)
    typed_model = typed(asm_doc, "IModelDoc2", module=mod)

    # Step 1: Create empty exploded view
    try:
        view_ok = typed_asm.CreateExplodedView()
    except Exception as exc:
        return 0, f"CreateExplodedView raised: {exc!r}"

    if not view_ok:
        return 0, "CreateExplodedView returned False"

    # Get assembly title for direction reference SelectByID2
    try:
        asm_title = asm_doc.GetTitle
        if callable(asm_title):
            asm_title = asm_title()
        asm_name = asm_title.replace(".SLDASM", "") if asm_title else "Asm1"
    except Exception:
        asm_name = "Asm1"

    # Get IConfiguration for AddExplodeStep
    try:
        config = typed_model.GetActiveConfiguration()
    except Exception as exc:
        return 0, f"GetActiveConfiguration failed: {exc!r}"

    # Wrap config in early-bound IConfiguration for AddExplodeStep
    cfg_cls = getattr(mod, "IConfiguration", None)
    if cfg_cls is None:
        return 0, "IConfiguration not in gen_py module"
    typed_config = cfg_cls(config._oleobj_)

    sel_mgr = typed_model.SelectionManager
    model_ext = typed_model.Extension

    step_count = 0

    for i, step_spec in enumerate(view_spec.get("steps", [])):
        # Resolve component objects
        comp_ids = step_spec.get("components", [])
        comp_objects = []
        for cid in comp_ids:
            comp = placed.get(cid)
            if comp is None:
                return step_count, (
                    f"step[{i}]: component {cid!r} not found in placed components"
                )
            comp_objects.append(comp)

        # Resolve direction plane name
        direction = step_spec.get("direction", "front")
        plane_name = _DIRECTION_TO_PLANE.get(direction)
        if plane_name is None:
            return step_count, (
                f"step[{i}]: unknown direction {direction!r}"
            )

        dist_mm = step_spec.get("distance_mm", 50.0)
        dist_m = float(dist_mm) / 1000.0
        reverse = bool(step_spec.get("reverse", False))

        # Clear selection before each step
        try:
            typed_model.ClearSelection2(True)
        except Exception:
            pass

        # Select first component with mark=1
        first_comp = comp_objects[0]
        try:
            sel_ok = first_comp.Select2(False, 1)
        except Exception as exc:
            return step_count, (
                f"step[{i}]: Select2 failed on {comp_ids[0]!r}: {exc!r}"
            )
        if not sel_ok:
            return step_count, (
                f"step[{i}]: Select2 returned False on {comp_ids[0]!r}"
            )

        # Append direction reference plane with mark=0
        dir_ref = f"{plane_name}@{asm_name}"
        try:
            sel_dir = model_ext.SelectByID2(
                dir_ref, "PLANE", 0, 0, 0, True, 0, None, 0
            )
        except Exception as exc:
            return step_count, (
                f"step[{i}]: SelectByID2({dir_ref!r}) raised: {exc!r}"
            )

        # Verify 2-entity selection
        try:
            sel_count = sel_mgr.GetSelectedObjectCount2(-1)
        except Exception:
            sel_count = 0

        if sel_count < 2:
            return step_count, (
                f"step[{i}]: selection count={sel_count} (expected >=2)"
            )

        # Create explode step
        try:
            step = typed_config.AddExplodeStep(
                dist_m, reverse, False, False
            )
        except Exception as exc:
            return step_count, (
                f"step[{i}]: AddExplodeStep raised: {exc!r}"
            )

        if step is None or step == 0:
            return step_count, (
                f"step[{i}]: AddExplodeStep returned None/0"
            )

        step_count += 1

    return step_count, None
