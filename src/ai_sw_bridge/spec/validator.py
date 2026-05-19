"""
Spec validator: schema + dependency graph + locals.txt reference checks.

Three layers of validation, in order. Each returns ValidationError on the
first failure (fail-fast).

1. Schema check: jsonschema against schema.SCHEMA.
2. Reference check (strict topological): every `sketch`, `of_feature`
   reference must point to a feature already declared *earlier* in the list,
   and the referenced feature must be of an appropriate type.
3. Locals check: every {"rhs": "..."} expression's quoted variable refs must
   exist in the spec's `locals` file (if any).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jsonschema

from .schema import (
    SCHEMA,
    SKETCH_TYPES,
    EXTRUDE_TYPES,
    PATTERN_TYPES,
    ALL_TYPES,
)

# Sketch types that reference a parent feature via `of_feature` (sketched
# on the parent extrusion's face) rather than a reference plane. Kept as a
# named constant so the validator's reference check picks up new face-based
# sketches automatically as they're added to the schema.
FACE_SKETCH_TYPES = frozenset(
    {
        "sketch_rectangle_on_face",
        "sketch_circle_on_face",
        "sketch_circles_on_face",
    }
)

# All feature types that take `of_feature` to bind to a parent extrusion's
# face -- includes the face-sketches plus modify primitives like simple_hole
# that drill directly into a face without a separate sketch step.
FACE_BOUND_TYPES = FACE_SKETCH_TYPES | frozenset({"simple_hole"})


class ValidationError(Exception):
    """One validation failure. Use `path` to locate it in the spec.

    Plain Exception subclass (not @dataclass): @dataclass on an Exception
    breaks Exception.args, which downstream frameworks rely on for
    repr/pickling/re-raising.
    """

    def __init__(self, message: str, path: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.path = path

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


# Matches a quoted variable reference in an Equation Manager expression.
# E.g. `"S1B_X"` -> capture S1B_X. Same regex used by ai-sw-observe equations.
QUOTED_VAR_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"')


def _strip_comments(node: Any) -> Any:
    """Recursively remove keys starting with '_' from dicts. Lets specs carry
    `_comment` fields without tripping additionalProperties=false. Returns a
    deep-copy with the keys filtered out; original is untouched."""
    if isinstance(node, dict):
        return {k: _strip_comments(v) for k, v in node.items() if not k.startswith("_")}
    if isinstance(node, list):
        return [_strip_comments(v) for v in node]
    return node


def _check_schema(spec: dict[str, Any]) -> None:
    """Raise ValidationError on the first jsonschema violation."""
    cleaned = _strip_comments(spec)
    try:
        jsonschema.validate(instance=cleaned, schema=SCHEMA)
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path)
        raise ValidationError(message=e.message, path=path or "$") from e


def _check_references(spec: dict[str, Any]) -> None:
    """Strict topological check: every reference points to an earlier feature
    of the right kind."""
    seen: dict[str, str] = {}  # name -> type
    for i, feat in enumerate(spec["features"]):
        name = feat["name"]
        ftype = feat["type"]

        if name in seen:
            raise ValidationError(
                message=f"duplicate feature name '{name}'",
                path=f"features/{i}/name",
            )

        # Reference checks per feature type
        if ftype in FACE_BOUND_TYPES:
            target = feat["of_feature"]
            if target not in seen:
                raise ValidationError(
                    message=f"{ftype} references '{target}', "
                    f"which is not an earlier feature",
                    path=f"features/{i}/of_feature",
                )
            if seen[target] not in EXTRUDE_TYPES:
                raise ValidationError(
                    message=f"{ftype} requires '{target}' to be "
                    f"an extrusion-type feature; got '{seen[target]}'",
                    path=f"features/{i}/of_feature",
                )
        elif ftype in EXTRUDE_TYPES:
            target = feat["sketch"]
            if target not in seen:
                raise ValidationError(
                    message=f"{ftype} references sketch '{target}', "
                    f"which is not an earlier feature",
                    path=f"features/{i}/sketch",
                )
            if seen[target] not in SKETCH_TYPES:
                raise ValidationError(
                    message=f"{ftype} requires '{target}' to be a sketch; "
                    f"got '{seen[target]}'",
                    path=f"features/{i}/sketch",
                )
        elif ftype in PATTERN_TYPES:
            # linear_pattern / mirror_feature: `seed` must name an earlier
            # feature. v1 doesn't constrain the seed's type (any built
            # feature is in principle patternable/mirrorable; SW will
            # error at build time if the geometry doesn't support it).
            target = feat["seed"]
            if target not in seen:
                raise ValidationError(
                    message=f"{ftype} references seed '{target}', "
                    f"which is not an earlier feature",
                    path=f"features/{i}/seed",
                )

        # simple_hole: `depth` is required when end_condition='blind' (the
        # default) and forbidden when end_condition='through_all'. Schema's
        # additionalProperties=false makes this hard to express purely in
        # JSON schema, so enforce here.
        if ftype == "simple_hole":
            end_cond = feat.get("end_condition", "blind")
            has_depth = "depth" in feat
            if end_cond == "blind" and not has_depth:
                raise ValidationError(
                    message="simple_hole with end_condition='blind' requires `depth`",
                    path=f"features/{i}/depth",
                )
            if end_cond == "through_all" and has_depth:
                raise ValidationError(
                    message=(
                        "simple_hole with end_condition='through_all' must not "
                        "include `depth` (the hole runs to the opposite side)"
                    ),
                    path=f"features/{i}/depth",
                )

        # Chamfer mode-conditional field check. The schema can't easily
        # express "if mode=='equal_distance' then `angle` is forbidden and
        # `distance` is required" with `additionalProperties: false` still
        # in force, so we enforce it here for clearer error messages.
        if ftype == "chamfer_edge":
            mode = feat.get("mode")
            has_distance = "distance" in feat
            has_angle = "angle" in feat
            if not has_distance:
                raise ValidationError(
                    message=f"chamfer_edge mode '{mode}' requires `distance`",
                    path=f"features/{i}/distance",
                )
            if mode == "distance_angle" and not has_angle:
                raise ValidationError(
                    message="chamfer_edge mode 'distance_angle' requires `angle`",
                    path=f"features/{i}/angle",
                )
            if mode == "equal_distance" and has_angle:
                raise ValidationError(
                    message=(
                        "chamfer_edge mode 'equal_distance' must not include "
                        "`angle` (the equal-distance case is symmetric)"
                    ),
                    path=f"features/{i}/angle",
                )

        seen[name] = ftype


def _extract_var_refs(value: Any) -> list[str]:
    """If a length value is an {rhs} object, return all quoted var names in it.
    Otherwise []."""
    if isinstance(value, dict) and "rhs" in value:
        return QUOTED_VAR_RE.findall(value["rhs"])
    return []


def _walk_rhs_in_feature(
    node: Any,
    path: str,
) -> "list[tuple[str, str]]":
    """Recursively find every {"rhs": "..."} inside a feature dict.

    Returns [(field_path, var_name)] for each quoted var referenced. Field
    path is a human-readable JSON-pointer-ish locator (e.g. "circles[0].diameter")
    rooted at the feature itself.

    Schema-agnostic by design: any future LENGTH_SCHEMA field is picked up
    automatically without modifying the validator. This was a real footgun
    -- v0.2's hardcoded ("width","height","depth","diameter") tuple would
    silently miss any new length field added in v1.1+.
    """
    out: list[tuple[str, str]] = []
    if isinstance(node, dict):
        if "rhs" in node and isinstance(node["rhs"], str):
            for v in QUOTED_VAR_RE.findall(node["rhs"]):
                out.append((path, v))
        else:
            for k, v in node.items():
                sub_path = f"{path}.{k}" if path else k
                out.extend(_walk_rhs_in_feature(v, sub_path))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            sub_path = f"{path}[{i}]"
            out.extend(_walk_rhs_in_feature(v, sub_path))
    return out


def _collect_rhs_var_refs(spec: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Walk all features recursively; collect every {rhs} reference.

    Returns {var_name: [(feature_name, field_path), ...]} so error messages
    can point to where each ref appears.
    """
    refs: dict[str, list[tuple[str, str]]] = {}
    for feat in spec["features"]:
        feat_name = feat.get("name", "<unnamed>")
        for field_path, var_name in _walk_rhs_in_feature(feat, ""):
            refs.setdefault(var_name, []).append((feat_name, field_path))
    return refs


def _check_locals(spec: dict[str, Any]) -> None:
    """If any feature uses {rhs}, the spec must declare a `locals` path,
    that file must exist, and every quoted var ref must be defined in it."""
    refs = _collect_rhs_var_refs(spec)
    if not refs:
        return

    locals_path = spec.get("locals")
    if not locals_path:
        # Pick one ref for the error message
        any_var = next(iter(refs))
        feat_name, field = refs[any_var][0]
        raise ValidationError(
            message=(
                f"feature '{feat_name}' field '{field}' uses rhs '\"{any_var}\"' "
                f"but spec has no `locals` path declared"
            ),
            path="$/locals",
        )

    p = Path(locals_path)
    if not p.exists():
        raise ValidationError(
            message=f"locals file not found: {p}",
            path="$/locals",
        )

    # Parse declared names from the file. Reuses locals_io.parse via the
    # established module so the regex stays in one place.
    # Read under ExclusiveLock to avoid racing with concurrent atomic_write
    # from mutate.py (and with OneDrive's transient post-replace handle).
    from ..locals_io import ExclusiveLock, parse

    try:
        with ExclusiveLock(p) as lock:
            text = lock.read_text()
    except OSError:
        # Fall back to a plain read if the lock can't be acquired (e.g.
        # validator running concurrently with the user editing the file
        # in an external editor). Stale-by-a-tick is acceptable here.
        text = p.read_text(encoding="utf-8")
    declared = {e.name for e in parse(text)}

    for var, sites in refs.items():
        if var not in declared:
            feat_name, field = sites[0]
            raise ValidationError(
                message=(
                    f"feature '{feat_name}' field '{field}' references "
                    f"variable '\"{var}\"' but it is not declared in {p.name}"
                ),
                path=f"$/features (rhs ref to '{var}')",
            )


def validate(spec: dict[str, Any]) -> None:
    """Run all three checks. Raises ValidationError on first failure."""
    _check_schema(spec)
    _check_references(spec)
    _check_locals(spec)
