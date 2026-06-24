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

from .schema import MATE_ALIGNMENTS, MATE_TYPES, SLOT_CONSTRAINTS


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

    patterns = spec.get("component_patterns")
    if patterns is not None:
        if not isinstance(patterns, list):
            raise AssemblyValidationError(
                "component_patterns must be an array", "/component_patterns"
            )
        _check_component_patterns(patterns, component_ids)

    arrays = spec.get("component_arrays")
    if arrays is not None:
        if not isinstance(arrays, list):
            raise AssemblyValidationError(
                "component_arrays must be an array", "/component_arrays"
            )
        _check_component_arrays(arrays, component_ids)

    exploded = spec.get("exploded_views")
    if exploded is not None:
        if not isinstance(exploded, list):
            raise AssemblyValidationError(
                "exploded_views must be an array", "/exploded_views"
            )
        _check_exploded_views(exploded, component_ids)


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
            raise AssemblyValidationError(f"duplicate component id {cid!r}", path)
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


def _check_transform(transform: Any, cid: str, parent_path: str) -> None:
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


def _check_mates(mates: list[dict[str, Any]], component_ids: set[str]) -> None:
    for i, mate in enumerate(mates):
        path = f"/mates/{i}"
        if not isinstance(mate, dict):
            raise AssemblyValidationError("mate must be a dict", path)

        mtype = mate.get("type")
        if mtype not in MATE_TYPES:
            raise AssemblyValidationError(
                f"mate type {mtype!r} not in {sorted(MATE_TYPES)}", path
            )

        if mtype == "width":
            for scalar in ("value_mm", "value_deg", "limit", "a", "b"):
                if mate.get(scalar) is not None:
                    raise AssemblyValidationError(
                        f"width mate does not accept {scalar!r} "
                        f"(uses width_faces/tab_faces only)",
                        path,
                    )
            for set_key in ("width_faces", "tab_faces"):
                face_set = mate.get(set_key)
                if not isinstance(face_set, list) or len(face_set) != 2:
                    raise AssemblyValidationError(
                        f"width mate requires {set_key} with exactly 2 refs",
                        path,
                    )
                for j, ref in enumerate(face_set):
                    ref_path = f"{path}/{set_key}/{j}"
                    if not isinstance(ref, dict):
                        raise AssemblyValidationError(
                            f"{set_key}[{j}] must be a dict", ref_path
                        )
                    ref_comp = ref.get("component")
                    if not isinstance(ref_comp, str) or not ref_comp:
                        raise AssemblyValidationError(
                            f"{set_key}[{j}].component must be a non-empty string",
                            ref_path,
                        )
                    if ref_comp not in component_ids:
                        raise AssemblyValidationError(
                            f"{set_key}[{j}].component {ref_comp!r} not found in "
                            f"component ids {sorted(component_ids)}",
                            ref_path,
                        )
                    face_ref = ref.get("face_ref")
                    if not isinstance(face_ref, dict) or not face_ref:
                        raise AssemblyValidationError(
                            f"{set_key}[{j}].face_ref must be a non-empty dict",
                            ref_path,
                        )
            continue

        # Hinge (W48 Tier-3): compound concentric+coincident, TWO role pairs
        # (concentric_faces/coincident_faces) — never the symmetric a/b path.
        if mtype == "hinge":
            for scalar in ("value_mm", "value_deg", "limit", "a", "b"):
                if mate.get(scalar) is not None:
                    raise AssemblyValidationError(
                        f"hinge mate does not accept {scalar!r} (uses "
                        f"concentric_faces/coincident_faces only)",
                        path,
                    )
            hinge_align = mate.get("alignment")
            if hinge_align is not None and hinge_align not in MATE_ALIGNMENTS:
                raise AssemblyValidationError(
                    f"mate alignment {hinge_align!r} not in "
                    f"{sorted(MATE_ALIGNMENTS)}",
                    path,
                )
            for set_key in ("concentric_faces", "coincident_faces"):
                face_set = mate.get(set_key)
                if not isinstance(face_set, list) or len(face_set) != 2:
                    raise AssemblyValidationError(
                        f"hinge mate requires {set_key} with exactly 2 refs",
                        path,
                    )
                for j, ref in enumerate(face_set):
                    ref_path = f"{path}/{set_key}/{j}"
                    if not isinstance(ref, dict):
                        raise AssemblyValidationError(
                            f"{set_key}[{j}] must be a dict", ref_path
                        )
                    ref_comp = ref.get("component")
                    if not isinstance(ref_comp, str) or not ref_comp:
                        raise AssemblyValidationError(
                            f"{set_key}[{j}].component must be a non-empty string",
                            ref_path,
                        )
                    if ref_comp not in component_ids:
                        raise AssemblyValidationError(
                            f"{set_key}[{j}].component {ref_comp!r} not found in "
                            f"component ids {sorted(component_ids)}",
                            ref_path,
                        )
                    face_ref = ref.get("face_ref")
                    if not isinstance(face_ref, dict) or not face_ref:
                        raise AssemblyValidationError(
                            f"{set_key}[{j}].face_ref must be a non-empty dict",
                            ref_path,
                        )
            continue

        alignment = mate.get("alignment")
        if alignment is not None and alignment not in MATE_ALIGNMENTS:
            raise AssemblyValidationError(
                f"mate alignment {alignment!r} not in {sorted(MATE_ALIGNMENTS)}",
                path,
            )

        if mtype == "coincident" and alignment is None:
            raise AssemblyValidationError("coincident mate requires 'alignment'", path)

        # Advanced mates (W75). symmetric requires a symmetry_plane (RefPlane
        # name); the profile_center scalars (offset_mm/flip/lock_rotation) belong
        # only to profile_center. Fail closed on cross-type leakage.
        if mtype == "symmetric":
            sp = mate.get("symmetry_plane")
            if not isinstance(sp, str) or not sp.strip():
                raise AssemblyValidationError(
                    "symmetric mate requires 'symmetry_plane' (a reference "
                    "plane feature name, e.g. 'Right Plane')",
                    path,
                )
        elif mate.get("symmetry_plane") is not None:
            raise AssemblyValidationError(
                f"{mtype} mate does not accept 'symmetry_plane'", path
            )
        if mtype != "profile_center":
            for adv in ("offset_mm", "flip", "lock_rotation"):
                if mate.get(adv) is not None:
                    raise AssemblyValidationError(
                        f"{mtype} mate does not accept {adv!r}", path
                    )

        # linear_coupler (W75b): requires a positive ratio; reverse optional.
        # The ratio/reverse fields belong only to linear_coupler.
        if mtype == "linear_coupler":
            for key in ("ratio_numerator", "ratio_denominator"):
                v = mate.get(key)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
                    raise AssemblyValidationError(
                        f"linear_coupler mate requires {key!r} as a positive number",
                        path,
                    )
        else:
            for key in ("ratio_numerator", "ratio_denominator", "reverse"):
                if mate.get(key) is not None:
                    raise AssemblyValidationError(
                        f"{mtype} mate does not accept {key!r}", path
                    )

        value_mm = mate.get("value_mm")
        if mtype == "distance":
            if value_mm is None:
                raise AssemblyValidationError("distance mate requires 'value_mm'", path)
            if not isinstance(value_mm, (int, float)) or value_mm <= 0:
                raise AssemblyValidationError(
                    f"distance mate value_mm must be a positive number, got {value_mm!r}",
                    path,
                )
        elif mtype in (
            "concentric",
            "parallel",
            "perpendicular",
            "tangent",
            "symmetric",
            "profile_center",
            "linear_coupler",
        ):
            if value_mm is not None:
                raise AssemblyValidationError(
                    f"{mtype} mate does not accept 'value_mm' (geometric constraint)",
                    path,
                )
            if mate.get("value_deg") is not None:
                raise AssemblyValidationError(
                    f"{mtype} mate does not accept 'value_deg'",
                    path,
                )

        if mtype == "angle":
            value_deg = mate.get("value_deg")
            if value_deg is None:
                raise AssemblyValidationError("angle mate requires 'value_deg'", path)
            if not isinstance(value_deg, (int, float)):
                raise AssemblyValidationError(
                    f"angle mate value_deg must be a number, got {value_deg!r}",
                    path,
                )
            if value_mm is not None:
                raise AssemblyValidationError(
                    "angle mate does not accept 'value_mm'; use 'value_deg'",
                    path,
                )

        # Mechanical mates (W46 Tier-1) — gear only; screw FROZEN (COM wall,
        # see docs/DEFERRED.md "W46 screw mate").
        if mtype == "gear":
            ratio = mate.get("ratio")
            if not isinstance(ratio, dict):
                raise AssemblyValidationError(
                    "gear mate requires 'ratio' with 'numerator' and " "'denominator'",
                    path,
                )
            for key in ("numerator", "denominator"):
                v = ratio.get(key)
                if not isinstance(v, (int, float)) or v <= 0:
                    raise AssemblyValidationError(
                        f"gear ratio {key!r} must be a positive number, " f"got {v!r}",
                        f"{path}/ratio",
                    )

        # Mechanical mates (W47 Tier-2) — rack-pinion + cam-follower.
        if mtype == "rackpinion":
            pitch_dia = mate.get("pitch_diameter_mm")
            travel = mate.get("rack_travel_per_rev_mm")
            provided = [v for v in (pitch_dia, travel) if v is not None]
            if len(provided) != 1:
                raise AssemblyValidationError(
                    "rackpinion mate requires EXACTLY ONE of "
                    "'pitch_diameter_mm' or 'rack_travel_per_rev_mm'",
                    path,
                )
            if not isinstance(provided[0], (int, float)) or provided[0] <= 0:
                raise AssemblyValidationError(
                    f"rackpinion scalar must be a positive number, "
                    f"got {provided[0]!r}",
                    path,
                )
        # camfollower: no coupling scalar — type + a + b (already required) is
        # sufficient; the cam (a) and follower (b) entity refs drive resolution.

        # Slot (W48 Tier-3): a/b = slot face + pin face (validated by the a/b loop
        # below). constraint selects the positional mode; distance/percent modes
        # require their scalar.
        if mtype == "slot":
            constraint = mate.get("constraint", "free")
            if constraint not in SLOT_CONSTRAINTS:
                raise AssemblyValidationError(
                    f"slot constraint {constraint!r} not in "
                    f"{sorted(SLOT_CONSTRAINTS)}",
                    path,
                )
            if constraint == "distance":
                dval = mate.get("distance_mm")
                if not isinstance(dval, (int, float)) or dval <= 0:
                    raise AssemblyValidationError(
                        "slot 'distance' constraint requires a positive "
                        "'distance_mm'",
                        path,
                    )
            elif constraint == "percent":
                pval = mate.get("percent")
                if not isinstance(pval, (int, float)) or not (0 <= pval <= 100):
                    raise AssemblyValidationError(
                        "slot 'percent' constraint requires 'percent' in " "[0, 100]",
                        path,
                    )

        limit = mate.get("limit")
        if limit is not None:
            if mtype not in ("distance", "angle"):
                raise AssemblyValidationError(
                    f"'limit' is only supported for distance and angle mates, "
                    f"not {mtype!r}",
                    path,
                )
            if mtype == "distance":
                min_mm = limit.get("min_mm")
                max_mm = limit.get("max_mm")
                if min_mm is None or max_mm is None:
                    raise AssemblyValidationError(
                        "distance limit requires both 'min_mm' and 'max_mm'",
                        f"{path}/limit",
                    )
                if min_mm >= max_mm:
                    raise AssemblyValidationError(
                        f"distance limit min_mm ({min_mm}) must be less than "
                        f"max_mm ({max_mm})",
                        f"{path}/limit",
                    )
            elif mtype == "angle":
                min_deg = limit.get("min_deg")
                max_deg = limit.get("max_deg")
                if min_deg is None or max_deg is None:
                    raise AssemblyValidationError(
                        "angle limit requires both 'min_deg' and 'max_deg'",
                        f"{path}/limit",
                    )
                if min_deg >= max_deg:
                    raise AssemblyValidationError(
                        f"angle limit min_deg ({min_deg}) must be less than "
                        f"max_deg ({max_deg})",
                        f"{path}/limit",
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


def _check_component_patterns(
    patterns: list[dict[str, Any]], component_ids: set[str]
) -> None:
    for i, pat in enumerate(patterns):
        path = f"/component_patterns/{i}"
        if not isinstance(pat, dict):
            raise AssemblyValidationError("pattern must be a dict", path)

        ptype = pat.get("type")
        if ptype != "mirror":
            raise AssemblyValidationError(
                f"unknown pattern type {ptype!r} (only 'mirror' is supported)",
                path,
            )

        seed = pat.get("seed")
        if not isinstance(seed, str) or not seed:
            raise AssemblyValidationError(
                "mirror pattern requires a non-empty 'seed' string", path
            )
        if seed not in component_ids:
            raise AssemblyValidationError(
                f"mirror pattern seed {seed!r} not found in component ids "
                f"{sorted(component_ids)}",
                path,
            )

        plane = pat.get("plane")
        if plane not in ("front", "top", "right"):
            raise AssemblyValidationError(
                f"mirror pattern plane must be 'front', 'top', or 'right', "
                f"got {plane!r}",
                path,
            )

        name_modifier = pat.get("name_modifier")
        if name_modifier is not None:
            if not isinstance(name_modifier, int) or name_modifier < 0:
                raise AssemblyValidationError(
                    f"mirror pattern name_modifier must be a non-negative "
                    f"integer, got {name_modifier!r}",
                    path,
                )


def _check_component_arrays(
    arrays: list[dict[str, Any]], component_ids: set[str]
) -> None:
    """Validate component_arrays entries.

    Checks: id present + unique, type is linear or circular, count >= 2,
    positive spacing_mm/radius_mm, non-zero direction/axis, valid part
    reference, expanded-id collisions with existing component ids.
    """
    import math

    seen_array_ids: set[str] = set()
    expanded_ids: set[str] = set(component_ids)

    for i, arr in enumerate(arrays):
        path = f"/component_arrays/{i}"
        if not isinstance(arr, dict):
            raise AssemblyValidationError("array must be a dict", path)

        aid = arr.get("id")
        if not isinstance(aid, str) or not aid:
            raise AssemblyValidationError("array id must be a non-empty string", path)
        if aid in seen_array_ids:
            raise AssemblyValidationError(f"duplicate array id {aid!r}", path)
        seen_array_ids.add(aid)

        atype = arr.get("type")
        if atype not in ("linear", "circular"):
            raise AssemblyValidationError(
                f"unknown array type {atype!r} (must be 'linear' or 'circular')",
                path,
            )

        count = arr.get("count")
        if not isinstance(count, int) or count < 2:
            raise AssemblyValidationError(
                f"array count must be an integer >= 2, got {count!r}", path
            )

        # Check part reference
        has_part = "part" in arr and arr["part"] is not None
        has_part_spec = "part_spec" in arr and arr["part_spec"] is not None
        if not has_part and not has_part_spec:
            raise AssemblyValidationError(
                f"array {aid!r} must have either 'part' or 'part_spec'", path
            )
        if has_part and has_part_spec:
            raise AssemblyValidationError(
                f"array {aid!r} has both 'part' and 'part_spec'; "
                "exactly one is required",
                path,
            )

        if atype == "linear":
            spacing = arr.get("spacing_mm")
            if not isinstance(spacing, (int, float)) or spacing <= 0:
                raise AssemblyValidationError(
                    f"linear array spacing_mm must be a positive number, "
                    f"got {spacing!r}",
                    path,
                )

            direction = arr.get("direction")
            if (
                not isinstance(direction, (list, tuple))
                or len(direction) != 3
                or not all(isinstance(v, (int, float)) for v in direction)
            ):
                raise AssemblyValidationError(
                    "linear array direction must be a 3-element numeric array",
                    path,
                )
            dlen = math.sqrt(sum(v**2 for v in direction))
            if dlen < 1e-12:
                raise AssemblyValidationError(
                    "linear array direction must be non-zero", path
                )

        elif atype == "circular":
            radius = arr.get("radius_mm")
            if not isinstance(radius, (int, float)) or radius <= 0:
                raise AssemblyValidationError(
                    f"circular array radius_mm must be a positive number, "
                    f"got {radius!r}",
                    path,
                )

            axis = arr.get("axis")
            if (
                not isinstance(axis, (list, tuple))
                or len(axis) != 3
                or not all(isinstance(v, (int, float)) for v in axis)
            ):
                raise AssemblyValidationError(
                    "circular array axis must be a 3-element numeric array",
                    path,
                )
            alen = math.sqrt(sum(v**2 for v in axis))
            if alen < 1e-12:
                raise AssemblyValidationError(
                    "circular array axis must be non-zero", path
                )

        # Check expanded-id collisions
        for k in range(count):
            expanded_id = f"{aid}_{k}"
            if expanded_id in expanded_ids:
                raise AssemblyValidationError(
                    f"expanded id {expanded_id!r} collides with existing "
                    f"component or previously expanded id",
                    path,
                )
            expanded_ids.add(expanded_id)


def _check_exploded_views(views: list[dict[str, Any]], component_ids: set[str]) -> None:
    """Validate exploded_views entries.

    Checks: name present + unique, steps non-empty, each step has valid
    component references, positive distance, known direction.
    """
    seen_names: set[str] = set()

    for i, view in enumerate(views):
        path = f"/exploded_views/{i}"
        if not isinstance(view, dict):
            raise AssemblyValidationError("exploded view must be a dict", path)

        name = view.get("name")
        if not isinstance(name, str) or not name:
            raise AssemblyValidationError(
                "exploded view name must be a non-empty string", path
            )
        if name in seen_names:
            raise AssemblyValidationError(
                f"duplicate exploded view name {name!r}", path
            )
        seen_names.add(name)

        steps = view.get("steps")
        if not isinstance(steps, list) or not steps:
            raise AssemblyValidationError(
                f"exploded view {name!r} must have at least one step",
                f"{path}/steps",
            )

        for j, step in enumerate(steps):
            step_path = f"{path}/steps/{j}"
            if not isinstance(step, dict):
                raise AssemblyValidationError("step must be a dict", step_path)

            comps = step.get("components")
            if not isinstance(comps, list) or not comps:
                raise AssemblyValidationError(
                    "step must have at least one component id",
                    f"{step_path}/components",
                )
            for cid in comps:
                if not isinstance(cid, str) or not cid:
                    raise AssemblyValidationError(
                        f"component id must be a non-empty string, got {cid!r}",
                        f"{step_path}/components",
                    )
                if cid not in component_ids:
                    raise AssemblyValidationError(
                        f"component {cid!r} not found in component ids "
                        f"{sorted(component_ids)}",
                        f"{step_path}/components",
                    )

            dist = step.get("distance_mm")
            if not isinstance(dist, (int, float)) or dist <= 0:
                raise AssemblyValidationError(
                    f"step distance_mm must be a positive number, got {dist!r}",
                    f"{step_path}/distance_mm",
                )

            direction = step.get("direction")
            if direction not in ("front", "top", "right"):
                raise AssemblyValidationError(
                    f"step direction must be 'front', 'top', or 'right', "
                    f"got {direction!r}",
                    f"{step_path}/direction",
                )

            reverse = step.get("reverse")
            if reverse is not None and not isinstance(reverse, bool):
                raise AssemblyValidationError(
                    f"step reverse must be a boolean, got {reverse!r}",
                    f"{step_path}/reverse",
                )
