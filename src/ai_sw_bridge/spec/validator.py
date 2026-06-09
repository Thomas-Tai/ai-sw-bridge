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
    EXPECT_SCHEMA,
    schema_for_version,
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


def _v2_enabled() -> bool:
    """Whether the `schema_v2` feature flag is ON.

    Resolved here (not cached) so env/TOML/CLI overrides apply per-call. The
    flags module is the single source of truth for the four-level precedence
    chain; we only read the one flag we own. Resolution is best-effort: if the
    flags module is somehow unavailable, v2 stays OFF (fail-closed, so a v2
    spec is rejected rather than silently accepted).
    """
    try:
        from ..flags import resolve as resolve_flags

        return bool(resolve_flags().get("schema_v2", False))
    except Exception:  # pragma: no cover - defensive; flags is in-tree
        return False


def _check_schema(spec: dict[str, Any]) -> None:
    """Raise ValidationError on the first jsonschema violation.

    Version-routed (X5, FR-1/FR-2): the schema validated against is chosen by
    the spec's declared `schema_version` and the `schema_v2` flag. v1 specs use
    the unchanged v1 ``SCHEMA``; v2 specs use the superset ``SCHEMA_V2`` only
    when the flag is ON, otherwise the v1 schema's `const: 1` rejects them.
    """
    cleaned = _strip_comments(spec)
    # `schema_version` may be absent/non-int (a malformed spec); fall back to
    # the v1 schema, which carries the required-key + `const` checks that emit
    # the right error.
    raw_version = cleaned.get("schema_version") if isinstance(cleaned, dict) else None
    version = raw_version if isinstance(raw_version, int) else SCHEMA["properties"][
        "schema_version"
    ]["const"]
    schema = schema_for_version(version, v2_enabled=_v2_enabled())
    try:
        jsonschema.validate(instance=cleaned, schema=schema)
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path)
        raise ValidationError(message=e.message, path=path or "$") from e


def _check_references(spec: dict[str, Any]) -> None:
    """Strict topological check: every reference points to an earlier feature
    of the right kind."""
    seen: dict[str, str] = {}  # name -> type
    features_by_name: dict[str, dict[str, Any]] = {}  # name -> full feature dict
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
            # revolve_boss / revolve_cut: the referenced sketch must declare
            # a centerline. SW would fail at build time with a cryptic error
            # (boss) or silently return None (cut) otherwise.
            if ftype in ("revolve_boss", "revolve_cut"):
                target_feat = features_by_name[target]
                if "centerline" not in target_feat:
                    raise ValidationError(
                        message=(
                            f"{ftype} requires '{target}' to declare a "
                            f"`centerline` (used as axis of revolution)"
                        ),
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
        features_by_name[name] = feat


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


def _check_locals(spec: dict[str, Any], spec_path: Path | None = None) -> None:
    """If any feature uses {rhs}, the spec must declare a `locals` path,
    that file must exist, and every quoted var ref must be defined in it.

    If `spec_path` is supplied and `spec["locals"]` is a relative path, the
    locals path is resolved relative to the spec file's directory. Absolute
    `locals` paths are used as-is (typical for production specs that point
    at a locals file in a sibling project).
    """
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
    if not p.is_absolute() and spec_path is not None:
        p = (spec_path.parent / p).resolve()
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


def _check_expect_blocks(spec: dict[str, Any]) -> None:
    """Validate any `_expect` blocks on features against EXPECT_SCHEMA.

    Runs on the RAW spec (before _strip_comments) because _expect is
    underscore-prefixed and would be stripped otherwise. Called after
    _check_schema so that malformed features fail fast with a clear path
    before we inspect their _expect blocks.
    """
    for i, feat in enumerate(spec.get("features", [])):
        if "_expect" not in feat:
            continue
        expect = feat["_expect"]
        try:
            jsonschema.validate(instance=expect, schema=EXPECT_SCHEMA)
        except jsonschema.ValidationError as e:
            path = "/".join(str(p) for p in e.absolute_path)
            raise ValidationError(
                message=f"invalid _expect block: {e.message}",
                path=(
                    f"features/{i}/_expect/{path}" if path else f"features/{i}/_expect"
                ),
            ) from e


def _check_face_role_shapes(spec: dict[str, Any]) -> None:
    """Fourth validation layer (E2.5, spec.md §2.6): structural check on
    ``face_role`` fields of face-bound features.

    The manifest doesn't exist at spec-ingest time (the parent feature
    hasn't been built yet), so the validator can only confirm shape:
    when ``face_role`` is declared, it must be a non-empty string.
    Actual role-to-fingerprint resolution runs at build-time via
    ``brep.resolver.resolve_face_role``.
    """
    for i, feat in enumerate(spec.get("features", [])):
        if "face_role" not in feat:
            continue
        role = feat["face_role"]
        if not isinstance(role, str) or not role.strip():
            raise ValidationError(
                message=(f"face_role must be a non-empty string; got {role!r}"),
                path=f"features/{i}/face_role",
            )
        if feat.get("type") not in FACE_BOUND_TYPES:
            raise ValidationError(
                message=(
                    f"face_role is only supported on face-bound features "
                    f"({sorted(FACE_BOUND_TYPES)}); feature '{feat.get('name')}' "
                    f"is of type '{feat.get('type')}'"
                ),
                path=f"features/{i}/face_role",
            )


def compute_referenced_face_roles(spec: dict[str, Any]) -> set[tuple[str, str]]:
    """Compute which (parent_feature_name, face_role) pairs are referenced
    by downstream features. Used by the builder to enable lazy B-rep
    interrogation (spec.md §2.11): features not in this set can skip
    face walking entirely."""
    refs: set[tuple[str, str]] = set()
    for feat in spec.get("features", []):
        if feat.get("type") not in FACE_BOUND_TYPES:
            continue
        parent = feat.get("of_feature")
        role = feat.get("face_role")
        if parent and role:
            refs.add((parent, role))
    return refs


def _check_relations(spec: dict[str, Any]) -> None:
    """Sixth validation layer (W39): sketch relation type/arity/ref checks.

    Validates any ``relations`` blocks on sketch features: known relation
    types only, correct entity arity per type, entity refs are non-negative
    integers, no duplicate refs within a single relation. Schema-level
    checks (JSON Schema enum/int constraints) catch most malformation; this
    layer adds the cross-field arity enforcement that JSON Schema can't
    express cleanly with ``additionalProperties: false``.
    """
    from ._sketch_relations import RELATION_ARITY, SUPPORTED_RELATION_TYPES

    for i, feat in enumerate(spec.get("features", [])):
        relations = feat.get("relations")
        if relations is None:
            continue
        if not isinstance(relations, list):
            raise ValidationError(
                message="relations must be an array",
                path=f"features/{i}/relations",
            )
        for j, rel in enumerate(relations):
            if not isinstance(rel, dict):
                raise ValidationError(
                    message="each relation must be an object",
                    path=f"features/{i}/relations/{j}",
                )
            rtype = rel.get("type")
            if rtype not in SUPPORTED_RELATION_TYPES:
                raise ValidationError(
                    message=(
                        f"unknown relation type {rtype!r}; supported: "
                        f"{sorted(SUPPORTED_RELATION_TYPES)}"
                    ),
                    path=f"features/{i}/relations/{j}/type",
                )
            entities = rel.get("entities", [])
            expected = RELATION_ARITY.get(rtype, 0)
            if len(entities) != expected:
                raise ValidationError(
                    message=(
                        f"relation type {rtype!r} requires {expected} "
                        f"entities, got {len(entities)}"
                    ),
                    path=f"features/{i}/relations/{j}/entities",
                )
            for k, ref in enumerate(entities):
                if not isinstance(ref, int) or ref < 0:
                    raise ValidationError(
                        message=(
                            f"entity ref must be a non-negative integer "
                            f"segment index, got {ref!r}"
                        ),
                        path=f"features/{i}/relations/{j}/entities/{k}",
                    )
            if len(set(entities)) != len(entities):
                raise ValidationError(
                    message=f"duplicate entity references in {entities}",
                    path=f"features/{i}/relations/{j}/entities",
                )


def validate(spec: dict[str, Any], spec_path: Path | None = None) -> None:
    """Run all checks. Raises ValidationError on first failure.

    `spec_path` is optional. When supplied, relative `locals` paths in the
    spec are resolved relative to the spec file's directory. Callers that
    already pass absolute paths in `spec["locals"]` can omit it.
    """
    _check_schema(spec)
    _check_expect_blocks(spec)
    _check_references(spec)
    _check_face_role_shapes(spec)
    _check_relations(spec)
    _check_locals(spec, spec_path=spec_path)
